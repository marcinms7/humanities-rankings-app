"""Bounded, metadata-only library and publisher image discovery.

The transport enforces provider cooldowns, response caching, public addresses,
redirect hosts and robots rules. These adapters never write catalog records or
download image bodies. A scanned binding/title page is explicitly distinguished
from a modern cover; portrait names need independent identity corroboration.
"""
from __future__ import annotations

import html
import json
import re
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit
from xml.etree import ElementTree

from research.media_matching import match_item_author, match_item_title, norm, same_author, words_in_order
from research.media_transport import CandidateRejected, SECRET_PARAMETERS

LOC_HOSTS = frozenset({'www.loc.gov', 'loc.gov'})
LOC_IMAGE_HOSTS = frozenset({'tile.loc.gov', 'cdn.loc.gov', 'www.loc.gov', 'loc.gov'})
GALLICA_HOSTS = frozenset({'gallica.bnf.fr'})
# Exact hosts, deliberately not substring/suffix matching. Additional publishers
# require an explicit adapter policy, not an arbitrary URL supplied in metadata.
PUBLISHERS = {
    'www.penguinrandomhouse.com': ('Penguin Random House', {'images.penguinrandomhouse.com'}),
    'www.penguin.co.uk': ('Penguin Books', {'cdn.penguin.co.uk', 'images.penguinrandomhouse.com'}),
    'www.faber.co.uk': ('Faber', set()),
    'us.macmillan.com': ('Macmillan', {'images.macmillan.com', 'mpd-biblio-covers.imgix.net'}),
    'www.panmacmillan.com': ('Pan Macmillan', {'images.panmacmillan.com'}),
    'www.bloomsbury.com': ('Bloomsbury', {'media.bloomsbury.com', 'images.bloomsbury.com'}),
    'global.oup.com': ('Oxford University Press', set()),
    'www.cambridge.org': ('Cambridge University Press', {'assets.cambridge.org'}),
    'www.hup.harvard.edu': ('Harvard University Press', {'hup-us.imgix.net'}),
}
PROVIDERS = frozenset({'loc-covers', 'loc-portraits', 'gallica-covers', 'gallica-portraits', 'publisher-covers'})
MAX_RESULTS = 8
MAX_CANDIDATES = 12
MAX_PUBLISHER_PAGES = 4


def _default_fetch(url, *, allowed_hosts, raw=False, respect_robots=False):
    from research.media_transport import fetch_bytes, fetch_json
    method = fetch_bytes if raw else fetch_json
    return method(url, allowed_hosts=allowed_hosts, respect_robots=respect_robots)


def _available(fetch, url, **kwargs):
    try:
        return fetch(url, **kwargs)
    except CandidateRejected:
        # A removed page, malformed individual response or robots-disallowed
        # page does not invalidate other candidate pages. ProviderOutage is
        # deliberately not caught: retry the provider after its cooldown.
        return None


def _strings(value):
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [text for member in value for text in _strings(member)]
    return []


def _text(value):
    if isinstance(value, dict):
        value = value.get('@value', value.get('none', value.get('en', value.get('fr', ''))))
    return html.unescape(re.sub(r'<[^>]+>', ' ', ' '.join(_strings(value)))).strip()


def _url(value, hosts, base=''):
    if not isinstance(value, str):
        return ''
    value = urljoin(base, value.strip())
    try:
        parsed = urlsplit(value)
        valid = parsed.scheme in {'http', 'https'} and parsed.hostname in hosts and not parsed.username and not parsed.password and parsed.port in {None, 80, 443}
    except ValueError:
        return ''
    if not valid:
        return ''
    return parsed._replace(scheme='https', fragment='').geturl()


def _candidate(provider, source, image_url, credit, **metadata):
    return {'provider': provider, 'source': source, 'source_url': source,
            'image_url': image_url, 'credit': credit, **metadata}


def _publisher_page(value, hosts, base=''):
    url = _url(value, hosts, base)
    # Edition URLs and discovered publisher links are untrusted inputs. A
    # credential-bearing URL must never become public image provenance or be
    # interpolated into attribution prose, even before cache sanitization.
    if url and any(key.casefold() in SECRET_PARAMETERS
                   for key, _ in parse_qsl(urlsplit(url).query, keep_blank_values=True)):
        return ''
    return url


def _dedupe(candidates):
    seen = set()
    result = []
    for candidate in candidates:
        if candidate['image_url'] and candidate['image_url'] not in seen:
            seen.add(candidate['image_url'])
            result.append(candidate)
    return result[:MAX_CANDIDATES]


