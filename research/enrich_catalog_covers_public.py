"""Resumable public-API cover enrichment for the shared catalogue.

Order of evidence: Open Library's work search/Covers API, then Internet
Archive's public advanced-search/image service.  A cover is accepted only when
the submitted work title and one credited author agree after normalisation.
This creates an explicitly unverified display edition only where a work has none; it
does not infer ISBNs, publishers, page counts, translators, or release dates.
Every outcome is appended before the next item so it can be resumed safely.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from urllib.parse import urlencode, quote, urlsplit
from PIL import Image
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from research.enrichment_queue import Queue, exclusive, rotate, records
from research.media_matching import (MATCHER_VERSION, norm, words, words_in_order,
                                    same_title, same_author, match_item_title, match_item_author)
from research.media_transport import CandidateRejected, ProviderOutage, fetch_json, fetch_bytes
from research.media_cover_rejections import reject_reviewed_cover, requires_scope_review
from research.media_image_quality import (reject_known_placeholder, placeholder_reference,
                                         needs_cover, replacement_receipt, lookup_due)
from research.operational_state import atomic_state
RUN = ROOT / "research" / "_runs" / "2026-09-13" / "catalog-public-cover-fallback"
CACHE = RUN / "outcomes.jsonl"
MAX_IMAGE_CANDIDATES = 6
_OL_KEY = re.compile(r"/(works/OL[0-9]+W|books/OL[0-9]+M)")


def read_json(url: str, params: dict, timeout: int = 15) -> dict:
    provider = 'internet_archive' if urlsplit(url).hostname == 'archive.org' else 'openlibrary'
    return fetch_json(url + ('?' + urlencode(params, doseq=True) if params else ''),
                      provider=provider, timeout=timeout)


def read_image(url: str) -> bytes:
    provider = 'internet_archive' if urlsplit(url).hostname == 'archive.org' else 'openlibrary'
    data = fetch_bytes(url, provider=provider, timeout=20)
    reject_known_placeholder(data)
    try:
        with Image.open(io.BytesIO(data)) as picture:
            if picture.format not in {'JPEG', 'PNG', 'WEBP'}:
                raise ValueError('Unsupported cover image format.')
            if (min(picture.size) < 80 or max(picture.size) / min(picture.size) > 5
                    or picture.width * picture.height > 40_000_000):
                raise ValueError('Cover image has unsuitable dimensions.')
            picture.verify()
        # JPEG verify checks the container, but can accept truncated pixels.
        with Image.open(io.BytesIO(data)) as picture:
            picture.load()
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as error:
        raise CandidateRejected('Invalid cover image') from error
    return data


def valid_isbn(value: str) -> str:
    value = re.sub(r'[\s-]', '', str(value or '')).upper()
    if re.fullmatch(r'[0-9]{9}[0-9X]', value):
        return value if sum((10 - i) * (10 if char == 'X' else int(char))
                            for i, char in enumerate(value)) % 11 == 0 else ''
    if re.fullmatch(r'(?:978|979)[0-9]{10}', value):
        return value if sum(int(char) * (1 if i % 2 == 0 else 3)
                            for i, char in enumerate(value)) % 10 == 0 else ''
    return ''


def _openlibrary_key(value: str) -> str | None:
    # Remote IDs are discovery hints. The title and author are revalidated
    # against API metadata even when the ID came from an existing edition.
    parsed = urlsplit(str(value or ''))
    if parsed.scheme not in {'https', 'http'} or parsed.hostname not in {'openlibrary.org', 'www.openlibrary.org'}:
        return None
    match = _OL_KEY.match(parsed.path)
    if not match or parsed.path[match.end():match.end() + 1] not in {'', '/', '.'}:
        return None
    return '/' + match.group(1)


def edition_identifiers(editions) -> dict:
    keys, isbns = [], []
    for edition in editions:
        if getattr(edition, 'is_archived', False):
            continue
        isbn = valid_isbn(getattr(edition, 'isbn', ''))
        if isbn:
            isbns.append(isbn)
        for field in ('source_url', 'cover_source_url'):
            key = _openlibrary_key(getattr(edition, field, ''))
            if key:
                keys.append(key)
        notes = getattr(edition, 'translation_notes', '') or ''
        for url in re.findall(r'https?://[^\s<>"\']+', notes):
            key = _openlibrary_key(url.rstrip(').,;'))
            if key:
                keys.append(key)
        # Legacy notes sometimes retain only an explicitly labelled OL ID.
        for match in re.finditer(r'(?:Open Library|openlibrary|source_key)[^\n]{0,80}?\b(OL[0-9]+[WM])\b', notes, re.I):
            key = match.group(1).upper()
            keys.append('/' + ('works/' if key.endswith('W') else 'books/') + key)
    return {'openlibrary': list(dict.fromkeys(keys)), 'isbn': list(dict.fromkeys(isbns))}


def cover_lookup_item(work, aliases=None) -> dict:
    aliases = aliases or {'works': {}, 'people': {}}
    authors = list(work.authors.all())
    editions = getattr(work, 'media_editions', None)
    if editions is None:
        editions = list(work.editions.filter(is_archived=False).order_by('pk'))
    # Prefer the selected edition when its own identifier is available.
    editions = sorted(editions, key=lambda edition: (edition.pk != work.default_edition_id, edition.pk))
    identifiers = edition_identifiers(editions)
    default = work.default_edition
    item = {'id': work.pk, 'title': work.title, 'display_title': work.title,
            'authors': [person.name for person in authors], 'year': work.original_year,
            'edition_id': work.default_edition_id, 'isbn': valid_isbn(default.isbn) if default else '',
            'provider_identifiers': identifiers, 'isbns': identifiers['isbn'],
            'source_urls': list(dict.fromkeys(url for edition in editions
                for url in [edition.source_url, edition.cover_source_url] if url)),
            'publishers': list(dict.fromkeys(edition.publisher for edition in editions if edition.publisher)),
            'shared_priority': bool(getattr(work, 'shared_priority', False)),
            'title_aliases': aliases.get('works', {}).get(str(work.pk), []),
            'author_aliases': list(dict.fromkeys(alias for person in authors
                 for alias in aliases.get('people', {}).get(str(person.pk), [])))}
    placeholder = placeholder_reference(default.cover) if default and getattr(default, 'cover', None) else None
    if placeholder:
        item['placeholder_replacement'] = placeholder
    return item


def _positive_covers(values):
    return [value for value in values if isinstance(value, int) and not isinstance(value, bool) and value > 0]


def _record_authors(record: dict) -> list[str]:
    names = []
    for entry in record.get('authors', [])[:4]:
        if not isinstance(entry, dict):
            continue
        author = entry.get('author', entry)
        key = author.get('key', '') if isinstance(author, dict) else ''
        if re.fullmatch(r'/authors/OL[0-9]+A', key):
            try:
                name = read_json('https://openlibrary.org' + key + '.json', {}).get('name', '')
            except CandidateRejected:
                continue
            if name:
                names.append(name)
    return names


def _verified_record(item: dict, key: str, *, isbn: str = '') -> list[dict]:
    if not _OL_KEY.fullmatch(key):
        return []
    try:
        record = read_json('https://openlibrary.org' + key + '.json', {})
    except CandidateRejected:
        return []
    return _record_candidates(item, record, key, isbn=isbn)


def _record_candidates(item: dict, record: dict, key: str, *, isbn: str = '') -> list[dict]:
    if not _OL_KEY.fullmatch(key) or not match_item_title(item, str(record.get('title', '')))[0]:
        return []
    if isbn and isbn not in [valid_isbn(value) for field in ('isbn_10', 'isbn_13') for value in record.get(field, [])]:
        return []
    # A book record may inherit creators from its linked work. Require both the
    # edition's title and that linked work's identity instead of trusting ID.
    edition_authors = _record_authors(record)
    author_ok = match_item_author(item, edition_authors)
    if not edition_authors and key.startswith('/books/'):
        for link in record.get('works', [])[:2]:
            work_key = link.get('key', '')
            if not re.fullmatch(r'/works/OL[0-9]+W', work_key):
                continue
            try:
                work = read_json('https://openlibrary.org' + work_key + '.json', {})
            except CandidateRejected:
                continue
            if match_item_title(item, str(work.get('title', '')))[0] and match_item_author(item, _record_authors(work)):
                author_ok = True
                break
    if not author_ok:
        return []
    candidates = [{'provider': 'openlibrary', 'cover_id': cover, 'source_key': key}
                  for cover in _positive_covers(record.get('covers', []))[:MAX_IMAGE_CANDIDATES]]
    if key.startswith('/works/'):
        # Keep an identified work even without its aggregate image so linked
        # edition images can be attempted after a broken first cover.
        candidates.append({'provider': 'openlibrary', 'source_key': key, 'linked_editions': True})
    return candidates


def _candidate_images(candidates):
    seen = set()
    for candidate in candidates:
        if candidate.get('linked_editions'):
            try:
                editions = read_json('https://openlibrary.org' + candidate['source_key'] + '/editions.json', {'limit': 20})
            except CandidateRejected:
                continue
            ids = _positive_covers([cover for edition in editions.get('entries', []) for cover in edition.get('covers', [])])
        else:
            ids = [candidate['cover_id']]
        for cover in ids:
            if cover not in seen:
                seen.add(cover)
                yield {**candidate, 'cover_id': cover}


def _download_openlibrary(candidates, attempted, *, item=None):
    for candidate in _candidate_images(candidates):
        if candidate['cover_id'] in attempted:
            continue
        if len(attempted) >= MAX_IMAGE_CANDIDATES:
            break
        attempted.add(candidate['cover_id'])
        try:
            image = read_image(f"https://covers.openlibrary.org/b/id/{candidate['cover_id']}-L.jpg?default=false")
            if item is not None:
                reject_reviewed_cover(item, image)
        except CandidateRejected:
            continue  # A bad individual cover must not hide the next safe one.
        return {**{key: value for key, value in candidate.items() if key != 'linked_editions'}, 'image': image}
    return None


def outage_summary(failures):
    """Retain restrictive failures and every provider's actual retry deadline."""
    if not failures:
        return {}
    strongest = max(failures, key=lambda failure: (
        failure.get('http_status') in {403, 429},
        {'maxlag': 0, 'transient': 1, 'unavailable': 2}.get(failure.get('outage_type'), 2),
        failure['retry_after']))
    return {'provider_outage': True,
            'retry_after': max(failure['retry_after'] for failure in failures),
            **{key: strongest[key] for key in ('reason', 'http_status', 'outage_type')}}


