"""Exact work identities from Wolne Lektury's public, bulk book catalogue.

These are the library's generated digital-edition covers, never evidence of a
particular printed edition. The advertised cover artwork credit is retained;
the underlying text's license is not misrepresented as the cover's license.
API documentation: https://wolnelektury.pl/api/
Reuse guidance: https://wolnelektury.pl/info/zasady-wykorzystania/
"""
from __future__ import annotations

import time
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

from research.media_matching import match_item_author, match_item_title, words_in_order
from research.media_transport import (
    CandidateRejected, ProviderOutage, fetch_json, fetch_text,
    response_cache_timestamp, validate_external_url,
)

POLICY_VERSION = 'wolnelektury-lettered-whole-work-v2'
CATALOGUE_URL = 'https://wolnelektury.pl/api/books/'
HOSTS = {'wolnelektury.pl'}
TTL = 86400
_catalogue_cache = None


def _title_key(value):
    words = words_in_order(value)
    return ''.join(words[1:] if words and words[0] in {'a', 'an', 'the'} else words)


def _url(value, prefixes):
    if not isinstance(value, str) or not value:
        raise CandidateRejected('Wolne Lektury URL missing')
    parts = validate_external_url(value, HOSTS)
    if (parts.scheme != 'https' or parts.query or parts.fragment
            or not any(parts.path.startswith(prefix) for prefix in prefixes)):
        raise CandidateRejected('Unexpected Wolne Lektury resource URL')
    return value


def _catalogue_complete(data):
    # An empty or malformed whole-library response is not 7,000+ no-matches.
    # Some valid public records have no credited author; they cannot match.
    return bool(isinstance(data, list) and data and all(
        isinstance(row, dict) and all(isinstance(row.get(key), str) and row[key].strip()
                                     for key in ('title', 'href', 'url', 'slug'))
        and (row.get('author') is None or isinstance(row['author'], str))
        for row in data))


def _index(fetch=None):
    global _catalogue_cache
    fetcher = fetch or fetch_json
    now = time.time()
    if (_catalogue_cache is not None and _catalogue_cache[0] is fetcher
            and now < _catalogue_cache[1]):
        return _catalogue_cache[2]
    data = fetcher(CATALOGUE_URL, provider='wolnelektury-covers', allowed_hosts=HOSTS,
                   cache_ttl=TTL, min_interval=2, json_cacheable=_catalogue_complete)
    if not _catalogue_complete(data):
        raise ProviderOutage('Wolne Lektury catalogue is incomplete')
    index = {}
    for row in data:
        if not row.get('author'):
            continue
        try:
            _url(row['href'], ('/api/books/',))
            _url(row['url'], ('/katalog/lektura/',))
        except CandidateRejected as error:
            raise ProviderOutage('Wolne Lektury catalogue resource is invalid') from error
        index.setdefault(_title_key(row['title']), []).append(row)
    # Derived memory state never extends the age of the persisted API response.
    stamp = response_cache_timestamp(CATALOGUE_URL, allowed_hosts=HOSTS) if fetch is None else None
    _catalogue_cache = (fetcher, min(now, stamp) + TTL if stamp is not None else now + TTL, index)
    return index


def _matching(item, index):
    result, seen = [], set()
    for title in [item['title'], *item.get('title_aliases', [])]:
        for row in index.get(_title_key(title), []):
            if (row['href'] not in seen and match_item_title(item, row['title'])[0]
                    and match_item_author(item, [row['author']])):
                result.append(row)
                seen.add(row['href'])
    return result


def prepare_items(items, *, fetch=None):
    """Filter before queue selection without changing candidate fingerprints.

    Failure propagates before queue attempts are consumed. Cached-download-only
    runs should skip this preparation and use their saved candidate records.
    """
    if not items:
        return []
    index = _index(fetch)
    return [item for item in items if _matching(item, index)]


