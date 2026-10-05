"""Credited media providers with durable verified candidates and safe fallbacks."""
from __future__ import annotations
import argparse
import hashlib
import html
import io
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlencode, quote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.enrichment_queue import Queue, exclusive, rotate
from research.operational_state import atomic_state, read_state
from research.media_matching import same_title, same_author, match_item_title, match_item_author, MATCHER_VERSION
from research.media_cover_rejections import reject_reviewed_cover, requires_scope_review
from research.media_transport import CandidateRejected, CandidateStore, ProviderOutage, fetch_json, fetch_bytes, public_candidate, public_text, public_url, OPENLIBRARY_IMAGE_HOSTS
from research.media_wikimedia import WIKIMEDIA_IMAGE_HOSTS, WIKIMEDIA_IMAGE_POLICY
from research.media_image_quality import reject_known_placeholder, needs_cover, replacement_receipt, lookup_due
from PIL import Image

RUN = ROOT / 'research/_runs/media-completion'
PROVIDERS = ['google-covers', 'wikipedia-covers', 'reviewed-covers', 'wolnelektury-covers', 'openlibrary-portraits', 'linked-wikidata-portraits',
             'dbpedia-portraits', 'gnd-portraits', 'rijksmuseum-portraits', 'cached-wikidata-portraits',
             'wellcome-portraits', 'nobel-portraits',
             'loc-covers', 'loc-portraits', 'gallica-covers', 'gallica-portraits', 'publisher-covers']
POLICY = MATCHER_VERSION + ':verified-candidates-v2'


def fetch(url, image=False, **kwargs):
    return (fetch_bytes if image else fetch_json)(url, **kwargs)


def validate_image(blob):
    reject_known_placeholder(blob)
    try:
        with Image.open(io.BytesIO(blob)) as picture:
            if (min(picture.size) < 80 or max(picture.size) / min(picture.size) > 5
                    or picture.width * picture.height > 40_000_000):
                raise CandidateRejected('Image is too small or has an unsuitable aspect ratio')
            extension = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp', 'GIF': 'gif'}.get(picture.format)
            if not extension:
                raise CandidateRejected('Unsupported image format')
            picture.verify()
        # JPEG verify() checks headers only. Decode pixels as well so a broken
        # download cannot mark the catalog as complete with an unusable file.
        with Image.open(io.BytesIO(blob)) as picture:
            picture.load()
    except (OSError, SyntaxError, Image.DecompressionBombError):
        raise CandidateRejected('Invalid raster image') from None
    return extension


def google_candidates(item):
    if not item.get('authors'):
        return []
    queries = ['isbn:' + value for value in item.get('provider_identifiers', {}).get('isbn', [])[:2]]
    queries.extend(f'intitle:"{title}" inauthor:"{item["authors"][0]}"'
                   for title in [item['title'], *item.get('title_aliases', [])][:3])
    candidates, seen = [], set()
    for query in queries[:4]:
        params = {'q': query, 'maxResults': 40, 'printType': 'books'}
        if os.environ.get('GOOGLE_BOOKS_API_KEY'):
            params['key'] = os.environ['GOOGLE_BOOKS_API_KEY']
        data = fetch('https://www.googleapis.com/books/v1/volumes?' + urlencode(params),
                     allowed_hosts={'www.googleapis.com'})
        if 'error' in data:
            raise ProviderOutage('Google Books API error')
        for volume in data.get('items', []):
            info = volume.get('volumeInfo', {})
            if not match_item_title(item, info.get('title', ''))[0] or not match_item_author(item, info.get('authors', [])):
                continue
            images = info.get('imageLinks', {})
            for size in ('extraLarge', 'large', 'medium', 'small', 'thumbnail'):
                url = images.get(size)
                if not url or url in seen or not volume.get('id'):
                    continue
                seen.add(url)
                candidates.append({'source': 'https://books.google.com/books?id=' + quote(volume['id']),
                    'image_url': url.replace('http://', 'https://', 1),
                    'credit': 'Google Books cover; rights remain with the publisher / cover artist.',
                    'matched_title': info['title'], 'matched_authors': info.get('authors', []),
                    'cover_basis': 'representative_work'})
        if candidates:
            break
    return candidates


