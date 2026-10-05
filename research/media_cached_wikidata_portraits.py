"""Reuse public library identity evidence for batched Wikidata portraits.

The process-local index reads existing response files once. It sends no Open
Library requests, and only public authority IDs/file names leave this module.
No catalog data is written; download/transactional ingestion stay with callers.
"""
from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
import html
import json
from pathlib import Path
import re
import time
from urllib.parse import urlencode, urlsplit

from research.media_matching import norm
from research.media_portrait_bibliography import matched_work_titles
from research import media_transport as transport
from research.media_wikimedia import WIKIMEDIA_IMAGE_HOSTS
from research.operational_state import atomic_state

POLICY_VERSION = 'cached-reciprocal-library-wikidata-v1'
MAX_BATCH = 50
_AUTHOR = re.compile(r'/authors/(OL[1-9]\d*A)')
_WORK = re.compile(r'/works/OL[1-9]\d*W')
_QID = re.compile(r'Q[1-9]\d*')
ENTITY_TTL = 86400


class PartialDiscovery(transport.ProviderOutage):
    """A metadata outage with safe input-indexed results to checkpoint first."""
    def __init__(self, error, completed):
        super().__init__(error.reason, retry_after=error.retry_after, status=error.status,
                         outage_type=error.outage_type)
        self.completed = completed


def _read(path):
    try:
        if path.stat().st_size > transport.MAX_BYTES:
            return None
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, UnicodeDecodeError):
        return None


def _author_keys(work):
    for entry in work.get('authors', []) if isinstance(work.get('authors'), list) else []:
        if isinstance(entry, dict) and isinstance(entry.get('author'), dict):
            key = entry['author'].get('key')
            if isinstance(key, str) and _AUTHOR.fullmatch(key):
                yield key


@lru_cache(maxsize=2)
def _index(response_root):
    """One bounded-file cache scan per worker process, reused by every batch."""
    authors, records = {}, defaultdict(dict)
    for metadata_path in Path(response_root).glob('*/*.json'):
        metadata = _read(metadata_path)
        url = metadata.get('final_url', '') if metadata else ''
        if not isinstance(url, str):
            continue
        try:
            parts = urlsplit(url)
        except ValueError:
            continue
        if parts.scheme != 'https' or parts.hostname != 'openlibrary.org' or parts.username or parts.password:
            continue
        path = parts.path.removesuffix('.json')
        author_match = _AUTHOR.fullmatch(path)
        works_match = re.fullmatch(r'(/authors/OL[1-9]\d*A)/works', path)
        work_match = _WORK.fullmatch(path)
        if not (author_match or works_match or work_match):
            continue
        body = metadata_path.with_suffix('')
        data = _read(body)
        if data is None:
            continue
        try:
            modified = body.stat().st_mtime_ns
        except OSError:
            continue
        if author_match:
            if data.get('key') != path or not isinstance(data.get('name'), str):
                continue
            if modified >= authors.get(path, {}).get('modified', 0):
                authors[path] = {'record': data, 'modified': modified}
            continue
        entries = data.get('entries', []) if works_match else [data]
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get('title'), str):
                continue
            key = entry.get('key')
            if not isinstance(key, str) or not _WORK.fullmatch(key):
                continue
            if work_match and key != path:
                continue
            for author_key in _author_keys(entry):
                if works_match and author_key != works_match[1]:
                    continue
                previous = records[author_key].get(key)
                if previous is None or modified >= previous[0]:
                    records[author_key][key] = (modified, entry)
    names = defaultdict(set)
    for key, value in authors.items():
        record = value['record']
        alternate = record.get('alternate_names', [])
        for name in [record['name'], *(alternate if isinstance(alternate, list) else [])]:
            if isinstance(name, str) and norm(name):
                names[norm(name)].add(key)
    return {'authors': {key: value['record'] for key, value in authors.items()},
            'works': {key: [row[1] for row in value.values()] for key, value in records.items()},
            'names': dict(names)}