def _bibliographic_title(title):
    # MARC/ISBD responsibility statements are separate from the actual title.
    # Only explicitly marked edition annotations are removed; volume/part
    # designations remain, so a component cannot masquerade as a complete work.
    title = str(title).split(' / ', 1)[0].strip()
    title = re.sub(r'\s*\(?\[(?:[ÉE]dition|[Ii]llustrated edition|[Rr]eprint)[^\]]*\]\)?\s*$', '', title)
    return title.rstrip(' .;:')


def _subject_name(value):
    value = value.split('--', 1)[0].strip(' .[]')
    return re.sub(r'\.?\s*Personne représentée\.?$', '', value, flags=re.I).strip()


def _life_span(heading):
    match = re.search(r'(?<!\d)(\d{3,4})\s*[-–—]\s*(\d{3,4})(?!\d)', heading)
    return match.groups() if match else None


def _portrait_identity(item, subjects, title, descriptions, links=(), authorities=()):
    names = [item['title'], *item.get('title_aliases', [])]
    clean_title = re.sub(r'\s*\[.*?\]\s*', ' ', title).strip(' []')
    clean_title = re.sub(r'^(?:portrait(?: of| de)?|buste de)\s+', '', clean_title, flags=re.I)
    clean_title = re.sub(r'\s*[,;:]\s*(?:portrait|head.*|bust.*|half.length.*)$', '', clean_title, flags=re.I)
    subject_names = [_subject_name(subject) for subject in subjects]
    if not same_author(names, [clean_title, *subject_names]):
        return []
    evidence = []
    # Titles shorter than eight normalized characters are not distinctive
    # enough to corroborate a namesake through free-text metadata.
    hay = words_in_order(' '.join(descriptions))
    for work in item.get('works', item.get('authors', [])):
        work = work.get('title', '') if isinstance(work, dict) else work
        tokens = words_in_order(work)
        if len(norm(work)) >= 8 and any(hay[index:index + len(tokens)] == tokens for index in range(len(hay) - len(tokens) + 1)):
            evidence.append('Catalog work mentioned: ' + work)
    # A reviewed authority URI is useful across catalog providers. Ordinary
    # source_urls are not automatically an identity assertion.
    proven = set(item.get('verified_identity_urls', []))
    for link in links:
        if link in proven:
            evidence.append('Verified authority URI: ' + link)
    birth, death = item.get('birth_year'), item.get('death_year')
    if birth and death:
        dates = re.compile(rf'(?<!\d){re.escape(str(birth))}\s*[-–—]\s*{re.escape(str(death))}(?!\d)')
        if any(dates.search(subject) and same_author(names, [_subject_name(subject)]) for subject in subjects):
            evidence.append(f'Corroborated life dates: {birth}–{death}')
    for authority in authorities:
        for subject in subject_names:
            if (same_author(names, [subject]) and _life_span(subject)
                    and _life_span(subject) == _life_span(authority['heading'])):
                evidence.append(f'Library identity agrees with author of catalog work {authority["work"]}: {authority["heading"]} ({authority["source"]})')
    return evidence


def _loc_authors(record):
    details = record.get('item', {}) if isinstance(record.get('item'), dict) else {}
    authors = _strings(record.get('contributor')) + _strings(details.get('contributor_names'))
    if isinstance(record.get('contributors'), list):
        authors += [key for contributor in record['contributors'] if isinstance(contributor, dict) for key in contributor]
    return authors


def _authorities(item, provider, fetch):
    """Corroborate portrait subject headings against up to two catalog works.

    An identical name alone still does not suffice: the resulting dated author
    heading must also agree with the picture's subject heading before acceptance.
    """
    works = item.get('works', item.get('authors', []))
    matches = []
    for work in works[:2]:
        title = work.get('title', '') if isinstance(work, dict) else work
        if not title:
            continue
        expected = {'title': title, 'authors': [item['title'], *item.get('title_aliases', [])]}
        if provider.startswith('gallica'):
            query = f'dc.title all "{_cql(title)}" and dc.creator all "{_cql(item["title"])}" and dc.type all "monographie"'
            url = 'https://gallica.bnf.fr/SRU?' + urlencode({'version': '1.2', 'operation': 'searchRetrieve', 'query': query, 'maximumRecords': 3})
            raw = _available(fetch, url, allowed_hosts=GALLICA_HOSTS, raw=True)
            if raw is None:
                continue
            documents = _dc_records(raw)
            records = [(next(iter(record.get('title', [])), ''), record.get('creator', []), next(iter(record.get('identifier', [])), '')) for record in documents]
        else:
            url = 'https://www.loc.gov/books/?' + urlencode({'fo': 'json', 'q': title + ' ' + item['title'], 'c': 3})
            documents = _available(fetch, url, allowed_hosts=LOC_HOSTS)
            if not isinstance(documents, dict):
                continue
            records = [(record.get('title', ''), _loc_authors(record), record.get('id', '')) for record in documents.get('results', [])[:3] if isinstance(record, dict)]
        for found_title, authors, source in records:
            if match_item_title(expected, _bibliographic_title(found_title))[0]:
                for heading in authors:
                    if _life_span(heading) and same_author(expected['authors'], [heading]):
                        matches.append({'work': title, 'heading': heading, 'source': source})
        if matches:
            break
    return matches


