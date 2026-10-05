"""Work-corroborated DBpedia identities and credited Commons portraits.

DBpedia's primary thumbnail is a discovery hint, not proof that an image is a
portrait. Commons metadata and rights are rechecked before returning it.
"""
from __future__ import annotations

import html
import json
import re
from urllib.parse import parse_qs, unquote, urlencode

from research.media_matching import same_author, same_title, words_in_order
from research.media_text_evidence import portrait_work_records
from research.media_transport import CandidateRejected, ProviderOutage, fetch_json, validate_external_url
from research.media_wikimedia import WIKIMEDIA_IMAGE_HOSTS

POLICY_VERSION = 'dbpedia-work-primary-portrait-v1'
MAX_BATCH = 10
MAX_ROWS = 2000
MAX_IMAGES = 3
API_HOSTS = {'dbpedia.org'}
COMMONS_HOSTS = {'commons.wikimedia.org'}
_WORK_SUFFIX = re.compile(r'\s+\((?:book|novel|novella|play|poem|short story|essay|manga|comics|comic book|graphic novel|novel series|book series)\)$', re.I)
_NOT_PORTRAIT = re.compile(
    r'\b(?:blue plaques?|commemorative plaques?|plaques?|graves?|gravestones?|tombstones?|'
    r'cemeter(?:y|ies)|book covers?|cover art|buildings?|houses? of|coats? of arms|'
    r'signatures?|autographs?|group (?:photographs?|portraits?|pictures?)|maps?)\b', re.I)


def _text(value):
    return ' '.join(html.unescape(re.sub(r'<[^>]+>', ' ', str(value or ''))).split())


def _names(item):
    return list(dict.fromkeys(name for name in [item.get('title', ''), *item.get('title_aliases', [])]
                              if isinstance(name, str) and name.strip()))[:3]


def _resource(value):
    try:
        parts = validate_external_url(value, API_HOSTS)
    except (CandidateRejected, TypeError, ValueError):
        return ''
    if not parts.path.startswith('/resource/') or not parts.path[10:] or parts.query or parts.fragment:
        return ''
    return parts._replace(scheme='https').geturl()


def _value(row, key):
    value = row.get(key, {})
    return value.get('value', '') if isinstance(value, dict) else ''


def _query(items, fetch):
    names = sorted(set(name for item in items for name in _names(item)))
    if not names:
        return []
    # JSON quoting is valid SPARQL string quoting, including quotes/backslashes
    # in owner-supplied names. No arbitrary graph syntax is interpolated.
    literals = ' '.join(json.dumps(name, ensure_ascii=False) + '@en' for name in names)
    query = f'''PREFIX dbo: <http://dbpedia.org/ontology/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
SELECT DISTINCT ?person ?name ?image ?workLabel ?philosopher ?wikidata WHERE {{
  VALUES ?name {{ {literals} }}
  ?person a dbo:Person ; rdfs:label ?name .
  OPTIONAL {{ ?person dbo:thumbnail ?image }}
  OPTIONAL {{ ?work a dbo:WrittenWork ; dbo:author ?person ; rdfs:label ?workLabel .
             FILTER(lang(?workLabel) = "en") }}
  BIND(EXISTS {{ ?person a dbo:Philosopher }} AS ?philosopher)
  OPTIONAL {{ ?person owl:sameAs ?wikidata .
             FILTER(STRSTARTS(STR(?wikidata), "http://www.wikidata.org/entity/Q") ||
                    STRSTARTS(STR(?wikidata), "https://www.wikidata.org/entity/Q")) }}
}} LIMIT {MAX_ROWS + 1}'''
    data = fetch('https://dbpedia.org/sparql?' + urlencode({
        'query': query, 'format': 'application/sparql-results+json',
    }), allowed_hosts=API_HOSTS, reject_partial_sparql=True)
    rows = data.get('results', {}).get('bindings') if isinstance(data, dict) else None
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ProviderOutage('DBpedia returned invalid identity results')
    if len(rows) > MAX_ROWS:
        raise ProviderOutage('DBpedia identity query exceeded its complete-result bound')
    return rows