def cached_identity(item):
    """Return one complete-name, reciprocal-work identity, or no safe match."""
    index = _index(str(transport.STATE / 'responses'))
    keys = set()
    for name in [item.get('title', ''), *item.get('title_aliases', [])]:
        if isinstance(name, str):
            keys.update(index['names'].get(norm(name), set()))
    identities = []
    for key in sorted(keys):
        record = index['authors'][key]
        works = index['works'].get(key, [])
        matches = matched_work_titles(item, works, author_key=key)
        if not matches:
            continue
        sources = [
            'https://openlibrary.org' + work['key'] for work in works
            if matched_work_titles(item, [work], author_key=key)
        ]
        identities.append({'author_key': key.removeprefix('/authors/'), 'name': record['name'],
            'matched_works': matches, 'identity_sources': list(dict.fromkeys([
                'https://openlibrary.org' + key, *sources])),
            'wikidata': record.get('remote_ids', {}).get('wikidata')
                        if isinstance(record.get('remote_ids'), dict) else None})
    if len(identities) != 1:
        return None
    identity = identities[0]
    return identity if isinstance(identity['wikidata'], str) and _QID.fullmatch(identity['wikidata']) else None


def _entity_complete(data, qids):
    if not isinstance(data, dict) or 'error' in data or not isinstance(data.get('entities'), dict):
        return False
    for qid in qids:
        entity = data['entities'].get(qid)
        if not isinstance(entity, dict):
            return False
        if 'missing' in entity:
            continue
        if not isinstance(entity.get('claims'), dict):
            return False
        for field in ('labels', 'aliases'):
            if not isinstance(entity.get(field), dict):
                return False
        for prop in ('P31', 'P648', 'P18'):
            claims = entity['claims'].get(prop, [])
            if not isinstance(claims, list):
                return False
            for claim in claims:
                if not isinstance(claim, dict) or not isinstance(claim.get('mainsnak'), dict):
                    return False
                if not isinstance(claim['mainsnak'].get('datavalue', {}), dict):
                    return False
        labels = entity['labels'].get('en', {})
        aliases = entity['aliases'].get('en', [])
        if not isinstance(labels, dict) or not isinstance(labels.get('value', ''), str):
            return False
        if not isinstance(aliases, list) or any(not isinstance(row, dict) or not isinstance(row.get('value'), str) for row in aliases):
            return False
    return True


def _values(claims, prop):
    return [claim['mainsnak'].get('datavalue', {}).get('value')
            for claim in claims.get(prop, []) if claim.get('rank') != 'deprecated']


def _entity_path(qid):
    return transport.STATE / 'wikidata-entities' / (qid + '.json')


def _entities(qids, fetch):
    """Checkpoint individual authorities across changed batch composition."""
    entities = {}
    for qid in qids:
        saved = _read(_entity_path(qid))
        if not saved or saved.get('schema') != 1 or saved.get('qid') != qid:
            continue
        stamp = saved.get('fetched_at')
        if type(stamp) not in (int, float) or not 0 <= time.time() - stamp < ENTITY_TTL:
            continue
        data = {'entities': {qid: saved.get('entity')}}
        if _entity_complete(data, [qid]):
            entities[qid] = saved['entity']
    missing = [qid for qid in qids if qid not in entities]
    if not missing:
        return entities
    url = 'https://www.wikidata.org/w/api.php?' + urlencode({
        'action': 'wbgetentities', 'ids': '|'.join(missing), 'props': 'claims|labels|aliases',
        'languages': 'en', 'format': 'json', 'formatversion': 2, 'maxlag': 5,
    })
    try:
        data = fetch(url, allowed_hosts={'www.wikidata.org'},
                     json_cacheable=lambda value: _entity_complete(value, missing))
    except transport.CandidateRejected:
        raise transport.ProviderOutage('Wikidata metadata response could not be verified') from None
    now = time.time()
    complete = _entity_complete(data, missing)
    # A partial response cannot come from this request's HTTP cache: its
    # completeness predicate rejects both cache reuse and cache writes. Any
    # retained old whole-body file therefore predates this fresh partial data.
    origin = transport.response_cache_timestamp(url, allowed_hosts={'www.wikidata.org'}) if complete else None
    # A response read from a 23-hour-old HTTP cache has one hour remaining,
    # even when its per-authority checkpoint was created just now.
    stamp = min(origin, now) if origin is not None else now
    for qid in missing:
        if _entity_complete(data, [qid]):
            entities[qid] = data['entities'][qid]
            atomic_state(_entity_path(qid), {'schema': 1, 'qid': qid, 'fetched_at': stamp,
                'source_url': 'https://www.wikidata.org/entity/' + qid, 'entity': entities[qid]})
    if not complete:
        raise transport.ProviderOutage('Incomplete cached-identity Wikidata response')
    return entities


