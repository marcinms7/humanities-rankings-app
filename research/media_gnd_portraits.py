"""Credited GND portraits corroborated by a catalog work's library author ID.

lobid supplies keyless GND authority and library bibliography APIs. Image rights
belong to each depiction, not the CC0 authority metadata. Images remain on their
advertised Wikimedia hosts, with the common transport's cooldowns intact.
"""
from __future__ import annotations

import html
import re
from urllib.parse import urlencode, urlsplit

from research.media_matching import match_item_title, same_author, words_in_order
from research.media_text_evidence import portrait_work_records
from research.media_transport import CandidateRejected, fetch_json
from research.media_wikimedia import WIKIMEDIA_IMAGE_HOSTS

API_HOSTS = frozenset({'lobid.org'})
MAX_NAMES = 3
MAX_ENTITIES = 8
MAX_WORKS = 4
MAX_BOOKS = 12
MAX_CANDIDATES = 6
AUTHOR_ROLE = 'id.loc.gov/vocabulary/relators/aut'


def _text(value):
    return html.unescape(re.sub(r'<[^>]*>', ' ', str(value or ''))).strip()


def _list(value):
    return value if isinstance(value, list) else []


def _url(value, hosts):
    if not isinstance(value, str):
        return ''
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in {'http', 'https'} or parsed.hostname not in hosts
                or parsed.username or parsed.password or parsed.port not in {None, 80, 443}):
            return ''
    except ValueError:
        return ''
    return value


def _gnd(value):
    value = _url(value, {'d-nb.info'})
    parsed = urlsplit(value)
    match = re.fullmatch(r'/gnd/(\d[\dX-]{3,15})', parsed.path)
    if not match or parsed.query or parsed.fragment:
        return ''
    return match[1]


def _terms(value):
    # Only words enter Lucene syntax; provider records never inject operators.
    return ' AND '.join('"' + word + '"' for word in words_in_order(value)[:24])


def _search(kind, query, limit, fetch, *, require_complete=True):
    url = 'https://lobid.org/' + kind + '/search?' + urlencode({
        'q': query, 'format': 'json', 'size': limit,
    })
    try:
        result = fetch(url, allowed_hosts=API_HOSTS, cache_ttl=86400, min_interval=2.1)
    except CandidateRejected:
        return []
    if not isinstance(result, dict) or not isinstance(result.get('member'), list):
        raise ValueError('lobid returned invalid catalog metadata')
    total = result.get('totalItems')
    if type(total) is not int or total < 0:
        raise ValueError('lobid did not report a valid result count')
    # Authority completeness determines the possible identities. When several
    # identities remain, a partial bibliography could hide another namesake's
    # matching work. One fully resolved identity needs only positive authorship
    # evidence, not every edition of that work. Never paginate either search.
    if (len(result['member']) > limit or total < len(result['member'])
            or (require_complete and (total > limit or total > len(result['member'])))):
        return []
    return [row for row in result['member'][:limit] if isinstance(row, dict)]


def _licensed_images(entity):
    result = []
    for depiction in _list(entity.get('depiction'))[:3]:
        if not isinstance(depiction, dict):
            continue
        rights = []
        for license in _list(depiction.get('license')):
            if not isinstance(license, dict):
                continue
            uri = _url(license.get('id'), {'creativecommons.org', 'www.creativecommons.org'})
            path = urlsplit(uri).path.rstrip('/')
            if (re.fullmatch(r'/licenses/by(?:-sa)?/\d\.\d(?:/[^/]+)?', path)
                    or re.fullmatch(r'/publicdomain/(?:mark|zero)/1\.0(?:/deed\.[a-z-]+)?', path)):
                rights.append((_text(license.get('abbr') or license.get('name')), uri))
        creators = [_text(value) for value in _list(depiction.get('creatorName')) if _text(value)]
        source = _url(depiction.get('url'), {'commons.wikimedia.org'})
        if not rights or not rights[0][0] or not creators or not source:
            continue
        if not urlsplit(source).path.startswith('/wiki/File:'):
            continue
        for key in ('thumbnail', 'id'):
            image = _url(depiction.get(key), set(WIKIMEDIA_IMAGE_HOSTS))
            if not image:
                continue
            parsed = urlsplit(image)
            if parsed.hostname == 'commons.wikimedia.org' and not parsed.path.startswith('/wiki/Special:FilePath/'):
                continue
            result.append({'source': source, 'source_url': source, 'image_url': image,
                'allowed_image_hosts': list(WIKIMEDIA_IMAGE_HOSTS),
                'rights': rights[0][0], 'rights_url': rights[0][1],
                'credit': f'Portrait / historical depiction. {", ".join(creators)} · {rights[0][0]}. Wikimedia Commons via lobid GND.',
                'image_metadata': depiction})
    return result