def _identities(item, rows):
    names = _names(item)
    grouped = {}
    for row in rows:
        uri, name = _resource(_value(row, 'person')), _value(row, 'name')
        if not uri or row.get('name', {}).get('xml:lang') != 'en' or not same_author(names, [name]):
            continue
        identity = grouped.setdefault(uri, {'uri': uri, 'names': set(), 'images': set(),
                                           'works': set(), 'qids': set(), 'philosopher': False})
        identity['names'].add(name)
        if _value(row, 'image'):
            identity['images'].add(_value(row, 'image'))
        if row.get('workLabel', {}).get('xml:lang') == 'en':
            identity['works'].add(_value(row, 'workLabel'))
        qid = re.fullmatch(r'https?://www\.wikidata\.org/entity/(Q[1-9]\d*)', _value(row, 'wikidata'))
        if qid:
            identity['qids'].add(qid[1])
        identity['philosopher'] |= _value(row, 'philosopher') in {'true', '1'}
    result = []
    for identity in grouped.values():
        matched = []
        for expected in portrait_work_records(item):
            titles = [expected.get('title', ''), *expected.get('title_aliases', [])]
            if any(same_title(title, _WORK_SUFFIX.sub('', found))[0]
                   for title in titles for found in identity['works']):
                matched.append(expected['title'])
        philosopher = bool(item.get('ranked') and identity['philosopher'])
        if not matched and not philosopher:
            continue
        result.append({'uri': identity['uri'], 'names': sorted(identity['names']),
                       'images': sorted(identity['images'])[:MAX_IMAGES],
                       'wikidata': next(iter(identity['qids'])) if len(identity['qids']) == 1 else '',
                       'matched_works': list(dict.fromkeys(matched)), 'ranked_philosopher': philosopher})
    # Distinct corroborated people must not be silently resolved by row order.
    return result if len(result) == 1 else []


def verified_identities(item, fetch=None):
    """Return zero or one work-corroborated identity, even without a thumbnail."""
    return _identities(item, _query([item], fetch or fetch_json))


def _filename(url):
    try:
        parts = validate_external_url(url, COMMONS_HOSTS)
    except (CandidateRejected, TypeError, ValueError):
        return ''
    prefix = '/wiki/Special:FilePath/'
    if not parts.path.startswith(prefix) or parts.fragment or set(parse_qs(parts.query)) - {'width'}:
        return ''
    filename = unquote(parts.path[len(prefix):]).replace('_', ' ')
    if (len(filename) > 500 or re.search(r'[/|#\x00-\x1f]', filename)
            or not re.search(r'\.(?:jpe?g|png|webp|gif)$', filename, re.I)):
        return ''
    return filename


def _contains_name(text, names):
    tokens = words_in_order(text)
    return any((parts := words_in_order(name)) and any(tokens[i:i + len(parts)] == parts
               for i in range(len(tokens) - len(parts) + 1)) for name in names)


def _portrait(info, filename, identity):
    metadata = info.get('extmetadata', {})
    def field(key):
        return _text(metadata.get(key, {}).get('value'))
    description, categories = field('ImageDescription'), field('Categories')
    if _NOT_PORTRAIT.search(' '.join((filename, description, categories))):
        return False
    if re.search(r'\b(?:group|together with)\b', description, re.I):
        return False
    # Primary thumbnails can depict another person or an unsigned cover. The
    # entire catalog name must recur in the file name or image description.
    if not _contains_name(filename + ' ' + description, identity['names']):
        return False
    for name in identity['names']:
        name_pattern = r'[\W_]+'.join(re.escape(word) for word in words_in_order(name))
        if re.search(name_pattern + r'[\W_]+(?:and|with)[\W_]+', filename + ' ' + description, re.I):
            return False
    licence = field('LicenseShortName')
    return bool(field('Artist') and re.fullmatch(
        r'(?:CC BY(?:-SA)? [1-4]\.0|CC0(?: 1\.0)?|Public domain)', licence, re.I))