def _file_pages(data, filenames):
    """Resolve explicit redirects; omitted or malformed requested rows defer."""
    if not isinstance(data, dict) or 'error' in data or not isinstance(data.get('query'), dict):
        return None
    query = data['query']
    if not isinstance(query.get('pages'), list):
        return None
    redirects = {}
    for field in ('normalized', 'redirects'):
        rows = query.get(field, [])
        if not isinstance(rows, list):
            return None
        for row in rows:
            if not isinstance(row, dict) or not all(isinstance(row.get(key), str) for key in ('from', 'to')):
                return None
            redirects[row['from'].replace('_', ' ')] = row['to'].replace('_', ' ')
    pages = {}
    for page in query['pages']:
        if not isinstance(page, dict) or not isinstance(page.get('title'), str):
            return None
        pages[page['title'].replace('_', ' ')] = page
    result = {}
    for filename in filenames:
        title, seen = 'File:' + filename.replace('_', ' '), set()
        while title in redirects and title not in seen:
            seen.add(title)
            title = redirects[title]
        page = pages.get(title)
        if page is None:
            return None
        if 'missing' in page or 'invalid' in page:
            result[filename] = []
            continue
        info = page.get('imageinfo')
        if not isinstance(info, list):
            return None
        for image in info:
            if not isinstance(image, dict) or not isinstance(image.get('extmetadata', {}), dict):
                return None
            for field in ('Artist', 'LicenseShortName', 'LicenseUrl'):
                value = image.get('extmetadata', {}).get(field, {})
                if not isinstance(value, dict) or not isinstance(value.get('value', ''), str):
                    return None
            if any(key in image and not isinstance(image[key], str) for key in ('url', 'thumburl', 'descriptionurl')):
                return None
        result[filename] = info
    return result


