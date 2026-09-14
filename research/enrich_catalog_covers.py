"""Resumable Open Library cover/edition enrichment for catalog works.

Google Books was tested first but returned HTTP 429 without an API key. This
script keeps every lookup in a cache so interrupted runs resume safely.
"""
from __future__ import annotations

import argparse
import json
import sys
import re
import time
import unicodedata
from pathlib import Path

from django.core.files.base import ContentFile
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
RUN = ROOT / "research" / "_runs" / "2026-09-13"
CACHE = RUN / "cover-enrichment-cache.jsonl"
MEDIA = ROOT / "media" / "covers" / "api-enrichment"


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]", "", value)


def best_doc(work, docs):
    title = norm(work.title)
    author_values = work.authors.all() if hasattr(work.authors, "all") else work.authors
    authors = {norm(person.name) for person in author_values}
    scored = []
    for doc in docs:
        doc_title = norm(doc.get("title", ""))
        doc_authors = {norm(name) for name in doc.get("author_name", [])}
        title_score = 2 if doc_title == title else (1 if title in doc_title or doc_title in title else 0)
        author_score = 2 if authors and doc_authors & authors else 0
        cover_score = 1 if doc.get("cover_i") else 0
        scored.append((title_score + author_score + cover_score, doc))
    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored or scored[0][0] < 4:
        return None
    return scored[0][1]


def load_cache():
    if not CACHE.exists():
        return {}
    result = {}
    for line in CACHE.read_text().splitlines():
        try:
            row = json.loads(line)
            result[str(row["work_id"])] = row
        except (ValueError, KeyError):
            continue
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--delay", type=float, default=0.05)
    args = parser.parse_args()
    import os
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.settings")
    import django
    django.setup()
    from backend.core.models import Edition, Work

    cache = load_cache()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    MEDIA.mkdir(parents=True, exist_ok=True)
    def fetch_json(url, params):
        request = Request(url + "?" + urlencode(params), headers={"User-Agent": "humanities-rankings-cover-enrichment/1.0"})
        with urlopen(request, timeout=6) as response:
            return json.loads(response.read())

    def fetch_bytes(url):
        request = Request(url, headers={"User-Agent": "humanities-rankings-cover-enrichment/1.0"})
        with urlopen(request, timeout=6) as response:
            return response.read()
    works = list(Work.objects.filter(is_archived=False).prefetch_related("authors", "editions"))
    processed = 0
    stats = {"already_covered": 0, "matched": 0, "covers": 0, "no_match": 0, "errors": 0}
    with CACHE.open("a") as cache_file:
        for work in works:
            if args.limit and processed >= args.limit:
                break
            if any(edition.cover for edition in work.editions.filter(is_archived=False)):
                stats["already_covered"] += 1
                continue
            if str(work.pk) in cache:
                continue
            author = work.authors.first()
            params = {"title": work.title, "author": author.name if author else "", "limit": 5, "fields": "*,availability"}
            row = {"work_id": work.pk, "title": work.title, "status": "no_match"}
            try:
                doc = best_doc(work, fetch_json("https://openlibrary.org/search.json", params).get("docs", []))
                if not doc:
                    stats["no_match"] += 1
                else:
                    stats["matched"] += 1
                    isbn = (doc.get("isbn") or [""])[0]
                    cover_id = doc.get("cover_i")
                    edition = work.editions.filter(is_archived=False).first()
                    if edition is None:
                        edition = Edition(work=work, language="English", publisher=(doc.get("publisher") or [""])[0], isbn=isbn,
                                          pages=doc.get("number_of_pages_median"), source_url=f"https://openlibrary.org/works/{(doc.get('key') or '').split('/')[-1]}")
                        edition.full_clean()
                        edition.save()
                    if cover_id:
                        image = fetch_bytes(f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg?default=false")
                        edition.cover.save(f"openlibrary-{cover_id}.jpg", ContentFile(image), save=False)
                        edition.image_attribution = f"Open Library Covers API: https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
                        edition.save(update_fields=["cover", "image_attribution", "updated_at"])
                        stats["covers"] += 1
                    row.update({"status": "covered" if cover_id else "matched_without_cover", "edition_id": edition.pk, "cover_id": cover_id, "isbn": isbn})
            except Exception as error:
                stats["errors"] += 1
                row.update({"status": "error", "error": str(error)[:300]})
            cache_file.write(json.dumps(row, ensure_ascii=False) + "\n")
            cache_file.flush()
            cache[str(work.pk)] = row
            processed += 1
            time.sleep(args.delay)
    print(json.dumps({"processed": processed, **stats, "cached": len(cache)}, indent=2))


if __name__ == "__main__":
    main()