def _provider_failure(item, provider, error):
    item['_provider_outage'] = True
    item['_retry_after'] = max(item.get('_retry_after', 0), error.retry_after)
    item.setdefault('_provider_failures', []).append({
        'provider': provider, 'retry_after': error.retry_after, **error.state_fields()})
    return None, f'provider_blocked: {provider}: {error.reason}'


def openlibrary(item: dict) -> tuple[dict | None, str | None]:
    try:
        return _openlibrary(item)
    except ProviderOutage as error:
        return _provider_failure(item, 'openlibrary', error)


def _openlibrary(item: dict) -> tuple[dict | None, str | None]:
    attempted = set()
    identifiers = item.get('provider_identifiers', {})
    for key in identifiers.get('openlibrary', [])[:6]:
        result = _download_openlibrary(_verified_record(item, key), attempted, item=item)
        if result:
            return result, None
    for isbn in identifiers.get('isbn', [])[:3]:
        if not valid_isbn(isbn):
            continue
        try:
            record = read_json('https://openlibrary.org/isbn/' + isbn + '.json', {})
        except CandidateRejected:
            continue
        result = _download_openlibrary(_record_candidates(item, record, record.get('key', ''), isbn=isbn), attempted, item=item)
        if result:
            return result, None
    matches, seen_keys = [], set()
    useful_authors = [name for name in [*item['authors'], *item.get('author_aliases', [])]
                      if name.casefold() not in {'collaborators', 'anonymous'}]
    titles = list(dict.fromkeys([item['title'], *item.get('title_aliases', [])]))[:3]
    for title in titles:
        for author in useful_authors[:3]:
            data = read_json('https://openlibrary.org/search.json', {
                'title': title, 'author': author, 'limit': 30,
                'fields': 'key,title,author_name,cover_i,edition_count,first_publish_year,first_sentence',
            })
            for doc in data.get('docs', []):
                key = doc.get('key', '')
                if key in seen_keys or not re.fullmatch(r'/works/OL[0-9]+W', key):
                    continue
                seen_keys.add(key)
                title_ok, score = match_item_title(item, str(doc.get('title', '')))
                if title_ok and match_item_author(item, doc.get('author_name', [])):
                    count = doc.get('edition_count')
                    matches.append((score, count if isinstance(count, int) else 0, doc))
            if matches:
                break
        if matches:
            break
    if not matches and item.get('title_only_fallback'):
        broad = read_json('https://openlibrary.org/search.json', {
            'title': item['title'], 'limit': 40,
            'fields': 'key,title,author_name,cover_i,edition_count,first_publish_year,first_sentence',
        }).get('docs', [])
        for doc in broad:
            title_ok, score = match_item_title(item, str(doc.get('title', '')))
            if title_ok and match_item_author(item, doc.get('author_name', [])) and re.fullmatch(r'/works/OL[0-9]+W', doc.get('key', '')):
                matches.append((score, doc.get('edition_count') or 0, doc))
    if not matches:
        return None, 'openlibrary_no_safe_cover'
    matches.sort(key=lambda row: (row[0], row[1]), reverse=True)
    if len(matches) > 1 and matches[0][:2] == matches[1][:2] and matches[0][2]['key'] != matches[1][2]['key']:
        return None, 'openlibrary_ambiguous'
    doc = matches[0][2]
    candidates = [{'provider': 'openlibrary', 'source_key': doc['key'], 'cover_id': cover,
                   'year': doc.get('first_publish_year'), 'edition_count': doc.get('edition_count')}
                  for cover in _positive_covers([doc.get('cover_i')])]
    candidates.append({'provider': 'openlibrary', 'source_key': doc['key'], 'linked_editions': True})
    result = _download_openlibrary(candidates, attempted, item=item)
    return (result, None) if result else (None, 'openlibrary_no_usable_image')