def candidates(item, fetch=None):
    """At most two metadata requests; a name alone never accepts a portrait."""
    fetch = fetch or fetch_json
    names = [item['title'], *item.get('title_aliases', [])][:MAX_NAMES]
    clauses = [f'(preferredName:({_terms(name)}) OR variantName:({_terms(name)}))'
               for name in names if _terms(name)]
    if not clauses:
        return []
    entities = {}
    for entity in _search('gnd', '(' + ' OR '.join(clauses) + ') AND type:Person', MAX_ENTITIES, fetch):
        identity = _gnd(entity.get('id'))
        if (not identity or 'DifferentiatedPerson' not in _list(entity.get('type'))
                or not same_author(names, [entity.get('preferredName', ''), *_list(entity.get('variantName'))])):
            continue
        images = _licensed_images(entity)
        entities[identity] = (entity, images)
    if not any(images for _, images in entities.values()):
        return []
    works = portrait_work_records(item)[:MAX_WORKS]
    works = [work for work in works if isinstance(work.get('title'), str) and _terms(work['title'])]
    titles = list(dict.fromkeys(title for work in works
        for title in [work['title'], *work.get('title_aliases', [])[:2]] if _terms(title)))
    if not titles:
        return []
    title_query = ' OR '.join(f'title:({_terms(title)})' for title in titles)
    # Match exactly in code too: GND identifiers are not evidence of authorship
    # when present only as a book's subject, translator or editor.
    ids_query = ' OR '.join('"https://d-nb.info/gnd/' + identity + '"' for identity in entities)
    books = _search('resources', f'contribution.agent.id:({ids_query}) AND ({title_query})', MAX_BOOKS, fetch,
                    require_complete=len(entities) != 1)
    evidence = {}
    for book in books:
        source = _url(book.get('id'), {'lobid.org'})
        if not source or not re.fullmatch(r'/resources/[A-Za-z0-9_-]+', urlsplit(source).path):
            continue
        base_title = _text(book.get('title'))
        record_titles = [base_title] + [base_title + ': ' + _text(subtitle)
            for subtitle in _list(book.get('otherTitleInformation')) if _text(subtitle)]
        matched = [work['title'] for work in works
                   if any(match_item_title(work, title)[0] for title in record_titles)]
        if not matched:
            continue
        for contribution in _list(book.get('contribution')):
            if not isinstance(contribution, dict):
                continue
            agent, role = contribution.get('agent', {}), contribution.get('role', {})
            if not isinstance(agent, dict) or not isinstance(role, dict):
                continue
            identity = _gnd(agent.get('id'))
            role_url = _url(role.get('id'), {'id.loc.gov'})
            if (identity not in entities or role_url.split('://', 1)[-1] != AUTHOR_ROLE
                    or 'Person' not in _list(agent.get('type'))
                    or not same_author(names, [agent.get('label', ''), *_list(agent.get('altLabel'))])):
                continue
            evidence.setdefault(identity, []).append({'work': matched[0], 'source': source,
                'author': agent.get('label', ''), 'authority': 'https://d-nb.info/gnd/' + identity})
    # Multiple corroborated namesakes are ambiguous even when just one has a
    # convenient image. Never choose an arbitrary first author.
    if len(evidence) != 1:
        return []
    identity, proof = next(iter(evidence.items()))
    result = []
    seen = set()
    for image in entities[identity][1]:
        if image['image_url'] in seen:
            continue
        seen.add(image['image_url'])
        result.append({**image, 'provider': 'gnd-portraits', 'title': entities[identity][0]['preferredName'],
            'identity_basis': 'lobid_catalog_work_author_gnd', 'subject_authority': proof[0]['authority'],
            'matched_works': list(dict.fromkeys(row['work'] for row in proof)),
            'identity_evidence': proof, 'depiction_kind': 'historical_depiction'})
        if len(result) >= MAX_CANDIDATES:
            break
    return result
