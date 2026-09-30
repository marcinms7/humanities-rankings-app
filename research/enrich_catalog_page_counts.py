"""Resumably add page counts used by the reading-time estimator.

Existing page counts are immutable here. ISBN lookups are preferred; otherwise
an exact normalized title-and-author Open Library work match may supply its
median edition length. Every decision is appended to a JSONL audit ledger.
"""
from __future__ import annotations

import argparse, json, os, re, sys, threading, time, unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from enrichment_queue import Queue, exclusive, rotate

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
RUN = ROOT / "research" / "_runs" / "2026-09-15" / "catalog-page-counts"
LEDGER = RUN / "outcomes.jsonl"
REQUEST_LOCK = threading.Lock()
LAST_REQUEST = 0.0
REQUEST_INTERVAL = 0.4

def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]", "", value)

def get_json(url: str, params: dict | None = None) -> dict:
    global LAST_REQUEST
    if params: url += "?" + urlencode(params)
    # Open Library is a shared public service.  Coordinate all workers so a
    # restart never creates an accidental burst of simultaneous requests.
    with REQUEST_LOCK:
        delay = REQUEST_INTERVAL - (time.monotonic() - LAST_REQUEST)
        if delay > 0: time.sleep(delay)
        LAST_REQUEST = time.monotonic()
    request = Request(url, headers={"User-Agent": "Marginalia-reading-metadata/1.0 (catalogue enrichment)"})
    with urlopen(request, timeout=15) as response:
        return json.loads(response.read())

def valid_pages(value) -> int | None:
    try: value = int(value)
    except (TypeError, ValueError): return None
    return value if 4 <= value <= 20000 else None

def search_title(value: str) -> str:
    """Remove catalogue-only subtitles/transliteration notes for a retry."""
    value = re.sub(r"\s*\([^)]*\)\s*$", "", value).strip()
    value = re.split(r"\s*[:—–]\s*", value, maxsplit=1)[0].strip()
    return value

def lookup(item: dict) -> dict:
    base = {"work_id": item["id"], "title": item["title"], "authors": item["authors"]}
    # Open Library's edition endpoint gives a physical count for an ISBN.
    if item.get("isbn"):
        isbn = re.sub(r"[^0-9Xx]", "", item["isbn"])
        try:
            data = get_json("https://openlibrary.org/api/books", {"bibkeys": f"ISBN:{isbn}", "format": "json", "jscmd": "data"})
            record = data.get(f"ISBN:{isbn}") or {}
            pages = valid_pages(record.get("number_of_pages"))
            if pages:
                return {**base, "status": "found", "pages": pages, "basis": "isbn_edition", "source_url": record.get("url", ""), "isbn": isbn}
        except Exception as error:
            isbn_error = str(error)[:180]
        else: isbn_error = "ISBN record has no page count"
    else: isbn_error = ""
    if not item["authors"]:
        return {**base, "status": "no_author", "isbn_error": isbn_error}
    try:
        query_title = search_title(item["title"])
        data = get_json("https://openlibrary.org/search.json", {
            "title": query_title, "author": item["authors"][0], "limit": 12,
            "fields": "key,title,author_name,number_of_pages_median,edition_count,isbn,publisher",
        })
    except Exception as error:
        return {**base, "status": "transient_error", "error": str(error)[:180], "isbn_error": isbn_error}
    wanted_titles, wanted_authors = {norm(item["title"]), norm(query_title)}, {norm(x) for x in item["authors"]}
    exact = [d for d in data.get("docs", []) if norm(d.get("title", "")) in wanted_titles and
             wanted_authors.intersection(norm(x) for x in d.get("author_name", [])) and valid_pages(d.get("number_of_pages_median"))]
    if not exact:
        return {**base, "status": "no_exact_page_match", "isbn_error": isbn_error}
    exact.sort(key=lambda d: int(d.get("edition_count") or 0), reverse=True)
    # Multiple OL work records are common. A clearly established record is safe;
    # tied candidates are left unresolved rather than guessed.
    if len(exact) > 1 and int(exact[0].get("edition_count") or 0) <= int(exact[1].get("edition_count") or 0):
        return {**base, "status": "ambiguous", "isbn_error": isbn_error}
    doc = exact[0]
    return {**base, "status": "found", "pages": valid_pages(doc["number_of_pages_median"]),
            "basis": "openlibrary_edition_median", "source_url": "https://openlibrary.org" + doc["key"],
            "edition_count": doc.get("edition_count"), "isbn_error": isbn_error}