def wikipedia_candidates(item):
    if not item.get('authors'):
        return []
    titles = list(dict.fromkeys(title + suffix for title in [item['title'], *item.get('title_aliases', [])][:3]
                              for suffix in ('', ' (novel)', ' (book)')))
    params = {'action': 'query', 'format': 'json', 'formatversion': 2, 'titles': '|'.join(titles),
              'redirects': 1, 'prop': 'revisions|info|pageprops', 'rvprop': 'content',
              'rvslots': 'main', 'inprop': 'url', 'maxlag': 5}
    data = fetch('https://en.wikipedia.org/w/api.php?' + urlencode(params), allowed_hosts={'en.wikipedia.org'})
    if 'error' in data:
        raise ProviderOutage('Wikipedia API error')
    candidates = []
    for page in data.get('query', {}).get('pages', []):
        title = re.sub(r' \((?:novel|book)\)$', '', page.get('title', ''))
        if not match_item_title(item, title)[0] or 'disambiguation' in page.get('pageprops', {}):
            continue
        revisions = page.get('revisions', [])
        if not revisions:
            continue
        content = revisions[0].get('slots', {}).get('main', {}).get('content', '')
        if not re.search(r'\{\{Infobox book\b', content, re.I):
            continue
        infobox = re.split(r'\{\{Infobox book\b', content, flags=re.I)[1].split('\n}}', 1)[0]
        def field(key):
            match = re.search(r'^\s*\|\s*' + key + r'\s*=([^\n]*)', infobox, re.M | re.I)
            return match.group(1).strip() if match else ''
        author = re.sub(r'\[\[(?:[^]|]*\|)?([^]]+)\]\]', r'\1', field('author'))
        author = html.unescape(re.sub(r'<[^>]+>', ' ', author)).strip()
        if not match_item_author(item, [author]):
            continue
        caption = field('caption')
        if not re.search(r'\bcover\b|\bfirst edition\b', caption, re.I):
            continue
        filename = re.sub(r'^(?:File|Image):', '', field('image'), flags=re.I)
        if not re.fullmatch(r'[^{}\[\]|<>]+\.(?:jpg|jpeg|png|webp|gif)', filename, re.I):
            continue
        info = fetch('https://en.wikipedia.org/w/api.php?' + urlencode({
            'action': 'query', 'format': 'json', 'formatversion': 2, 'titles': 'File:' + filename,
            'prop': 'imageinfo', 'iiprop': 'url|extmetadata', 'iiurlwidth': 500, 'maxlag': 5}),
            allowed_hosts={'en.wikipedia.org'})
        if 'error' in info:
            raise ProviderOutage('Wikipedia image API error')
        for filepage in info.get('query', {}).get('pages', []):
            for picture in filepage.get('imageinfo', []):
                metadata = picture.get('extmetadata', {})
                licence = metadata.get('LicenseShortName', {}).get('value', '')
                url = picture.get('thumburl') or picture.get('url')
                if not licence or not picture.get('descriptionurl') or not url:
                    continue
                artist = html.unescape(re.sub('<[^>]+>', ' ', metadata.get('Artist', {}).get('value', ''))).strip()
                candidates.append({'source': picture['descriptionurl'], 'article': page.get('fullurl'),
                    'image_url': url, 'matched_title': title, 'matched_author': author,
                    'allowed_image_hosts': list(WIKIMEDIA_IMAGE_HOSTS),
                    'caption': caption, 'metadata': metadata, 'cover_basis': 'representative_work',
                    'credit': f'Wikipedia book cover. {artist[:100]} · {licence[:60]}.'})
    return candidates


