"""Bounded Wellcome portraits linked to authors of known catalog works.

Uses the public Catalogue API and its item-specific IIIF image/rights records.
A picture's named subject is insufficient: that Person authority must also be
the author of a matching catalog work, or an explicitly reviewed identity URI.
No image bodies or catalog data are written here.
"""
from __future__ import annotations

import html
import re
from urllib.parse import urlencode, urlsplit

from research.media_matching import match_item_title, same_author
from research.media_transport import CandidateRejected, fetch_json

API_HOSTS = frozenset({'api.wellcomecollection.org'})
IMAGE_HOSTS = frozenset({'iiif.wellcomecollection.org'})
MAX_RESULTS = 8
MAX_WORKS = 2
MAX_CANDIDATES = 8
OPEN_LICENSES = frozenset({'pdm', 'cc0', 'cc-by', 'cc-by-sa'})


def _text(value):
    return html.unescape(re.sub(r'<[^>]+>', ' ', str(value or ''))).strip()


def _id(value):
    return value if isinstance(value, str) and re.fullmatch(r'[a-z0-9]{8}', value) else ''


def _safe_url(value, hosts):
    if not isinstance(value, str):
        return ''
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in {'http', 'https'} or parsed.hostname not in hosts
                or parsed.username or parsed.password or parsed.port not in {None, 80, 443}
                or parsed.query or parsed.fragment):
            return ''
    except ValueError:
        return ''
    return parsed._replace(scheme='https').geturl()


def _search(query, work_type, fetch):
    url = 'https://api.wellcomecollection.org/catalogue/v2/works?' + urlencode({
        'query': query, 'workType': work_type, 'pageSize': MAX_RESULTS,
        'include': 'subjects,contributors,items',
    })
    try:
        response = fetch(url, allowed_hosts=API_HOSTS)
    except CandidateRejected:
        return []
    if not isinstance(response, dict) or not isinstance(response.get('results'), list):
        raise ValueError('Wellcome returned invalid catalog metadata')
    return [row for row in response['results'][:MAX_RESULTS] if isinstance(row, dict)]


def _portrait_subject(record, names):
    # Restrict to pictures. Letters and authored books can have the same name
    # and a thumbnail, but their first pages are not portraits.
    if record.get('workType', {}).get('id') != 'k':
        return None
    subjects = {}
    for subject in record.get('subjects', []):
        for concept in subject.get('concepts', []):
            if concept.get('type') == 'Person' and _id(concept.get('id')):
                subjects[concept['id']] = concept
    if len(subjects) != 1:
        return None  # A group picture or an uncertain unnamed sitter.
    subject = next(iter(subjects.values()))
    if not same_author(names, [subject.get('label', '')]):
        return None
    title = _text(record.get('title'))
    # Standalone named sitter followed by a medium; reject buildings, monuments,
    # narrative scenes and pictures by the person rather than of the person.
    title = re.sub(r'^(?:portrait|bust) of\s+', '', title, flags=re.I)
    head = re.split(r'\.\s+(?=(?:colou?red |stipple |line |steel |copper |wood |oil )?'
                    r'(?:engraving|lithograph|photograph|painting|drawing|etching|mezzotint|woodcut|portrait)\b)',
                    title, maxsplit=1, flags=re.I)[0].rstrip(' .')
    if not same_author(names, [head]):
        return None
    return subject


