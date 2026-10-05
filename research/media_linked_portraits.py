"""Resolve portraits through a catalog work's verified author relationships."""
import html
import re
from urllib.parse import quote, urlencode, urlsplit

from research.media_matching import same_title, same_author
from research.media_transport import CandidateRejected, fetch_json, OPENLIBRARY_IMAGE_HOSTS
from research.media_wikimedia import WIKIMEDIA_IMAGE_HOSTS


def author_identities(item):
    """A stored work URL is a hint: recheck its title AND its author name."""
    identities = {}
    names = [item['title'], *item.get('title_aliases', [])]
    consulted = set()
    for work in item.get('linked_works', [])[:3]:
        for url in work.get('source_urls', [])[:2]:
            parts = urlsplit(url)
            if parts.hostname not in {'openlibrary.org', 'www.openlibrary.org'}:
                continue
            match = re.fullmatch(r'/(works/OL\d+W|books/OL\d+M)(?:/[^/]*)?/?', parts.path)
            if not match or match[1] in consulted:
                continue
            consulted.add(match[1])
            try:
                record = fetch_json('https://openlibrary.org/' + match[1] + '.json', allowed_hosts={'openlibrary.org'})
            except CandidateRejected:
                continue
            if not any(same_title(title, record.get('title', ''))[0]
                       for title in [work['title'], *work.get('title_aliases', [])]):
                continue
            authors = record.get('authors', [])
            if not authors and match[1].startswith('books/'):
                for link in record.get('works', [])[:1]:
                    key = link.get('key', '')
                    if not re.fullmatch(r'/works/OL\d+W', key):
                        continue
                    try:
                        linked = fetch_json('https://openlibrary.org' + key + '.json', allowed_hosts={'openlibrary.org'})
                    except CandidateRejected:
                        continue
                    if same_title(record['title'], linked.get('title', ''))[0]:
                        authors = linked.get('authors', [])
            for entry in authors[:6]:
                key = entry.get('author', entry).get('key', '')
                if not re.fullmatch(r'/authors/OL\d+A', key):
                    continue
                try:
                    author = fetch_json('https://openlibrary.org' + key + '.json', allowed_hosts={'openlibrary.org'})
                except CandidateRejected:
                    continue
                if not same_author(names, [author.get('name', ''), *author.get('alternate_names', [])]):
                    continue
                identity = identities.setdefault(key, {'key': key, 'record': author, 'matched_works': []})
                if work['title'] not in identity['matched_works']:
                    identity['matched_works'].append(work['title'])
    return list(identities.values())


def openlibrary_candidates(item):
    identities = author_identities(item)
    # Do not arbitrarily choose between distinct matching author records.
    if len(identities) != 1:
        return []
    identity = identities[0]
    photos = list(dict.fromkeys(value for value in identity['record'].get('photos', []) or []
                                if type(value) is int and value > 0))
    return [{'source': 'https://openlibrary.org' + identity['key'],
             'image_url': f'https://covers.openlibrary.org/a/id/{photo}-L.jpg?default=false',
             'allowed_image_hosts': list(OPENLIBRARY_IMAGE_HOSTS), 'matched_works': identity['matched_works'],
             'author_key': identity['key'].split('/')[-1], 'identity_basis': 'verified_work_author_link',
             'credit': 'Portrait / historical depiction via Open Library. Original photographer and reuse licence require review.'}
            for photo in photos[:8]]


def wikidata_candidates(item):
    identities = author_identities(item)
    if len(identities) != 1:
        return []
    identity = identities[0]
    author = identity['record']
    qid = author.get('remote_ids', {}).get('wikidata', '')
    if not re.fullmatch(r'Q\d+', qid):
        return []
    query = urlencode({'action': 'wbgetentities', 'ids': qid, 'props': 'claims|labels|aliases',
                       'languages': 'en', 'format': 'json', 'maxlag': 5})
    entity = fetch_json('https://www.wikidata.org/w/api.php?' + query,
                        allowed_hosts={'www.wikidata.org'}).get('entities', {}).get(qid, {})
    claims = entity.get('claims', {})
    def values(prop):
        return [row.get('mainsnak', {}).get('datavalue', {}).get('value')
                for row in claims.get(prop, []) if row.get('rank') != 'deprecated']
    if not any(isinstance(value, dict) and value.get('id') == 'Q5' for value in values('P31')):
        return []
    olid = identity['key'].split('/')[-1]
    reciprocal = values('P648')
    labels = [entity.get('labels', {}).get('en', {}).get('value', '')]
    labels += [row.get('value', '') for row in entity.get('aliases', {}).get('en', [])]
    if reciprocal and olid not in reciprocal:
        return []
    if olid not in reciprocal and not same_author([author.get('name', '')], labels):
        return []
    files = list(dict.fromkeys(value for value in values('P18') if isinstance(value, str)))[:3]
    if not files:
        return []
    query = urlencode({'action': 'query', 'titles': '|'.join('File:' + name for name in files),
                       'prop': 'imageinfo', 'iiprop': 'url|extmetadata', 'iiurlwidth': 500,
                       'format': 'json', 'formatversion': 2, 'maxlag': 5})
    pages = fetch_json('https://commons.wikimedia.org/w/api.php?' + query,
                       allowed_hosts={'commons.wikimedia.org'}).get('query', {}).get('pages', [])
    candidates = []
    for page in pages:
        for info in page.get('imageinfo', []):
            metadata = info.get('extmetadata', {})
            licence = metadata.get('LicenseShortName', {}).get('value', '')
            url = info.get('thumburl') or info.get('url')
            if not url or not licence or not info.get('descriptionurl'):
                continue
            artist = html.unescape(re.sub('<[^>]+>', ' ', metadata.get('Artist', {}).get('value', ''))).strip()
            candidates.append({'source': info['descriptionurl'], 'image_url': url,
                'allowed_image_hosts': list(WIKIMEDIA_IMAGE_HOSTS),
                'credit': f'Portrait / historical depiction. {artist[:110]} · {licence[:65]}.',
                'author_key': olid, 'wikidata': qid, 'matched_works': identity['matched_works'],
                'identity_basis': 'verified_work_author_and_wikidata_link', 'image_metadata': info})
    return candidates