def openlibrary_portrait_candidates(item):
    works = item.get('works', item.get('authors', []))
    if not works:
        return []
    if item.get('linked_works'):
        from research.media_linked_portraits import openlibrary_candidates
        linked = openlibrary_candidates(item)
        if linked:
            return linked
    names = [item['title'], *item.get('title_aliases', [])]
    known = []
    for url in item.get('source_urls', []):
        parts = urlsplit(url)
        if parts.hostname in {'openlibrary.org', 'www.openlibrary.org'}:
            match = re.fullmatch(r'/authors/(OL\d+A)(?:/[^/]*)?/?', parts.path)
            if match:
                known.append(match.group(1))
    docs, records = [], {}
    for key in dict.fromkeys(known):
        try:
            record = fetch(f'https://openlibrary.org/authors/{key}.json', allowed_hosts={'openlibrary.org'})
        except CandidateRejected:
            continue
        records[key] = record
        docs.append({**record, 'key': key})
    if not docs:
        data = fetch('https://openlibrary.org/search/authors.json?' + urlencode({'q': item['title'], 'limit': 20}),
                     allowed_hosts={'openlibrary.org'})
        docs = data.get('docs', [])
    matching = [author for author in docs if same_author(names, [author.get('name', '')])]
    if len(matching) > 6:
        return []
    matches = []
    for author in matching:
        key = author.get('key', '').split('/')[-1]
        if not re.fullmatch(r'OL\d+A', key):
            continue
        try:
            record = records.get(key) or fetch(f'https://openlibrary.org/authors/{key}.json',
                                               allowed_hosts={'openlibrary.org'})
        except CandidateRejected:
            continue
        photos = list(dict.fromkeys(photo for photo in record.get('photos', []) or []
                                    if type(photo) is int and photo > 0))
        # The author bibliography cannot yield an image if this author has no
        # usable photo ID. Only pay for work corroboration when a photo exists;
        # no portrait is accepted until that corroboration still succeeds.
        if not photos:
            continue
        from research.media_portrait_bibliography import matched_work_titles
        matched = matched_work_titles(item, [author.get('top_work', '')])
        if not matched:
            try:
                entries = fetch(f'https://openlibrary.org/authors/{key}/works.json?limit=100',
                                allowed_hosts={'openlibrary.org'}).get('entries', [])
            except CandidateRejected:
                continue
            matched = matched_work_titles(item, entries, author_key=key)
        if not matched:
            continue
        matches.append((key, photos, matched))
    if len(matches) != 1:
        return []
    key, photos, matched = matches[0]
    return [{'source': f'https://openlibrary.org/authors/{key}',
             'image_url': f'https://covers.openlibrary.org/a/id/{photo}-L.jpg?default=false',
             'allowed_image_hosts': list(OPENLIBRARY_IMAGE_HOSTS),
             'matched_works': matched, 'author_key': key,
             'credit': 'Portrait / historical depiction via Open Library. Original photographer and reuse licence require review.'}
            for photo in photos[:8]]


def download_candidates(candidates, diagnostics=None, *, item=None, reviewed=False):
    if diagnostics is not None:
        diagnostics['candidate_count'] = min(len(candidates), 16)
        diagnostics['candidate_rejections'] = []
    failed_hosts, outages = set(), []
    for candidate in candidates[:16]:
        candidate = public_candidate(candidate)
        host = (urlsplit(candidate['image_url']).hostname or '').lower().rstrip('.')
        if host in failed_hosts:
            continue
        try:
            blob = fetch(candidate['image_url'], image=True, cache_ttl=30 * 86400,
                         allowed_hosts=candidate.get('allowed_image_hosts'),
                         respect_robots=candidate.get('image_respect_robots', False))
            extension = validate_image(blob)
            if candidate.get('expected_sha256') and hashlib.sha256(blob).hexdigest() != candidate['expected_sha256']:
                raise CandidateRejected('Reviewed image bytes changed; requires another identity review')
            if item is not None:
                reject_reviewed_cover(item, blob, reviewed=reviewed)
        except CandidateRejected as error:
            if diagnostics is not None:
                diagnostics['candidate_rejections'].append(public_text(str(error))[:200])
            continue
        except ProviderOutage as error:
            # Try only another already verified candidate on another advertised
            # host. Do not rewrite a URL, repeat this host, or bypass transport
            # cooldowns (including a redirect to a cooling host).
            failed_hosts.add(host)
            outages.append(error)
            if diagnostics is not None:
                diagnostics.setdefault('candidate_outages', []).append({
                    'host': host, 'retry_after': error.retry_after, **error.state_fields()})
            continue
        return {**candidate, 'blob': blob, 'extension': extension}
    if outages:
        strongest = max(outages, key=lambda error: (
            error.status in {403, 429}, error.outage_type != 'maxlag', error.retry_after))
        raise ProviderOutage(strongest.reason, retry_after=max(error.retry_after for error in outages),
                             status=strongest.status, outage_type=strongest.outage_type)
    return None


def google_cover(item):
    return download_candidates(google_candidates(item), item=item)


def wikipedia_cover(item):
    return download_candidates(wikipedia_candidates(item), item=item)


def openlibrary_portrait(item):
    return download_candidates(openlibrary_portrait_candidates(item))