def loc_candidates(item, provider, fetch):
    portrait = provider == 'loc-portraits'
    endpoint = 'photos' if portrait else 'books'
    query = item['title'] + (' portrait' if portrait else ' ' + ' '.join(item.get('authors', [])[:1]))
    url = f'https://www.loc.gov/{endpoint}/?' + urlencode({'fo': 'json', 'q': query, 'c': MAX_RESULTS, 'fa': 'online-format:image'})
    payload = fetch(url, allowed_hosts=LOC_HOSTS)
    if not isinstance(payload, dict):
        raise ValueError('Library of Congress returned invalid JSON metadata')
    results = []
    authorities = None
    details_fetched = 0
    for record in payload.get('results', [])[:MAX_RESULTS]:
        if not isinstance(record, dict) or record.get('access_restricted'):
            continue
        source = _url(record.get('id', record.get('url', '')), LOC_HOSTS)
        title = str(record.get('title', ''))
        details = record.get('item', {}) if isinstance(record.get('item'), dict) else {}
        authors = _loc_authors(record)
        subjects = _strings(record.get('subject')) + _strings(details.get('subject_headings'))
        descriptions = _strings(record.get('description')) + _strings(details.get('summary')) + _strings(details.get('notes'))
        names = [item['title'], *item.get('title_aliases', [])]
        probable_portrait = portrait and same_author(names, [title.strip('[]'), *[_subject_name(subject) for subject in subjects]])
        needs_details = (probable_portrait and not any(_life_span(subject) for subject in subjects)) or (not portrait and not authors and match_item_title(item, _bibliographic_title(title))[0])
        if source and needs_details and details_fetched < 2:
            details_fetched += 1
            complete = _available(fetch, source.rstrip('/') + '/?fo=json', allowed_hosts=LOC_HOSTS)
            if isinstance(complete, dict) and isinstance(complete.get('item'), dict):
                record = {**record, **complete['item']}
                if record.get('access_restricted'):
                    continue
                title = str(record.get('title', ''))
                details = record.get('item', {}) if isinstance(record.get('item'), dict) else {}
                authors = _loc_authors(record)
                subjects = _strings(record.get('subject')) + _strings(details.get('subject_headings'))
                descriptions = _strings(record.get('description')) + _strings(details.get('summary')) + _strings(details.get('notes'))
        identity = _portrait_identity(item, subjects, title, descriptions, _strings(record.get('aka'))) if portrait else []
        if portrait and not identity and any(_life_span(subject) and same_author([item['title'], *item.get('title_aliases', [])], [_subject_name(subject)]) for subject in subjects):
            if authorities is None:
                authorities = _authorities(item, provider, fetch)
            identity = _portrait_identity(item, subjects, title, descriptions, authorities=authorities)
        if not source or (portrait and not identity):
            continue
        if not portrait and not (match_item_title(item, _bibliographic_title(title))[0] and match_item_author(item, authors)):
            continue
        rights = _text(record.get('rights_access')) or _text(details.get('rights')) or 'See the item-specific rights and access statement.'
        depiction = 'historical_depiction' if portrait else 'digitized_book_preview'
        label = 'Portrait / historical depiction' if portrait else 'Digitized book preview (page type unverified)'
        for raw_image in reversed(_strings(record.get('image_url'))):
            image_url = _url(raw_image, LOC_IMAGE_HOSTS, source)
            # LoC documents that image_url may contain a generic format icon.
            if not image_url or not re.search(r'/(?:service|storage-services|image-services|iiif)/', image_url):
                continue
            results.append(_candidate(provider, source, image_url,
                f'{label}; Library of Congress. {rights} {source}',
                matched_title=title, matched_authors=authors, identity_evidence=identity,
                depiction_kind=depiction, cover_basis=label, rights=rights,
                allowed_image_hosts=sorted(LOC_IMAGE_HOSTS)))
    return _dedupe(results)


