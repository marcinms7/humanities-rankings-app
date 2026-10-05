"""Resumable downloads of individually reviewed public cover sources.

The registry is evidence, not an instruction to overwrite catalog identities.
Only exact current work/author identities are admitted. Revisions reopen only
the affected queue records; discovery never fetches an arbitrary search page.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from research.media_transport import CandidateRejected, public_url, validate_external_url

POLICY_VERSION = 'reviewed-source-v1'
REGISTRY = Path(__file__).with_name('reviewed_cover_candidates.json')


def _url(value):
    if not isinstance(value, str) or not value:
        raise ValueError('Reviewed cover requires a public URL')
    try:
        parts = validate_external_url(value)
    except CandidateRejected as error:
        raise ValueError('Invalid reviewed cover URL') from error
    if parts.scheme != 'https' or public_url(value) != value:
        raise ValueError('Reviewed cover URLs must use HTTPS without secrets or fragments')
    return value


def load_registry(path=None):
    path = Path(path or REGISTRY)
    if not path.exists():
        return {}
    payload = json.loads(path.read_text())
    if payload.get('version') != 1 or not isinstance(payload.get('candidates'), list):
        raise ValueError('Unsupported reviewed cover registry')
    grouped = {}
    for entry in payload['candidates']:
        if not isinstance(entry, dict):
            raise ValueError('Invalid reviewed cover entry')
        identity, title, authors = entry.get('work_id'), entry.get('title'), entry.get('authors')
        if (type(identity) is not int or identity <= 0 or not isinstance(title, str) or not title.strip()
                or not isinstance(authors, list)
                or not all(isinstance(name, str) and name.strip() for name in authors)):
            raise ValueError('Reviewed cover must pin its catalog work and authors')
        source, image = _url(entry.get('source_url')), _url(entry.get('image_url'))
        evidence = entry.get('evidence')
        if (not isinstance(evidence, dict) or not evidence.get('title')
                or not isinstance(evidence.get('authors'), list)
                or (authors and not evidence['authors'])
                or (not authors and not evidence.get('note'))
                or not isinstance(entry.get('image_attribution'), str) or not entry['image_attribution'].strip()):
            raise ValueError('Reviewed cover requires title/author evidence and credit')
        if entry.get('cover_basis', 'representative_work') not in {'representative', 'representative_work'}:
            raise ValueError('Reviewed covers do not establish an exact catalog edition')
        if (evidence.get('image_sha256') is not None
                and not re.fullmatch(r'[0-9a-f]{64}', str(evidence['image_sha256']))):
            raise ValueError('Invalid reviewed cover image digest')
        hosts = entry.get('allowed_image_hosts', [urlsplit(image).hostname])
        if (not isinstance(hosts, list) or not hosts
                or not all(isinstance(host, str) and host and
                           urlsplit(_url('https://' + host)).netloc == host for host in hosts)):
            raise ValueError('Reviewed redirect hosts must be explicit public hostnames')
        if urlsplit(image).hostname not in hosts:
            raise ValueError('Reviewed image host is not allowed')
        grouped.setdefault(identity, []).append({**entry, 'source_url': source,
                                                 'image_url': image, 'allowed_image_hosts': hosts})
    return grouped


def _matching(item, registry):
    return [entry for entry in registry.get(item['id'], [])
            if entry['title'] == item.get('display_title', item['title'])
            and sorted(entry['authors']) == sorted(item.get('authors', []))]


def prepare_items(items, *, registry=None):
    registry = load_registry() if registry is None else registry
    result = []
    for item in items:
        entries = _matching(item, registry)
        if not entries:
            continue
        revision = hashlib.sha256(json.dumps(entries, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        result.append({**item, 'provider_identifiers': {**item.get('provider_identifiers', {}),
                       'reviewed_covers': revision}, '_reviewed_candidates': entries})
    return result


def is_openlibrary_api_image(entry):
    """Use the existing Covers API policy only for its reviewed image assets.

    Publisher/author pages and image URLs keep robots checks. Open Library's
    API images have their own public endpoint, including advertised Archive
    storage redirects, and use the same host cooldowns as every other request.
    """
    source, image = urlsplit(entry['source_url']), urlsplit(entry['image_url'])
    api_url = entry['evidence'].get('api_image_url', '')
    if (source.hostname not in {'openlibrary.org', 'www.openlibrary.org'}
            or not re.fullmatch(r'/(?:works/OL\d+W|books/OL\d+M)/?', source.path)
            or not re.fullmatch(r'https://covers\.openlibrary\.org/b/id/[1-9]\d*-L\.jpg\?default=false', api_url)):
        return False
    if entry['image_url'] == api_url:
        return True
    archive = image.hostname == 'archive.org' or re.fullmatch(r'ia\d+\.(?:us|eu)\.archive\.org', image.hostname or '')
    return bool(archive and (image.path.startswith('/download/olcovers') or image.path == '/view_archive.php'))


def candidates(item):
    # Re-read at discovery so an edited registry cannot retain a withdrawn URL
    # through an in-memory prepared item. CandidateStore keys include revision.
    entries = _matching(item, load_registry())
    return [{'source': entry['source_url'], 'image_url': entry['image_url'],
             'credit': entry['image_attribution'], 'matched_title': entry['evidence']['title'],
             'matched_authors': entry['evidence']['authors'], 'review_evidence': entry['evidence'],
             'expected_sha256': entry['evidence'].get('image_sha256'),
             'allowed_image_hosts': entry['allowed_image_hosts'],
             'image_respect_robots': not is_openlibrary_api_image(entry),
             'cover_basis': 'representative_work'} for entry in entries]