def provider_candidates(item, provider):
    if provider.endswith('-covers') and provider != 'reviewed-covers' and requires_scope_review(item):
        raise CandidateRejected('Work scope requires a reviewed complete-work cover')
    if provider == 'wolnelektury-covers':
        from research.media_wolnelektury_covers import candidates
        return candidates(item)
    if provider == 'reviewed-covers':
        from research.media_reviewed_covers import candidates
        return candidates(item)
    if provider == 'cached-wikidata-portraits':
        from research.media_cached_wikidata_portraits import candidates
        return candidates(item)
    if provider == 'dbpedia-portraits':
        from research.media_dbpedia_portraits import candidates
        return candidates(item)
    if provider == 'gnd-portraits':
        from research.media_gnd_portraits import candidates
        return candidates(item)
    if provider == 'rijksmuseum-portraits':
        from research.media_rijksmuseum_portraits import candidates
        return candidates(item)
    if provider == 'wellcome-portraits':
        from research.media_wellcome_portraits import candidates
        return candidates(item)
    if provider == 'nobel-portraits':
        from research.media_nobel_portraits import candidates
        return candidates(item)
    if provider == 'linked-wikidata-portraits':
        from research.media_linked_portraits import wikidata_candidates
        return wikidata_candidates(item)
    if provider == 'google-covers':
        return google_candidates(item)
    if provider == 'wikipedia-covers':
        return wikipedia_candidates(item)
    if provider == 'openlibrary-portraits':
        return openlibrary_portrait_candidates(item)
    from research.media_library_sources import candidates
    def adapter(url, *, allowed_hosts, raw=False, respect_robots=False):
        return fetch(url, image=raw, allowed_hosts=allowed_hosts, respect_robots=respect_robots)
    return candidates(item, provider, fetch=adapter)


class ImageProviderOutage(ProviderOutage):
    """Verified candidates are saved; only their image download is deferred."""


def prepare_dbpedia_batch(items):
    """Checkpoint up to ten people using two shared metadata requests.

    Downloads and catalog writes remain per person, so image outages cannot
    lose the other verified identities. Existing candidates, including empty
    results, never trigger repeated discovery within this batch.
    """
    from research.media_dbpedia_portraits import batch_candidates, MAX_BATCH
    store = CandidateStore('dbpedia-portraits', version=provider_policy('dbpedia-portraits'))
    if not items or store.get(items[0]) is not None:
        return
    missing = [item for item in items[:MAX_BATCH] if store.get(item) is None]
    found = batch_candidates(missing)
    if len(found) != len(missing):
        raise ProviderOutage('DBpedia returned an incomplete candidate batch')
    for item, candidates in zip(missing, found):
        store.put(item, candidates)


def prepare_cached_wikidata_batch(items):
    from research.media_cached_wikidata_portraits import batch_candidates, MAX_BATCH, PartialDiscovery
    provider = 'cached-wikidata-portraits'
    store = CandidateStore(provider, version=provider_policy(provider))
    if not items or store.get(items[0]) is not None:
        return
    missing = [item for item in items[:MAX_BATCH] if store.get(item) is None]
    try:
        found = batch_candidates(missing)
    except PartialDiscovery as error:
        # A later request must not discard earlier verified identities/credits.
        # Unfinished indices remain absent, so they cannot become false negatives.
        for index, candidates in error.completed.items():
            store.put(missing[index], candidates)
        raise
    if len(found) != len(missing):
        raise ProviderOutage('Wikidata returned an incomplete cached-identity batch')
    for item, candidates in zip(missing, found):
        store.put(item, candidates)


def _compatible_previous_openlibrary(item, candidates):
    """Reuse strict work/author matches from the immediately preceding policy.

    The old cache key includes this exact catalog identity. The newer policy
    adds structured title forms; it does not invalidate these original exact
    work matches. Recheck stored public fields before migrating positives.
    """
    from research.media_portrait_bibliography import matched_work_titles
    verified = []
    for candidate in candidates or []:
        if not isinstance(candidate, dict):
            continue
        key = candidate.get('author_key')
        if not isinstance(key, str) or not re.fullmatch(r'OL[1-9]\d*A', key):
            continue
        if candidate.get('source') != 'https://openlibrary.org/authors/' + key:
            continue
        image = candidate.get('image_url', '')
        if not isinstance(image, str) or not re.fullmatch(
                r'https://covers\.openlibrary\.org/a/id/[1-9]\d*-L\.jpg\?default=false', image):
            continue
        credit = candidate.get('credit')
        works = candidate.get('matched_works')
        hosts = candidate.get('allowed_image_hosts')
        if (not isinstance(credit, str) or not credit.strip()
                or not isinstance(works, list) or not all(isinstance(title, str) for title in works)
                or not isinstance(hosts, list) or not hosts
                or not all(isinstance(host, str) and host in OPENLIBRARY_IMAGE_HOSTS for host in hosts)
                or not matched_work_titles(item, works)):
            continue
        verified.append(candidate)
    return verified