def _dc_records(raw):
    if isinstance(raw, str):
        raw = raw.encode('utf8')
    if not isinstance(raw, bytes) or len(raw) > 5_000_000:
        raise ValueError('Invalid or oversized Gallica SRU response')
    # ElementTree does not resolve external entities; explicitly reject DTDs so
    # fixtures or upstream errors cannot supply entity-expansion payloads.
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('DTD/entity declarations are not supported')
    root = ElementTree.fromstring(raw)
    if root.findall('.//{http://www.loc.gov/zing/srw/diagnostic/}diagnostic'):
        raise ValueError('Gallica SRU returned a query diagnostic')
    ns = '{http://purl.org/dc/elements/1.1/}'
    for dc in root.findall('.//{http://www.openarchives.org/OAI/2.0/oai_dc/}dc')[:MAX_RESULTS]:
        values = {}
        for element in dc:
            if element.tag.startswith(ns) and element.text:
                values.setdefault(element.tag.removeprefix(ns), []).append(element.text.strip())
        yield values


def _cql(value):
    return str(value).replace('\\', '\\\\').replace('"', '\\"')[:250]


def _iiif_canvases(manifest):
    if not isinstance(manifest, dict):
        return []
    if isinstance(manifest.get('sequences'), list):
        return [canvas for sequence in manifest['sequences'] if isinstance(sequence, dict)
                for canvas in sequence.get('canvases', []) if isinstance(canvas, dict)]
    return [canvas for canvas in manifest.get('items', []) if isinstance(canvas, dict)]


def _canvas_images(canvas):
    resources = [entry.get('resource', {}) for entry in canvas.get('images', []) if isinstance(entry, dict)]
    for page in canvas.get('items', []):
        if isinstance(page, dict):
            resources += [entry.get('body', {}) for entry in page.get('items', []) if isinstance(entry, dict)]
    for resource in resources:
        if not isinstance(resource, dict):
            continue
        services = resource.get('service', [])
        if isinstance(services, dict):
            services = [services]
        for service in services:
            if not isinstance(service, dict):
                continue
            url = _url(service.get('@id', service.get('id', '')), GALLICA_HOSTS)
            if url and '/iiif/ark:/12148/' in url:
                # Gallica's documented Image API uses native.jpg, not the
                # default.jpg quality parameter common in newer IIIF servers.
                yield url.rstrip('/') + '/full/600,/0/native.jpg'
        direct = _url(resource.get('@id', resource.get('id', '')), GALLICA_HOSTS)
        if direct and re.search(r'/iiif/ark:/12148/[^/]+/f\d+/', direct):
            yield re.sub(r'/full/(?:full|max)/0/', '/full/600,/0/', direct)