def _detail_complete(data):
    return bool(isinstance(data, dict)
                and isinstance(data.get('title'), str) and data['title'].strip()
                and isinstance(data.get('url'), str) and data['url']
                and 'parent' in data and (data['parent'] is None or isinstance(data['parent'], dict))
                and type(data.get('preview')) is bool
                and isinstance(data.get('authors'), list)
                and all(isinstance(author, dict) and isinstance(author.get('name'), str)
                        and author['name'].strip() for author in data['authors'])
                and 'cover' in data and isinstance(data['cover'], (str, type(None))))


def _credits(raw, title):
    if (not isinstance(raw, str) or '<!DOCTYPE' in raw.upper() or '<!ENTITY' in raw.upper()):
        raise ProviderOutage('Invalid Wolne Lektury attribution XML')
    try:
        tree = ET.fromstring(raw)
    except ET.ParseError as error:
        raise ProviderOutage('Incomplete Wolne Lektury attribution XML') from error
    description = tree.find('.//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description')
    if description is None:
        raise ProviderOutage('Wolne Lektury attribution metadata missing')
    dc = '{http://purl.org/dc/elements/1.1/}'
    metadata = {node.tag[len(dc):]: ' '.join(''.join(node.itertext()).split())
                for node in description if node.tag.startswith(dc)}
    # Confirm the advertised XML belongs to this digital work before crediting.
    if not match_item_title({'title': title}, metadata.get('title', ''))[0]:
        raise ProviderOutage('Wolne Lektury attribution title does not match')
    return metadata


def candidates(item, *, fetch=None, text_fetch=None):
    fetcher, read_text = fetch or fetch_json, text_fetch or fetch_text
    rows = _matching(item, _index(fetch))
    for row in rows:
        detail = fetcher(row['href'], provider='wolnelektury-covers', allowed_hosts=HOSTS,
                         cache_ttl=TTL, min_interval=2, json_cacheable=_detail_complete)
        if not _detail_complete(detail):
            raise ProviderOutage('Incomplete Wolne Lektury book details')
        # Eponymous stories and nested sections must not stand in for collections.
        if detail['parent'] is not None or detail['preview']:
            continue
        authors = [author['name'] for author in detail['authors']]
        if not match_item_title(item, detail['title'])[0] or not match_item_author(item, authors):
            continue
        source = _url(detail['url'], ('/katalog/lektura/',))
        if urlsplit(source).path.rstrip('/') != urlsplit(row['url']).path.rstrip('/'):
            raise ProviderOutage('Wolne Lektury detail identity changed')
        # `simple_cover` is unlettered source artwork. The API's full `cover`
        # is the actual library jacket with the book title and author.
        image = detail['cover']
        if not image:
            continue
        image = _url(image, ('/media/book/cover/', '/media/book/cover_simple/', '/media/cache/'))
        if not detail.get('xml'):
            raise ProviderOutage('Wolne Lektury attribution source missing')
        xml_url = _url(detail['xml'], ('/media/book/xml/',))
        metadata = _credits(read_text(xml_url, provider='wolnelektury-covers', allowed_hosts=HOSTS,
                                      respect_robots=True, cache_ttl=TTL, min_interval=2), detail['title'])
        artwork = metadata.get('relation.coverImage.attribution', '')
        credit = 'Wolne Lektury digital-edition cover (Książka pochodzi z serwisu Wolne Lektury).'
        credit += f' Artwork: {artwork}.' if artwork else ' Artwork credit: see source.'
        credit += ' Cover-design rights: see source; not established by the text license.'
        # One fully verified digital edition suffices; avoid redundant per-work
        # requests after finding a valid whole-work cover.
        return [{
            'source': source, 'image_url': image, 'credit': credit,
            'matched_title': detail['title'], 'matched_authors': authors,
            'cover_basis': 'representative_work', 'allowed_image_hosts': sorted(HOSTS),
            'image_respect_robots': True,
            'cover_kind': 'library_generated_digital_edition',
            'attribution_source': xml_url, 'artwork_attribution': artwork,
            'text_rights': metadata.get('rights', ''),
            'text_license_url': metadata.get('rights.license', ''),
        }]
    return []