def _authorities(item, fetch):
    names = [item['title'], *item.get('title_aliases', [])]
    evidence = {}
    for work in item.get('works', item.get('authors', []))[:MAX_WORKS]:
        expected = work if isinstance(work, dict) else {'title': work}
        if not expected.get('title'):
            continue
        for record in _search(expected['title'], 'a', fetch):
            if record.get('workType', {}).get('id') != 'a':
                continue
            title = _text(record.get('title')).split(' / ', 1)[0].rstrip(' .;:')
            if not match_item_title(expected, title)[0]:
                continue
            for contribution in record.get('contributors', []):
                agent = contribution.get('agent', {})
                roles = {_text(role.get('label')).casefold() for role in contribution.get('roles', [])}
                author = 'author' in roles or (contribution.get('primary') is True and not roles)
                if (not author or agent.get('type') != 'Person' or not _id(agent.get('id'))
                        or not same_author(names, [agent.get('label', '')]) or not _id(record.get('id'))):
                    continue
                evidence.setdefault(agent['id'], []).append({
                    'work': expected['title'], 'source': 'https://wellcomecollection.org/works/' + record['id'],
                    'heading': agent['label'],
                })
    return evidence


def _image_location(location):
    license = location.get('license', {})
    if license.get('id') not in OPEN_LICENSES:
        return None
    rights_url = _safe_url(license.get('url'), {'creativecommons.org'})
    if not rights_url:
        return None
    conditions = location.get('accessConditions', [])
    if any(row.get('status', {}).get('id') not in {None, 'open'} for row in conditions):
        return None
    url = _safe_url(location.get('url'), IMAGE_HOSTS)
    # A known IIIF image service only, never presentation manifests or generic
    # page thumbnails. Preserve the whole original image (no guessed cropping).
    match = re.fullmatch(r'https://iiif\.wellcomecollection\.org/image/([A-Za-z0-9_.-]+)/'
                         r'(?:info\.json|full/[^/]+/0/default\.jpg)', url)
    if not match:
        return None
    return (f'https://iiif.wellcomecollection.org/image/{match[1]}/full/600,/0/default.jpg',
            _text(license.get('label')), rights_url, _text(location.get('credit')) or 'Wellcome Collection')


def candidates(item, fetch=None):
    """Return at most eight credited portrait candidates using <=3 requests."""
    fetch = fetch or fetch_json
    names = [item['title'], *item.get('title_aliases', [])]
    pictures = [(row, _portrait_subject(row, names)) for row in _search(item['title'], 'k', fetch)]
    pictures = [(row, subject) for row, subject in pictures if subject and _id(row.get('id'))]
    if not pictures:
        return []
    authorities = _authorities(item, fetch)
    proven = set(item.get('verified_identity_urls', []))
    result = []
    seen = set()
    for record, subject in pictures:
        subject_uri = 'https://api.wellcomecollection.org/catalogue/v2/concepts/' + subject['id']
        evidence = authorities.get(subject['id'], [])
        if not evidence and subject_uri not in proven:
            continue
        identity = [f'Author of catalog work {row["work"]}: {row["heading"]} ({row["source"]}); '
                    f'same Wellcome subject {subject["id"]}' for row in evidence]
        if subject_uri in proven:
            identity.append('Verified authority URI: ' + subject_uri)
        locations = [location for instance in record.get('items', []) for location in instance.get('locations', [])]
        if isinstance(record.get('thumbnail'), dict):
            locations.append(record['thumbnail'])
        artists = [_text(row.get('agent', {}).get('label')) for row in record.get('contributors', [])]
        for location in locations:
            image = _image_location(location)
            if not image or image[0] in seen:
                continue
            image_url, rights, rights_url, credit = image
            seen.add(image_url)
            source = 'https://wellcomecollection.org/works/' + record['id']
            result.append({
                'provider': 'wellcome-portraits', 'source': source, 'source_url': source,
                'image_url': image_url, 'allowed_image_hosts': sorted(IMAGE_HOSTS),
                'credit': f'Portrait / historical depiction. {", ".join(artists)} · {credit} · {rights}.',
                'rights': rights, 'rights_url': rights_url, 'title': _text(record.get('title')),
                'depiction_kind': 'historical_depiction', 'identity_basis': 'wellcome_catalog_work_author_subject',
                'identity_evidence': identity, 'subject_authority': subject_uri,
                'matched_works': list(dict.fromkeys(row['work'] for row in evidence)),
            })
            if len(result) >= MAX_CANDIDATES:
                return result
    return result