def gallica_candidates(item, provider, fetch):
    portrait = provider == 'gallica-portraits'
    if portrait:
        query = f'dc.title all "{_cql(item["title"])}" and dc.type all "image"'
    else:
        authors = item.get('authors', [])
        if not authors:
            return []
        query = f'dc.title all "{_cql(item["title"])}" and dc.creator all "{_cql(authors[0])}" and dc.type all "monographie"'
    url = 'https://gallica.bnf.fr/SRU?' + urlencode({'version': '1.2', 'operation': 'searchRetrieve', 'query': query, 'maximumRecords': MAX_RESULTS})
    raw = fetch(url, allowed_hosts=GALLICA_HOSTS, raw=True)
    results = []
    manifests = 0
    authorities = None
    for record in _dc_records(raw):
        title = next(iter(record.get('title', [])), '')
        authors = record.get('creator', [])
        identity = _portrait_identity(item, record.get('subject', []), title, record.get('description', []), record.get('relation', [])) if portrait else []
        if portrait and not identity and any(_life_span(subject) and same_author([item['title'], *item.get('title_aliases', [])], [_subject_name(subject)]) for subject in record.get('subject', [])):
            if authorities is None:
                authorities = _authorities(item, provider, fetch)
            identity = _portrait_identity(item, record.get('subject', []), title, record.get('description', []), authorities=authorities)
        if portrait and not identity:
            continue
        if not portrait and not (match_item_title(item, _bibliographic_title(title))[0] and match_item_author(item, authors)):
            continue
        source = next((url for value in record.get('identifier', []) if (url := _url(value, GALLICA_HOSTS)) and re.fullmatch(r'/ark:/12148/[a-zA-Z0-9]+', urlsplit(url).path)), '')
        if not source:
            continue
        if manifests >= 2:
            break
        manifests += 1
        manifest_url = source.replace('/ark:/', '/iiif/ark:/') + '/manifest.json'
        manifest = _available(fetch, manifest_url, allowed_hosts=GALLICA_HOSTS)
        if manifest is None:
            continue
        if not isinstance(manifest, dict):
            raise ValueError('Gallica returned an invalid IIIF manifest')
        rights = '; '.join(record.get('rights', []))
        license_url = _text(manifest.get('license', manifest.get('rights', '')))
        rights = '; '.join(filter(None, [rights, license_url])) or 'See Gallica item reuse conditions.'
        canvases = _iiif_canvases(manifest)
        chosen = []
        for canvas in canvases:
            label = _text(canvas.get('label'))
            lowered = norm(label)
            if portrait:
                chosen.append((canvas, 'historical_depiction', 'Portrait / historical depiction'))
                break
            if lowered in {'platsuperieur', 'premierplat', 'frontcover', 'cover', 'couverture'}:
                chosen.append((canvas, 'digitized_binding', 'Digitized historical binding'))
            elif lowered in {'pagedetitre', 'titlepage', 'titre'}:
                chosen.append((canvas, 'title_page', 'Scanned title page'))
        # Never call an arbitrary first scan a cover/title page. In particular,
        # a library calibration chart is not useful illustration for the work.
        for canvas, depiction, label in chosen[:3]:
            for image_url in _canvas_images(canvas):
                credit = f'{label}; {_text(manifest.get("attribution")) or "Bibliothèque nationale de France / Gallica"}. {rights} {source}'
                results.append(_candidate(provider, source, image_url, credit,
                    matched_title=title, matched_authors=authors, identity_evidence=identity,
                    depiction_kind=depiction, cover_basis=label, rights=rights,
                    page_label=_text(canvas.get('label')), manifest_url=manifest_url,
                    allowed_image_hosts=sorted(GALLICA_HOSTS)))
    return _dedupe(results)


class _PublisherHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scripts = []
        self.links = []
        self.active = None

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if tag.casefold() == 'script' and attributes.get('type', '').casefold() == 'application/ld+json':
            self.active = []
        elif tag.casefold() == 'a' and attributes.get('href'):
            self.links.append(attributes['href'])

    def handle_data(self, data):
        if self.active is not None:
            self.active.append(data)

    def handle_endtag(self, tag):
        if tag.casefold() == 'script' and self.active is not None:
            self.scripts.append(''.join(self.active))
            self.active = None


def _books(value, depth=0):
    if depth > 15:
        return
    if isinstance(value, dict):
        types = _strings(value.get('@type'))
        if any(kind.rsplit('/', 1)[-1] == 'Book' for kind in types):
            yield value
        for member in value.values():
            if isinstance(member, (dict, list)):
                yield from _books(member, depth + 1)
    elif isinstance(value, list):
        for member in value[:100]:
            yield from _books(member, depth + 1)


def _isbn(value):
    value = re.sub(r'[^0-9Xx]', '', str(value or '')).upper()
    if len(value) == 10 and all(char.isdigit() for char in value[:9]):
        digits = [int(char) if char.isdigit() else 10 for char in value]
        if sum((10 - index) * digit for index, digit in enumerate(digits)) % 11 == 0:
            stem = '978' + value[:9]
            return stem + str((-sum(int(char) * (1 if index % 2 == 0 else 3) for index, char in enumerate(stem))) % 10)
    if len(value) == 13 and value.isdigit() and value.startswith(('978', '979')):
        if sum(int(char) * (1 if index % 2 == 0 else 3) for index, char in enumerate(value)) % 10 == 0:
            return value
    return ''


def _book_authors(value):
    if isinstance(value, dict):
        return _strings(value.get('name'))
    if isinstance(value, list):
        return [name for member in value for name in _book_authors(member)]
    return _strings(value)


def _book_images(value):
    if isinstance(value, dict):
        return _strings(value.get('contentUrl', value.get('url', value.get('@id', ''))))
    if isinstance(value, list):
        return [url for member in value for url in _book_images(member)]
    return _strings(value)