def stored_candidates(item, provider, *, migrate=False):
    store = CandidateStore(provider, version=provider_policy(provider))
    candidates = store.get(item)
    if candidates is None and provider == 'openlibrary-portraits':
        previous = CandidateStore(provider, version=POLICY + ':archive-storage-v1').get(item)
        compatible = _compatible_previous_openlibrary(item, previous)
        if compatible:
            candidates = store.put(item, compatible) if migrate else compatible
    return candidates


def positive_candidates(items, provider, *, migrate=False):
    """Select verified cached images without network or catalog/queue writes.

    Callers separately enforce queue due times. Copies carry their candidates
    through a cached-only pass so cache expiry cannot trigger new discovery.
    """
    result = []
    for item in items:
        candidates = stored_candidates(item, provider, migrate=migrate)
        if candidates:
            result.append({**item, '_cached_candidates': candidates})
    return result


def prioritize_candidates(items, provider, queue, *, cached_only=False, positive=None):
    """Put due verified images ahead of fresh identities before batch limits."""
    if positive is None:
        positive = positive_candidates(items, provider, migrate=True)
    due_ids = {item['id'] for item in items}
    positive = [item for item in positive if item['id'] in due_ids]
    positive.sort(key=queue.priority)
    if cached_only:
        return positive
    cached_ids = {item['id'] for item in positive}
    return positive + sorted((item for item in items if item['id'] not in cached_ids), key=queue.priority)


def cached_retry_state(queue, positive):
    """Report pending verified images independently of metadata queue waits."""
    from research.enrichment_queue import MAX_ATTEMPTS
    retries = []
    now = time.time()
    for identity in dict.fromkeys(item['id'] for item in positive):
        row = queue.db.execute('SELECT state,next_retry,attempts FROM attempts WHERE work_id=?',
                               (identity,)).fetchone()
        if not row or row[0] not in {'pending', 'provider_wait', 'retryable'}:
            continue
        if row[0] == 'retryable' and row[2] >= MAX_ATTEMPTS:
            continue
        retries.append(now if row[0] == 'pending' else max(now, row[1] or 0))
    return {'cached_waiting': len(retries), 'cached_next_retry': min(retries, default=None)}


def cached_match(item, provider, diagnostics=None, *, cached_only=False):
    is_cover = provider.endswith('-covers')
    if is_cover and provider != 'reviewed-covers' and requires_scope_review(item):
        raise CandidateRejected('Work scope requires a reviewed complete-work cover')
    candidates = item.get('_cached_candidates')
    if candidates is None:
        candidates = stored_candidates(item, provider, migrate=True)
    if candidates is None:
        if cached_only:
            return None
        candidates = provider_candidates(item, provider)
        candidates = CandidateStore(provider, version=provider_policy(provider)).put(item, candidates)
    try:
        return download_candidates(candidates, diagnostics=diagnostics, item=item if is_cover else None,
                                   reviewed=provider == 'reviewed-covers')
    except ProviderOutage as error:
        raise ImageProviderOutage(error.reason, retry_after=error.retry_after,
                                  status=error.status, outage_type=error.outage_type) from error


def provider_policy(provider):
    suffix = ':archive-storage-v1' if provider == 'openlibrary-portraits' else ''
    if provider == 'wolnelektury-covers':
        from research.media_wolnelektury_covers import POLICY_VERSION
        suffix += ':' + POLICY_VERSION
    if provider == 'reviewed-covers':
        from research.media_reviewed_covers import POLICY_VERSION
        suffix += ':' + POLICY_VERSION
    if provider == 'openlibrary-portraits':
        from research.media_portrait_bibliography import POLICY_VERSION
        suffix += ':' + POLICY_VERSION
    if provider == 'cached-wikidata-portraits':
        from research.media_cached_wikidata_portraits import POLICY_VERSION
        suffix += ':' + POLICY_VERSION + ':' + WIKIMEDIA_IMAGE_POLICY
    if provider in {'linked-wikidata-portraits', 'wikipedia-covers'}:
        suffix += ':' + WIKIMEDIA_IMAGE_POLICY
    if provider in {'dbpedia-portraits', 'gnd-portraits', 'rijksmuseum-portraits'}:
        suffix += ':authority-portraits-v1'
    return POLICY + suffix


def image_credit(match):
    """Keep a clickable provenance URL even when the detailed rights are long."""
    source = public_url(match.get('source', match.get('source_url', '')))
    credit = public_text(match['credit']).replace(source, '').strip(' .;') if source else public_text(match['credit']).strip()
    if source and len(source) < 450:
        return credit[:max(0, 499 - len(source))].rstrip(' .;') + ' ' + source
    return credit[:500]