def internet_archive(item: dict) -> tuple[dict | None, str | None]:
    try:
        return _internet_archive(item)
    except ProviderOutage as error:
        return _provider_failure(item, 'internet_archive', error)


def _internet_archive(item: dict) -> tuple[dict | None, str | None]:
    # Escape query-language quotes rather than letting punctuation become an
    # extra clause. Creator metadata varies, so identity is checked locally.
    title = item['title'].replace('\\', ' ').replace('"', ' ')
    query = f'mediatype:texts AND title:("{title}")'
    data = read_json('https://archive.org/advancedsearch.php', {
        'q': query, 'fl[]': ['identifier', 'title', 'creator', 'year'], 'rows': 30, 'output': 'json',
    })
    choices = []
    for doc in data.get('response', {}).get('docs', []):
        title_ok, score = match_item_title(item, str(doc.get('title', '')))
        creators = doc.get('creator', [])
        if isinstance(creators, str):
            creators = [creators]
        if title_ok and match_item_author(item, creators) and re.fullmatch(r'[A-Za-z0-9_.-]+', str(doc.get('identifier', ''))):
            choices.append((score, doc))
    choices.sort(key=lambda row: row[0], reverse=True)
    if not choices:
        return None, 'internet_archive_no_safe_cover'
    for _, doc in choices[:MAX_IMAGE_CANDIDATES]:
        identifier = doc['identifier']
        try:
            image = read_image('https://archive.org/services/img/' + quote(identifier, safe=''))
            reject_reviewed_cover(item, image)
        except CandidateRejected:
            continue
        return {'provider': 'internet_archive', 'image': image, 'identifier': identifier}, None
    return None, 'internet_archive_no_usable_image'