def _parse_page(raw):
    if isinstance(raw, bytes):
        raw = raw.decode('utf8', 'replace')
    if not isinstance(raw, str) or len(raw) > 5_000_000:
        raise ValueError('Invalid or oversized publisher page')
    parser = _PublisherHTML()
    parser.feed(raw)
    return parser


def publisher_eligible(item):
    """Whether the configured publisher routes can perform any discovery.

    A missing URL/ISBN/publisher hint is an input gap, not a searched source
    that returned no cover. Keep such items out of the provider's attempt log.
    """
    if any(_publisher_page(source, PUBLISHERS) for source in item.get('source_urls', [])):
        return True
    publishers = ' '.join(item.get('publishers', [])).casefold()
    if 'faber' in publishers:
        return True
    return (any(name in publishers for name in ('macmillan', 'farrar', 'henry holt', 'st. martin'))
            and any(_isbn(raw) for raw in item.get('isbns', [])))


def publisher_candidates(item, fetch=None):
    fetch = fetch or _default_fetch
    pages = []
    for source in item.get('source_urls', []):
        checked = _publisher_page(source, PUBLISHERS)
        if checked and checked not in pages:
            pages.append(checked)
    isbns = {isbn for raw in item.get('isbns', []) if (isbn := _isbn(raw))}
    publishers = ' '.join(item.get('publishers', [])).casefold()
    if any(name in publishers for name in ('macmillan', 'farrar', 'henry holt', 'st. martin')):
        pages += ['https://us.macmillan.com/books/' + isbn for isbn in sorted(isbns)[:2]]
    # Search only one configured publisher, only with recorded publisher context,
    # and never attempt a search URL excluded by its current robots rules.
    if not pages and 'faber' in publishers:
        source = 'https://www.faber.co.uk/?' + urlencode({'s': item['title'], 'post_type': 'product'})
        raw = _available(fetch, source, allowed_hosts={'www.faber.co.uk'}, raw=True, respect_robots=True)
        if raw is None:
            return []
        parser = _parse_page(raw)
        for link in parser.links:
            checked = _publisher_page(link, {'www.faber.co.uk'}, source)
            if checked and urlsplit(checked).path.startswith('/product/') and checked not in pages:
                pages.append(checked)
                if len(pages) >= 3:
                    break
    results = []
    for source in pages[:MAX_PUBLISHER_PAGES]:
        host = urlsplit(source).hostname
        raw = _available(fetch, source, allowed_hosts={host}, raw=True, respect_robots=True)
        if raw is None:
            continue
        parser = _parse_page(raw)
        publisher, image_hosts = PUBLISHERS[host]
        allowed_images = {*image_hosts, host}
        for script in parser.scripts:
            try:
                payload = json.loads(script)
            except (ValueError, RecursionError):
                continue
            for book in _books(payload):
                title = _text(book.get('name'))
                authors = _book_authors(book.get('author'))
                if not (match_item_title(item, title)[0] and match_item_author(item, authors)):
                    continue
                found_isbns = {isbn for raw in (book.get('isbn') if isinstance(book.get('isbn'), list) else [book.get('isbn')]) if (isbn := _isbn(raw))}
                # A supplied ISBN constrains edition identity; conflicting or
                # absent publisher ISBNs cannot be silently ignored.
                if isbns and not isbns.intersection(found_isbns):
                    continue
                for raw_image in _book_images(book.get('image')):
                    image_url = _url(raw_image, allowed_images, source)
                    if image_url:
                        rights = 'Publisher cover image; copyright and reuse conditions remain with the rights holder.'
                        results.append(_candidate('publisher-covers', source, image_url,
                            f'Cover image supplied by {publisher}. {rights} {source}',
                            matched_title=title, matched_authors=authors, matched_isbns=sorted(found_isbns),
                            depiction_kind='publisher_cover', cover_basis='Publisher Book metadata', rights=rights,
                            allowed_image_hosts=sorted(allowed_images), image_respect_robots=True))
    return _dedupe(results)


def library_candidates(item, provider, fetch=None):
    fetch = fetch or _default_fetch
    if provider in {'loc-covers', 'loc-portraits'}:
        return loc_candidates(item, provider, fetch)
    if provider in {'gallica-covers', 'gallica-portraits'}:
        return gallica_candidates(item, provider, fetch)
    raise ValueError('Unknown library provider: ' + str(provider))


def candidates(item, provider, fetch=None):
    if provider == 'publisher-covers':
        return publisher_candidates(item, fetch)
    return library_candidates(item, provider, fetch)