def save_match(kind, item, match):
    extension = validate_image(match['blob'])
    if kind.endswith('-covers'):
        reject_reviewed_cover(item, match['blob'], reviewed=kind in {'reviewed-covers', 'catalog-covers'})
    from django.core.files.base import ContentFile
    from django.db import transaction
    from backend.core.models import Work, Edition, Person
    with transaction.atomic():
        if kind.endswith('-covers'):
            work = Work.objects.select_for_update().get(pk=item['id'])
            if (work.is_archived or work.title != item.get('display_title', item['title'])
                    or sorted(work.authors.values_list('name', flat=True)) != sorted(item['authors'])
                    or ('edition_id' in item and work.default_edition_id != item['edition_id'])):
                return 'identity_review_changed_during_lookup'
            edition = Edition.objects.select_for_update().get(pk=work.default_edition_id) if work.default_edition_id else None
            replaced = replacement_receipt(edition, item) if edition and edition.cover else None
            if edition and edition.cover and not replaced:
                return 'preserved_existing'
            if edition and (edition.is_archived or edition.work_id != work.pk):
                return 'identity_review_archived_edition'
            if edition is None:
                edition = Edition.objects.create(work=work, language='Not verified',
                    translation_notes='Representative work image; exact edition and language require verification.')
                work.default_edition = edition
                work.save(update_fields=['default_edition', 'updated_at'])
            filename = f'{kind}-{item["id"]}.{extension}'
            if replaced:
                from uuid import uuid4
                filename = f'placeholder-replacement-{uuid4().hex}-{filename}'
            edition.cover.save(filename, ContentFile(match['blob']), save=False)
            edition.cover_source_url = public_url(match.get('source', match.get('source_url', '')))
            edition.cover_basis = ('unknown' if kind == 'catalog-covers' and match.get('cover_basis') == 'unknown'
                                   else 'representative_work')
            edition.image_attribution = image_credit(match)
            edition.save(update_fields=['cover', 'cover_source_url', 'cover_basis', 'image_attribution', 'updated_at'])
            if replaced:
                match['replaced_placeholder'] = replaced
        else:
            person = Person.objects.select_for_update().get(pk=item['id'])
            current_works = sorted(person.works.filter(is_archived=False).values_list('title', flat=True))
            if person.is_archived or person.name != item['title'] or current_works != sorted(item.get('works', item['authors'])):
                return 'identity_review_changed_during_lookup'
            if match.get('ranked_philosopher') and not match.get('matched_works'):
                if not person.rankingentry_set.filter(is_archived=False, ranking__is_archived=False,
                                                       ranking__owner__isnull=True).exists():
                    return 'identity_review_changed_during_lookup'
            if person.portrait:
                return 'preserved_existing'
            person.portrait.save(f'{kind}-{item["id"]}.{extension}', ContentFile(match['blob']), save=False)
            person.image_attribution = image_credit(match)
            person.save(update_fields=['portrait', 'image_attribution', 'updated_at'])
    return 'covered'


