"""Bounded discovery of Nobel-owned, credited literature laureate portraits.

The public laureate API supplies the identity and official page URL. A catalog
work must also appear in that person's own facts/bibliography. Only modern
portraits explicitly credited to a Nobel copyright holder are eligible: the
site does not extend permission for most older/third-party photographs.
"""
from html.parser import HTMLParser
from functools import lru_cache
import re
from urllib.parse import urlsplit

from research.media_matching import norm, words_in_order
from research.media_transport import CandidateRejected, fetch_bytes, fetch_json

PROVIDER = 'nobel-portraits'
API_URL = 'https://api.nobelprize.org/2.1/laureates?nobelPrizeCategory=lit&limit=1000'
PAGE_HOSTS = frozenset({'www.nobelprize.org'})
RIGHTS_URL = 'https://www.nobelprize.org/about/copyright-information/#portraits'
RIGHTS = 'Nobel-owned portrait: credited editorial/educational noncommercial use; not an open licence.'
_VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}


class _Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def has_class(self, value):
        return value in self.attrs.get('class', '').split()

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, _Node):
                yield from child.walk()

    def text(self):
        if self.tag in {'script', 'style', 'nav', 'aside'}:
            return ''
        return ' '.join(child.text() if isinstance(child, _Node) else child for child in self.children)


class _Page(HTMLParser):
    def __init__(self, raw):
        super().__init__(convert_charrefs=True)
        self.root = _Node()
        self.stack = [self.root]
        if isinstance(raw, bytes):
            raw = raw.decode('utf8', 'replace')
        if not isinstance(raw, str) or len(raw) > 2_000_000:
            raise ValueError('Invalid or oversized Nobel page')
        self.feed(raw)

    def handle_starttag(self, tag, attrs):
        if len(self.stack) > 100:
            raise ValueError('Nobel page nesting exceeds limit')
        node = _Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def _fetch(url, *, raw=False, allowed_hosts, respect_robots=False):
    return (fetch_bytes if raw else fetch_json)(url, allowed_hosts=allowed_hosts,
                                               respect_robots=respect_robots)


def _url(value, pattern):
    if not isinstance(value, str):
        return ''
    try:
        parts = urlsplit(value)
        if (parts.scheme != 'https' or parts.hostname not in PAGE_HOSTS or parts.port not in {None, 443}
                or parts.username or parts.password or parts.query or parts.fragment
                or not re.fullmatch(pattern, parts.path)):
            return ''
    except ValueError:
        return ''
    return value


def _works(item, text):
    tokens = words_in_order(text)
    found = []
    for work in item.get('works', item.get('authors', []))[:30]:
        title = work.get('title', '') if isinstance(work, dict) else work
        wanted = words_in_order(title)
        if len(norm(title)) >= 8 and wanted and any(tokens[i:i + len(wanted)] == wanted
                                                    for i in range(len(tokens) - len(wanted) + 1)):
            found.append(title)
    return found


def _laureate_index(fetch):
    payload = fetch(API_URL, allowed_hosts={'api.nobelprize.org'})
    if not isinstance(payload, dict) or not isinstance(payload.get('laureates'), list):
        raise ValueError('Invalid Nobel laureate response')
    index = {}
    for record in payload['laureates'][:1000]:
        if not isinstance(record, dict) or record.get('gender') not in {'male', 'female'}:
            continue
        labels = {norm(record.get(field, {}).get('en', '')) for field in ('knownName', 'fullName')}
        for label in labels - {''}:
            index.setdefault(label, []).append(record)
    return index


@lru_cache(maxsize=1)
def _default_index():
    # A batch may inspect hundreds of non-laureates. Parse/index the cached
    # bulk response only once per worker process, not once for every person.
    return _laureate_index(_fetch)