def lookup(item: dict, skip_internet_archive: bool, skip_openlibrary: bool) -> tuple[dict | None, str | None]:
    if requires_scope_review(item):
        return None, 'identity_review_complete_work_scope'
    if not item['authors']:
        return None, 'no_credited_author'
    if skip_openlibrary:
        reason = 'openlibrary_skipped'
    else:
        result, reason = openlibrary(item)
        if result:
            return result, None
    if skip_internet_archive:
        return None, f'{reason}; internet_archive_skipped'
    archive, archive_reason = internet_archive(item)
    if archive:
        item.pop('_provider_outage', None)
        item.pop('_retry_after', None)
        item.pop('_provider_failures', None)
        return archive, None
    return None, f'{reason}; {archive_reason}'


def completed_ids(openlibrary_only: bool, retry_no_safe: bool, archive_only: bool) -> set[int]:
    if not CACHE.exists():
        return set()
    latest: dict[int, str] = {}
    for record in records(CACHE):
        try:
            latest[int(record["work_id"])] = str(record.get("status", ""))
        except (ValueError, KeyError, TypeError):
            continue
    if retry_no_safe:
        return {pk for pk, status in latest.items() if "openlibrary_no_safe_cover" in status}
    # The archive sweep is a one-pass queue. Provider failures are retained in
    # the ledger for a later retry window, but must not repeatedly block every
    # still-unattempted book behind them.
    if archive_only:
        # Open-Library-only rows explicitly say the archive was skipped and
        # still need their first Archive attempt.
        return {pk for pk, status in latest.items() if "internet_archive_skipped" not in status}
    if openlibrary_only:
        # This is a one-pass discovery sweep.  Retrying provider failures here
        # would starve later works; the normal Internet Archive pass remains
        # responsible for retrying unresolved records.
        return set(latest)
    return {pk for pk, status in latest.items() if status == "covered" or "internet_archive_no_safe_cover" in status}