def completed() -> set[int]:
    if not LEDGER.exists(): return set()
    latest = {}
    for line in LEDGER.read_text(errors="ignore").splitlines():
        try:
            row = json.loads(line); latest[int(row["work_id"])] = row.get("status")
        except Exception: pass
    return {wid for wid, status in latest.items() if status != "transient_error"}

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--retry-unresolved", action="store_true")
    parser.add_argument("--request-interval", type=float, default=0.4)
    parser.add_argument('--summary-file', type=Path)
    args = parser.parse_args()
    global REQUEST_INTERVAL
    REQUEST_INTERVAL = max(0.1, args.request_interval)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.settings")
    import django; django.setup()
    from django.db import transaction
    from backend.core.models import Edition, Work
    RUN.mkdir(parents=True, exist_ok=True)
    queue = Queue('pages', LEDGER)
    rotate(LEDGER)
    candidates = []
    qs = Work.objects.filter(is_archived=False, form__in=["book", "collection"]).select_related("default_edition").prefetch_related("authors")
    for work in qs.iterator(chunk_size=500):
        edition = work.default_edition
        if edition and edition.pages: continue
        item = {"id": work.pk, "title": work.title, "authors": [a.name for a in work.authors.all()],
                "edition_id": work.default_edition_id, "isbn": edition.isbn if edition else ""}
        if queue.due(item, 'openlibrary-pages-v2', retry=args.retry_unresolved):
            candidates.append(item)
    candidates.sort(key=queue.priority)
    if args.limit: candidates = candidates[:args.limit]
    stats = {"queued": len(candidates), "saved": 0, 'processed': 0}
    with LEDGER.open("a") as output, ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(lookup, item): item for item in candidates}
        for future in as_completed(futures):
            item = futures[future]
            try: row = future.result()
            except Exception as error: row = {**item, "work_id": item["id"], "status": "transient_error", "error": str(error)[:180]}
            if row["status"] == "found":
                with transaction.atomic():
                    work = Work.objects.select_for_update().get(pk=item["id"])
                    edition = Edition.objects.select_for_update().get(pk=work.default_edition_id) if work.default_edition_id else None
                    if (work.is_archived or work.title != item['title']
                            or sorted(work.authors.values_list('name', flat=True)) != sorted(item['authors'])
                            or work.default_edition_id != item['edition_id']
                            or (edition.isbn if edition else '') != item['isbn']
                            or (edition and edition.is_archived)):
                        row['status'] = 'identity_review_changed_during_lookup'
                        queue.finish(item, row, output)
                        stats['processed'] += 1
                        continue
                    if edition is None:
                        edition = Edition.objects.create(work=work, language="Not verified", translation_notes="Provider length record; English translation and exact printing require verification.", pages=row["pages"],
                            pages_basis='isbn_matched' if row['basis'] == 'isbn_edition' else 'estimated_across_editions', pages_source_url=row['source_url'])
                        work.default_edition = edition; work.save(update_fields=["default_edition", "updated_at"])
                        row["created_edition"] = True
                    elif edition.pages is None:
                        edition.pages = row["pages"]
                        edition.pages_basis = 'isbn_matched' if row['basis'] == 'isbn_edition' else 'estimated_across_editions'
                        edition.pages_source_url = row['source_url']
                        edition.save(update_fields=["pages", "pages_basis", "pages_source_url", "updated_at"])
                    else:
                        row["status"] = "preserved_existing"
                    row["edition_id"] = edition.pk
                if row["status"] == "found": stats["saved"] += 1
            stats[row["status"]] = stats.get(row["status"], 0) + 1
            queue.finish(item, row, output)
            stats['processed'] += 1
            print(f"[{stats['processed']}/{stats['queued']}] {row['status']}: {item['title']}" + (f" — {row.get('pages')} pages" if row.get('pages') else ""), flush=True)
    stats['provider_errors'] = queue.batch_errors
    stats.update(queue.summary())
    queue.close()
    (RUN / "latest-stats.json").write_text(json.dumps(stats, indent=2) + "\n")
    if args.summary_file:
        args.summary_file.write_text(json.dumps(stats, indent=2) + '\n')
    print(json.dumps(stats, indent=2))

if __name__ == "__main__":
    with exclusive('pages'):
        main()