def batch_candidates(items, fetch=None):
    """Return candidate lists aligned with at most fifty catalog people."""
    if len(items) > MAX_BATCH:
        raise ValueError('Cached Wikidata portrait batches are limited to fifty people')
    fetch = fetch or transport.fetch_json
    identities = [cached_identity(item) for item in items]
    if any(identity is None for identity in identities):
        # A provider's absent local evidence can change as other sources fill
        # the public cache. It is never a durable no-portrait decision.
        raise transport.ProviderOutage('Cached library identity evidence is not available',
                                       retry_after=time.time() + 300)
    qids = list(dict.fromkeys(identity['wikidata'] for identity in identities if identity))
    if not qids:
        return [[] for _ in items]
    entities = _entities(qids, fetch)
    selected = []
    for identity in identities:
        if identity is None:
            selected.append(None)
            continue
        entity = entities[identity['wikidata']]
        claims = entity.get('claims', {})
        human = any(isinstance(value, dict) and value.get('id') == 'Q5' for value in _values(claims, 'P31'))
        reciprocal = _values(claims, 'P648')
        label = entity.get('labels', {}).get('en', {}).get('value', '')
        labels = [label, *[row['value'] for row in entity.get('aliases', {}).get('en', [])]]
        consistent = identity['author_key'] in reciprocal if reciprocal else norm(identity['name']) in {norm(name) for name in labels}
        if not human or not consistent:
            selected.append(None)
            continue
        filenames = list(dict.fromkeys(value for value in _values(claims, 'P18')
            if isinstance(value, str) and value and not re.search(r'[|\r\n]', value)))[:3]
        selected.append({**identity, 'filenames': filenames})
    filenames = list(dict.fromkeys(filename for identity in selected if identity for filename in identity['filenames']))
    pictures = {}
    for start in range(0, len(filenames), 50):
        group = filenames[start:start + 50]
        try:
            data = fetch('https://commons.wikimedia.org/w/api.php?' + urlencode({
                'action': 'query', 'titles': '|'.join('File:' + name for name in group),
                'redirects': 1, 'prop': 'imageinfo', 'iiprop': 'url|mime|extmetadata', 'iiurlwidth': 500,
                'format': 'json', 'formatversion': 2, 'maxlag': 5,
            }), allowed_hosts={'commons.wikimedia.org'}, json_cacheable=lambda value, group=group: _file_pages(value, group) is not None)
            found = _file_pages(data, group)
            if found is None:
                # A valid file in a truncated response can still be credited;
                # never manufacture a negative for any omitted file.
                for filename in group:
                    complete_file = _file_pages(data, [filename])
                    if complete_file is not None:
                        pictures.update(complete_file)
                raise transport.ProviderOutage('Incomplete cached-identity Commons response')
            pictures.update(found)
        except (transport.ProviderOutage, transport.CandidateRejected) as error:
            results = _results(selected, pictures)
            completed = {index: candidates for index, (identity, candidates) in enumerate(zip(selected, results))
                         if identity is None or
                         all(filename in pictures for filename in identity['filenames'])}
            if isinstance(error, transport.CandidateRejected):
                error = transport.ProviderOutage('Commons metadata response could not be verified')
            raise PartialDiscovery(error, completed) from error
    return _results(selected, pictures)


def _results(selected, pictures):
    results = []
    for identity in selected:
        candidates = []
        if identity:
            for filename in identity['filenames']:
                for info in pictures.get(filename, []):
                    metadata = info.get('extmetadata', {})
                    licence = metadata.get('LicenseShortName', {}).get('value', '')
                    source = info.get('descriptionurl', '')
                    if not licence or not source:
                        continue
                    try:
                        transport.validate_external_url(source, {'commons.wikimedia.org'})
                    except transport.CandidateRejected:
                        continue
                    artist = html.unescape(re.sub('<[^>]+>', ' ', metadata.get('Artist', {}).get('value', ''))).strip()
                    for url in dict.fromkeys([info.get('thumburl'), info.get('url')]):
                        if not url:
                            continue
                        try:
                            transport.validate_external_url(url, WIKIMEDIA_IMAGE_HOSTS)
                        except transport.CandidateRejected:
                            continue
                        candidates.append({'provider': 'cached-wikidata-portraits', 'source': source,
                            'image_url': url, 'allowed_image_hosts': list(WIKIMEDIA_IMAGE_HOSTS),
                            'credit': f'Portrait / historical depiction. {artist or "Creator not recorded"} · {licence}.',
                            'rights': licence, 'rights_url': metadata.get('LicenseUrl', {}).get('value', ''),
                            'matched_works': identity['matched_works'], 'author_key': identity['author_key'],
                            'wikidata': identity['wikidata'], 'identity_sources': identity['identity_sources'],
                            'identity_basis': 'cached_reciprocal_library_work_author_and_wikidata',
                            'image_metadata': info})
        results.append(candidates)
    return results


def candidates(item, fetch=None):
    return batch_candidates([item], fetch)[0]