def completed_except_transient() -> set[int]:
    latest = {}
    if CACHE.exists():
        for row in records(CACHE):
            try:
                latest[int(row["work_id"])] = str(row.get("status", ""))
            except (ValueError, KeyError, TypeError):
                continue
    return {pk for pk, status in latest.items() if "error" not in status}


def completed_lookups(items, *, workers, skip_internet_archive=False,
                      skip_openlibrary=False, deadline=None):
    """Yield only attempted lookups, finishing active calls after a soft deadline.

    Keep at most one task per worker in flight. Check again in the worker so a
    task submitted just before the deadline cannot start a later lookup after
    waiting for thread scheduling. Unstarted tasks have no outcome or attempt.
    """
    skipped = object()

    def expired():
        return deadline is not None and time.monotonic() >= deadline

    def run(item):
        if expired():
            return skipped
        return lookup(item, skip_internet_archive, skip_openlibrary)

    items = iter(items)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {}
        exhausted = False
        while pending or not exhausted:
            while not exhausted and len(pending) < workers and not expired():
                try:
                    item = next(items)
                except StopIteration:
                    exhausted = True
                    break
                pending[pool.submit(run, item)] = item
            if not pending:
                break
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                item = pending.pop(future)
                if future.cancelled():
                    continue
                if future.exception() is None and future.result() is skipped:
                    continue
                yield item, future