def candidates(item, fetch=None):
    """Return zero/one image; no database writes or image downloads."""
    supplied_fetch = fetch
    fetch = fetch or _fetch
    names = {norm(name) for name in [item['title'], *item.get('title_aliases', [])] if len(norm(name)) >= 6}
    if not names:
        return []
    index = _laureate_index(fetch) if supplied_fetch else _default_index()
    matches = []
    for name in names:
        for record in index.get(name, []):
            if record not in matches:
                matches.append(record)
    if len(matches) != 1 or not re.fullmatch(r'\d+', str(matches[0].get('id', ''))):
        return []
    record = matches[0]
    source = ''
    for prize in record.get('nobelPrizes', [])[:3]:
        year = str(prize.get('awardYear', ''))
        if not re.fullmatch(r'\d{4}', year) or int(year) < 2007:
            continue
        for link in prize.get('links', []):
            source = _url(link.get('href'), rf'/prizes/literature/{year}/[a-z0-9-]+/facts/')
            if source:
                break
        if source:
            break
    if not source:
        return []
    try:
        page = _Page(fetch(source, raw=True, allowed_hosts=PAGE_HOSTS, respect_robots=True))
    except CandidateRejected:
        return []
    sections = [node for node in page.root.walk() if node.tag == 'section'
                and node.has_class('laureate-facts') and node.has_class('laur-' + str(record['id']))]
    if len(sections) != 1:
        return []
    section = sections[0]
    if not any(node.tag == 'h1' and norm(node.text()) in names for node in section.walk()):
        return []
    images = []
    for block in section.walk():
        if block.tag != 'div' or not block.has_class('image'):
            continue
        credits = [' '.join(node.text().split()) for node in block.walk()
                   if node.has_class('figcaption__attribution')]
        credit = ' '.join(credits)
        if not re.search(r'©\s*(?:The\s+)?Nobel (?:Foundation|Prize Outreach)\b', credit):
            continue
        if not any(node.tag == 'img' and norm(node.attrs.get('alt', '')) in names for node in block.walk()):
            continue
        for node in block.walk():
            if node.tag == 'img' and norm(node.attrs.get('alt', '')) in names:
                image = _url(node.attrs.get('src'), r'/images/[a-zA-Z0-9_-]+-portrait-medium\.(?:jpg|png|webp)')
                if image:
                    images.append((image, credit))
    images = list(dict.fromkeys(images))
    if len(images) != 1:
        return []
    own_text = ' '.join(node.text() for node in section.walk()
                        if node.tag == 'article' and node.has_class('page-content'))
    matched = _works(item, own_text)
    evidence_source = source
    if not matched:
        # One linked, same-person bibliography only. Never follow another
        # laureate or a generic page, and never use related-content snippets.
        bibliography = source.removesuffix('facts/') + 'bibliography/'
        if any(node.tag == 'a' and node.attrs.get('href') == bibliography for node in section.walk()):
            try:
                extra = _Page(fetch(bibliography, raw=True, allowed_hosts=PAGE_HOSTS, respect_robots=True))
            except CandidateRejected:
                return []
            main = next((node for node in extra.root.walk() if node.tag == 'main'), None)
            if main and any(node.tag == 'h1' and norm(node.text()) in names for node in main.walk()):
                text = ' '.join(node.text() for node in main.walk()
                                if node.tag == 'article' and node.has_class('page-content'))
                matched = _works(item, text)
                evidence_source = bibliography
    if not matched:
        return []
    image, credit = images[0]
    return [{'provider': PROVIDER, 'source': source, 'source_url': source,
             'image_url': image, 'allowed_image_hosts': sorted(PAGE_HOSTS), 'image_respect_robots': True,
             'credit': credit + ' · NobelPrize.org · Editorial/educational noncommercial use.',
             'rights': RIGHTS, 'rights_url': RIGHTS_URL, 'depiction_kind': 'portrait',
             'matched_works': matched, 'nobel_id': str(record['id']),
             'identity_basis': 'nobel_laureate_and_catalog_work',
             'identity_evidence': [f'Catalog work: {title} ({evidence_source})' for title in matched]}]