def portrait_lookup_item(person, aliases=None, include_links=False):
    aliases = aliases or {}
    works = [work.title for work in person.works.all() if not work.is_archived]
    item = {'id': person.pk, 'title': person.name, 'authors': works, 'works': works,
            'title_aliases': aliases.get('people', {}).get(str(person.pk), []),
            'source_urls': [person.source_url] if person.source_url else [],
            'biography': person.biography, 'ranked': bool(getattr(person, 'ranked', False)),
            'priority': getattr(person, 'shared_priority', getattr(person, 'ranked', 0))}
    work_aliases = {}
    for work in person.works.all():
        variants = aliases.get('works', {}).get(str(work.pk), [])
        if not work.is_archived and variants:
            work_aliases[work.title] = list(dict.fromkeys([*work_aliases.get(work.title, []), *variants]))
    if work_aliases:
        item['work_aliases'] = work_aliases
    if include_links:
        links = []
        for work in person.works.all():
            edition = work.default_edition
            if work.is_archived or not edition or edition.is_archived:
                continue
            urls = list(dict.fromkeys(url for url in [edition.cover_source_url, edition.source_url]
                                     if url and urlsplit(url).hostname in {'openlibrary.org', 'www.openlibrary.org'}))
            if urls:
                links.append({'title': work.title, 'title_aliases': aliases.get('works', {}).get(str(work.pk), []),
                              'source_urls': urls})
        item['linked_works'] = links
    return item


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('provider', choices=PROVIDERS)
    parser.add_argument('--limit', type=int, default=25)
    parser.add_argument('--max-seconds', type=int, default=0,
                        help='Yield after finishing the current record when this soft time budget expires; 0 disables it.')
    parser.add_argument('--person-id', type=int, help='Limit a portrait validation batch to one catalog person.')
    parser.add_argument('--work-id', type=int, help='Limit a cover validation batch to one catalog work.')
    parser.add_argument('--cached-only', action='store_true',
                        help='Download due verified cached images only; never discover new candidates.')
    args = parser.parse_args()
    if args.max_seconds < 0:
        parser.error('--max-seconds must be zero or positive.')
    if args.person_id and args.provider.endswith('-covers'):
        parser.error('--person-id applies only to portrait providers.')
    if args.work_id and not args.provider.endswith('-covers'):
        parser.error('--work-id applies only to cover providers.')
    RUN.mkdir(parents=True, exist_ok=True)
    stats_path = RUN / f'{args.provider}{"-cached" if args.cached_only else ""}-stats.json'
    cooldown = RUN / f'{args.provider}-cooldown.json'
    stats = {'processed': 0, 'covered': 0, 'provider_errors': 0, 'image_deferred': 0}
    if args.cached_only:
        stats['cached_only'] = True
    if (not args.cached_only and args.provider == 'google-covers'
            and not os.environ.get('GOOGLE_BOOKS_API_KEY', '').strip()):
        atomic_state(stats_path, {**stats, 'provider_status': 'credential_required',
                     'reason': 'GOOGLE_BOOKS_API_KEY is required; no requests were sent.'})
        return
    saved_cooldown = read_state(cooldown, cooldown=True)
    if not args.cached_only and saved_cooldown.get('until', 0) > time.time():
        atomic_state(stats_path, {**stats, 'provider_outage': True, 'retry_after': saved_cooldown['until'],
            **{key: saved_cooldown[key] for key in ('reason', 'outage_type', 'http_status') if key in saved_cooldown}})
        return
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.config.settings')
    import django
    django.setup()
    from django.db.models import Count, Prefetch, Q
    from backend.core.models import Work, Person, Edition
    from backend.core.search import aliases
    from research.enrich_catalog_covers_public import cover_lookup_item
    known_aliases = aliases()
    ledger = RUN / f'{args.provider}.jsonl'
    queue = Queue(args.provider, ledger)
    rotate(ledger)
    if args.provider.endswith('-covers'):
        records = Work.objects.filter(is_archived=False).select_related('default_edition').prefetch_related(
            'authors', Prefetch('editions', queryset=Edition.objects.filter(is_archived=False), to_attr='media_editions'))
        records = records.annotate(shared_priority=Count('rankingentry', filter=Q(
            rankingentry__is_archived=False, rankingentry__ranking__is_archived=False,
            rankingentry__ranking__owner__isnull=True), distinct=True)).order_by('-shared_priority', 'pk')
        if args.work_id:
            records = records.filter(pk=args.work_id)
        items = [cover_lookup_item(work, known_aliases) for work in records
                 if needs_cover(work)]
    else:
        records = Person.objects.filter(is_archived=False, portrait='').prefetch_related(
            Prefetch('works', queryset=Work.objects.select_related('default_edition'))).annotate(
            ranked=Count('rankingentry', filter=Q(rankingentry__is_archived=False,
                rankingentry__ranking__is_archived=False, rankingentry__ranking__owner__isnull=True), distinct=True))
        if args.person_id:
            records = records.filter(pk=args.person_id)
        items = [portrait_lookup_item(person, known_aliases,
                 include_links=args.provider in {'openlibrary-portraits', 'linked-wikidata-portraits'})
                 for person in records.order_by('-ranked', 'pk')]
    if args.provider == 'cached-wikidata-portraits':
        from research.media_cached_wikidata_portraits import cached_identity
        linked = []
        for item in items:
            identity = cached_identity(item)
            if identity:
                item['verified_identity_urls'] = [*identity['identity_sources'],
                    'https://www.wikidata.org/entity/' + identity['wikidata']]
                linked.append(item)
        # Missing cache evidence is pending discovery, never a terminal miss.
        items = linked
    if args.provider == 'reviewed-covers':
        from research.media_reviewed_covers import prepare_items
        items = prepare_items(items)
    if args.provider == 'wolnelektury-covers' and not args.cached_only:
        from research.media_wolnelektury_covers import prepare_items
        try:
            applicable = prepare_items(items)
        except ProviderOutage as error:
            # Bulk discovery has not completed: consume no book attempts and
            # leave previously checkpointed images for the cached-only pass.
            atomic_state(cooldown, {'until': error.retry_after, **error.state_fields()})
            atomic_state(stats_path, {**stats, 'queued': 0, 'provider_outage': True,
                'provider_errors': 1, 'retry_after': error.retry_after, **error.state_fields()})
            queue.close()
            return
        stats['not_applicable'] = len(items) - len(applicable)
        items = applicable
    if args.provider == 'publisher-covers':
        from research.media_library_sources import publisher_eligible
        applicable = [item for item in items if publisher_eligible(item)]
        stats['not_applicable'] = len(items) - len(applicable)
        items = applicable
        if not items:
            stats['provider_reason'] = 'No catalog item has an eligible publisher source URL.'
    positive = positive_candidates(items, args.provider, migrate=True)
    items = [item for item in items if lookup_due(queue, item, provider_policy(args.provider))]
    items = prioritize_candidates(items, args.provider, queue, cached_only=args.cached_only, positive=positive)
    if args.limit:
        items = items[:args.limit]
    stats['queued'] = len(items)
    started = time.monotonic()
    with ledger.open('a') as audit:
        for index, item in enumerate(items):
            if args.max_seconds and stats['processed'] and time.monotonic() - started >= args.max_seconds:
                stats['yielded_for_time_budget'] = True
                break
            result = {'work_id': item['id'], 'title': item['title'], 'provider': args.provider}
            diagnostics = {}
            metadata_outage = None
            try:
                if args.provider == 'dbpedia-portraits' and not args.cached_only:
                    prepare_dbpedia_batch(items[index:index + 10])
                if args.provider == 'cached-wikidata-portraits' and not args.cached_only:
                    from research.media_cached_wikidata_portraits import PartialDiscovery
                    batch = items[index:index + 50]
                    try:
                        prepare_cached_wikidata_batch(batch)
                    except PartialDiscovery as error:
                        metadata_outage = error
                        positive.extend(positive_candidates(batch, args.provider))
                        # An already completed first person can download now.
                        # Do not attach a metadata retry deadline to their image.
                        if stored_candidates(item, args.provider) is None:
                            raise
                match = cached_match(item, args.provider, diagnostics=diagnostics, cached_only=args.cached_only)
                result['status'] = save_match(args.provider, item, match) if match else 'no_safe_match'
                if match:
                    result.update({key: value for key, value in match.items() if key != 'blob'})
                stats['covered'] += result['status'] == 'covered'
            except ImageProviderOutage as error:
                # The metadata lookup and candidate checkpoint succeeded.
                # Defer only this record, leaving other metadata/image hosts
                # usable. Transport still enforces every saved host cooldown.
                result.update(status='image_deferred', provider_outage=True,
                              error=error.reason, retry_after=error.retry_after,
                              outage_stage='image', **error.state_fields())
                stats['image_deferred'] += 1
                positive.append(item)
            except ProviderOutage as error:
                result.update(status='provider_deferred', provider_outage=True,
                              error=error.reason, retry_after=error.retry_after, **error.state_fields())
                metadata_outage = error
            except CandidateRejected as error:
                result.update(status='no_safe_match', reason=str(error))
            except Exception as error:
                result.update(status='provider_error', error=type(error).__name__)
            if metadata_outage is not None:
                atomic_state(cooldown, {'until': metadata_outage.retry_after, **metadata_outage.state_fields()})
                stats.update(provider_outage=True, retry_after=metadata_outage.retry_after, provider_errors=1,
                             **metadata_outage.state_fields())
            result.update(diagnostics)
            queue.finish(item, result, audit)
            stats['processed'] += 1
            metadata_errors = max(0, queue.batch_errors - stats['image_deferred'])
            stats['provider_errors'] = max(stats['provider_errors'], metadata_errors)
            print(json.dumps({key: result[key] for key in ('work_id', 'title', 'status', 'provider')}, ensure_ascii=False), flush=True)
            stats.update(cached_retry_state(queue, positive))
            atomic_state(stats_path, {**stats, **queue.summary()})
            if stats.get('retry_after') or metadata_errors >= 3:
                break
    stats.update(queue.summary())
    stats.update(cached_retry_state(queue, positive))
    if args.provider == 'cached-wikidata-portraits' and not args.cached_only and not stats['processed']:
        # Other providers keep adding public identity evidence to the cache.
        # An empty subset today does not exhaust this source.
        stats['next_retry'] = min(stats.get('next_retry') or float('inf'), time.time() + 300)
    stats['elapsed_seconds'] = round(time.monotonic() - started, 2)
    queue.close()
    atomic_state(stats_path, stats)


if __name__ == '__main__':
    with exclusive('media-alternatives'):
        main()