def completed_lookup_result(item, future):
    """Recheck current reviewed exclusions immediately before saving a result."""
    try:
        match, reason = future.result()
        if match is not None:
            reject_reviewed_cover(item, match['image'])
        return match, reason
    except CandidateRejected as error:
        return None, f'no_safe_cover_reviewed_rejection: {str(error)[:150]}'
    except Exception as error:
        return None, f'worker_error: {str(error)[:150]}'


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument('--max-seconds', type=int, default=0,
                        help='Stop starting lookups after this soft time budget; finish active lookups safely. 0 disables it.')
    parser.add_argument("--skip-internet-archive", action="store_true")
    parser.add_argument("--skip-openlibrary", action="store_true")
    parser.add_argument("--retry-openlibrary-no-safe", action="store_true")
    parser.add_argument("--work-id", type=int, help="Process one work even if it appears in the prior outcome ledger")
    parser.add_argument("--ranking-slug")
    parser.add_argument("--retry", action="store_true")
    parser.add_argument("--clean-series-title", action="store_true")
    parser.add_argument("--min-work-id", type=int, default=0)
    parser.add_argument("--max-work-id", type=int)
    parser.add_argument("--retry-transient", action="store_true")
    parser.add_argument("--title-only-fallback", action="store_true")
    parser.add_argument("--clean-subtitle", action="store_true")
    parser.add_argument("--forms", default="", help="Comma-separated Work forms to include")
    parser.add_argument('--summary-file', type=Path)
    args = parser.parse_args()
    if args.max_seconds < 0:
        parser.error('--max-seconds must be zero or positive.')
    if args.workers < 1:
        parser.error('--workers must be positive.')
    deadline = time.monotonic() + args.max_seconds if args.max_seconds else None
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.settings")
    import django
    django.setup()
    from django.core.files.base import ContentFile
    from django.db import transaction
    from django.db.models import Exists, OuterRef, Prefetch
    from backend.core.models import Edition, Person, RankingEntry, Work
    from backend.core.search import aliases
    verified_aliases = aliases()

    RUN.mkdir(parents=True, exist_ok=True)
    queue = Queue('covers', CACHE)
    rotate(CACHE)
    policy = json.dumps({key: getattr(args, key) for key in ('skip_internet_archive', 'skip_openlibrary',
        'clean_series_title', 'clean_subtitle', 'title_only_fallback')}, sort_keys=True) + ':' + MATCHER_VERSION
    candidates = []
    person_name_titles = {norm(name) for name in Person.objects.values_list("name", flat=True)} if args.title_only_fallback else set()
    catalogue_titles = {norm(title) for title in Work.objects.filter(is_archived=False).values_list("title", flat=True)} if args.title_only_fallback else set()
    ranked = RankingEntry.objects.filter(work_id=OuterRef('pk'), is_archived=False,
                                         ranking__is_archived=False, ranking__origin__in=['curated', 'external'])
    queryset = Work.objects.filter(is_archived=False, pk__gte=args.min_work_id).select_related('default_edition').prefetch_related(
        'authors', Prefetch('editions', queryset=Edition.objects.filter(is_archived=False), to_attr='media_editions')
    ).annotate(shared_priority=Exists(ranked)).order_by('pk')
    if args.forms:
        queryset = queryset.filter(form__in=[value.strip() for value in args.forms.split(",") if value.strip()])
    if args.max_work_id:
        queryset = queryset.filter(pk__lte=args.max_work_id)
    if args.work_id:
        queryset = queryset.filter(pk=args.work_id)
    if args.ranking_slug:
        queryset = queryset.filter(rankingentry__ranking__slug=args.ranking_slug, rankingentry__is_archived=False).distinct()
    for work in queryset:
        if not needs_cover(work):
            continue
        author_names = [person.name for person in work.authors.all()]
        if args.title_only_fallback and (norm(work.title) in person_name_titles or any(norm(name) in catalogue_titles for name in author_names)):
            continue
        lookup_title = work.title
        if args.clean_series_title:
            lookup_title = re.sub(r"\s*\([^)]*(?:run|cycle|series|stories|albums|adaptation|issues)[^)]*\)\s*", " ", lookup_title, flags=re.I).strip()
        if args.clean_subtitle and ":" in lookup_title:
            lookup_title = lookup_title.split(":", 1)[0].strip()
        item = cover_lookup_item(work, verified_aliases)
        item.update(title=lookup_title, title_only_fallback=args.title_only_fallback,
                    shared_priority=work.shared_priority)
        retry = args.retry or bool(args.work_id)
        if args.retry_openlibrary_no_safe or args.retry_transient:
            saved = queue.db.execute('SELECT state,result FROM attempts WHERE work_id=?', (work.pk,)).fetchone()
            retry = bool(saved and ((args.retry_transient and saved[0] in {'retryable', 'retry_exhausted', 'provider_wait'}) or
                         (args.retry_openlibrary_no_safe and 'openlibrary_no_safe_cover' in saved[1])))
            if not retry:
                continue
        if lookup_due(queue, item, policy, retry=retry):
            candidates.append(item)
    candidates.sort(key=queue.priority)
    if args.limit:
        candidates = candidates[:args.limit]
    stats = {"queued": len(candidates), "covered": 0, 'processed': 0}
    failures = []
    def checkpoint_stats():
        # Expose already committed saves during long batches and safe stops;
        # the immutable per-item ledger remains the recovery authority.
        progress = {**stats, 'provider_errors': queue.batch_errors, **outage_summary(failures),
                    **queue.summary()}
        atomic_state(RUN / 'latest-stats.json', progress)
        if args.summary_file:
            atomic_state(args.summary_file, progress)
    checkpoint_stats()
    with CACHE.open("a") as output:
        for item, future in completed_lookups(candidates, workers=args.workers,
                skip_internet_archive=args.skip_internet_archive,
                skip_openlibrary=args.skip_openlibrary, deadline=deadline):
            record = {"work_id": item["id"], "title": item.get("display_title", item["title"]), "lookup_title": item["title"], "authors": item["authors"]}
            match, reason = completed_lookup_result(item, future)
            if reason:
                record["status"] = reason
                if item.get('_provider_outage'):
                    item_failures = item.get('_provider_failures', [])
                    failures.extend(item_failures)
                    record.update(outage_summary(item_failures), provider_failures=item_failures)
                stats[reason.split(":", 1)[0]] = stats.get(reason.split(":", 1)[0], 0) + 1
            else:
                with transaction.atomic():
                    work = Work.objects.select_for_update().get(pk=item["id"])
                    if (work.is_archived or work.title != item['display_title']
                            or work.default_edition_id != item['edition_id']
                            or sorted(work.authors.values_list('name', flat=True)) != sorted(item['authors'])):
                        record['status'] = 'identity_review_changed_during_lookup'
                        queue.finish(item, record, output)
                        stats['processed'] += 1
                        checkpoint_stats()
                        continue
                    edition = Edition.objects.select_for_update().get(pk=work.default_edition_id) if work.default_edition_id else None
                    if edition and (edition.is_archived or edition.work_id != work.pk):
                        record['status'] = 'identity_review_archived_edition'
                        queue.finish(item, record, output)
                        stats['processed'] += 1
                        checkpoint_stats()
                        continue
                    replaced = replacement_receipt(edition, item) if edition and edition.cover else None
                    if edition and edition.cover and not replaced:
                        record['status'] = 'preserved_existing'
                        queue.finish(item, record, output)
                        stats['processed'] += 1
                        checkpoint_stats()
                        continue
                    created = edition is None
                    if created:
                        edition = Edition(work=work, language="Not verified", translation_notes="Display record for a representative work cover; exact edition and language require verification.")
                        edition.full_clean()
                        edition.save()
                        work.default_edition = edition
                    changed = ["default_edition"] if created else []
                    if match["provider"] == "openlibrary":
                        edition.cover_source_url = "https://openlibrary.org" + match["source_key"]
                        attribution = f"Open Library Covers API: https://covers.openlibrary.org/b/id/{match['cover_id']}-L.jpg"
                        filename = f"openlibrary-{match['cover_id']}.jpg"
                    else:
                        edition.cover_source_url = "https://archive.org/details/" + match["identifier"]
                        attribution = f"Internet Archive item image: https://archive.org/services/img/{match['identifier']}"
                        filename = f"internet-archive-{match['identifier']}.jpg"
                    if changed:
                        work.save(update_fields=[*changed, "updated_at"])
                    if replaced:
                        from uuid import uuid4
                        filename = f'placeholder-replacement-{uuid4().hex}.jpg'
                    edition.cover.save(filename, ContentFile(match["image"]), save=False)
                    edition.image_attribution = attribution
                    edition.cover_basis = 'representative_work'
                    edition.save(update_fields=["cover", "cover_source_url", "cover_basis", "image_attribution", "updated_at"])
                    if replaced:
                        record['replaced_placeholder'] = replaced
                record.update(status="covered", provider=match["provider"], edition_id=edition.pk)
                record.update({key: value for key, value in match.items() if key not in {"image", "sentence"}})
                stats["covered"] += 1
            queue.finish(item, record, output)
            stats['processed'] += 1
            checkpoint_stats()
            print(f"[{record['work_id']}] {record['status']} — {record['title']}", flush=True)
    stats['provider_errors'] = queue.batch_errors
    stats['unstarted'] = len(candidates) - stats['processed']
    stats['budget_exhausted'] = bool(stats['unstarted'] and deadline is not None
                                     and time.monotonic() >= deadline)
    stats.update(outage_summary(failures))
    stats.update(queue.summary())
    queue.close()
    atomic_state(RUN / "latest-stats.json", stats)
    if args.summary_file:
        atomic_state(args.summary_file, stats)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    with exclusive('covers'):
        main()