def _commons(identities, fetch):
    filenames = sorted(set(name for identity in identities for url in identity['images']
                           if (name := _filename(url))))
    if not filenames:
        return {}
    response = fetch('https://commons.wikimedia.org/w/api.php?' + urlencode({
        'action': 'query', 'titles': '|'.join('File:' + name for name in filenames),
        'redirects': 1, 'prop': 'imageinfo', 'iiprop': 'url|extmetadata', 'iiurlwidth': 500,
        'format': 'json', 'formatversion': 2, 'maxlag': 5,
    }), allowed_hosts=COMMONS_HOSTS)
    if not isinstance(response, dict) or 'error' in response:
        raise ProviderOutage('Commons returned an image metadata error')
    query = response.get('query', {})
    redirects = {row['from'].replace('_', ' '): row['to'].replace('_', ' ')
                 for row in [*query.get('normalized', []), *query.get('redirects', [])]
                 if isinstance(row, dict) and 'from' in row and 'to' in row}
    pages = {page.get('title', '').replace('_', ' '): page for page in query.get('pages', [])}
    result = {}
    for filename in filenames:
        title = 'File:' + filename
        for _ in range(5):
            if title not in redirects:
                break
            title = redirects[title]
        page = pages.get(title, {})
        if not page.get('missing'):
            result[filename] = page.get('imageinfo', [])
    return result


def batch_candidates(items, fetch=None):
    """Resolve up to ten people with one DBpedia and one Commons request.

    Returns lists aligned with the input items. A batch cannot be silently
    truncated; callers can checkpoint each returned list in their usual store.
    """
    if len(items) > MAX_BATCH:
        raise ValueError('DBpedia portrait batches are limited to ten people')
    fetch = fetch or fetch_json
    rows = _query(items, fetch)
    selected = [_identities(item, rows) for item in items]
    images = _commons([identity for group in selected for identity in group], fetch)
    result = []
    for group in selected:
        candidates = []
        for identity in group:
            for filename in dict.fromkeys(_filename(url) for url in identity['images']):
                for info in images.get(filename, []):
                    if not _portrait(info, filename, identity):
                        continue
                    source = info.get('descriptionurl', '')
                    try:
                        validate_external_url(source, COMMONS_HOSTS)
                    except CandidateRejected:
                        continue
                    metadata = info.get('extmetadata', {})
                    artist = _text(metadata.get('Artist', {}).get('value'))
                    licence = _text(metadata.get('LicenseShortName', {}).get('value'))
                    # Both are URLs actually advertised for this exact file.
                    for image_url in dict.fromkeys([info.get('thumburl'), info.get('url')]):
                        if not image_url:
                            continue
                        try:
                            validate_external_url(image_url, WIKIMEDIA_IMAGE_HOSTS)
                        except CandidateRejected:
                            continue
                        candidates.append({
                            'provider': 'dbpedia-portraits', 'source': source, 'image_url': image_url,
                            'allowed_image_hosts': list(WIKIMEDIA_IMAGE_HOSTS),
                            'credit': f'Portrait / historical depiction. {artist[:160]} · {licence}.',
                            'rights': licence, 'rights_url': metadata.get('LicenseUrl', {}).get('value', ''),
                            'identity_basis': 'dbpedia_human_authored_catalog_work' if identity['matched_works']
                                              else 'dbpedia_ranked_philosopher',
                            'identity_url': identity['uri'], 'wikidata': identity['wikidata'],
                            'matched_works': identity['matched_works'],
                            'ranked_philosopher': identity['ranked_philosopher'], 'image_metadata': info,
                        })
        result.append(candidates)
    return result


def candidates(item, fetch=None):
    return batch_candidates([item], fetch)[0]
