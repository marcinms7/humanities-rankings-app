"""Resumable sourced web-image fallback for catalogue covers.

Uses DuckDuckGo public image results only to discover a source page. A result is
accepted only if its result text identifies the catalogue title and an author,
and it comes from a publisher or major book retailer. The source
page and image URL are saved as attribution; it never silently substitutes a
generic or title-only thumbnail.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from enrich_catalog_covers_public import norm, same_title

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
RUN = ROOT / "research" / "_runs" / "2026-09-14" / "catalog-web-cover-fallback"
CACHE = RUN / "outcomes.jsonl"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Marginalia catalogue cover lookup/1.0)"}
TRUSTED = ("penguinrandomhouse.com", "harpercollins.com", "macmillan.com", "hachettebookgroup.com", "bloomsbury.com", "panmacmillan.com", "faber.co.uk", "oup.com", "cambridge.org", "amazon.", "bookshop.org", "marvel.com", "dc.com", "imagecomics.com", "darkhorse.com", "fantagraphics.com", "viz.com", "kodansha.us", "yenpress.com", "sevenseasentertainment.com", "midtowncomics.com")
SEARCH_LOCK = threading.Lock()
LAST_SEARCH = 0.0


def read(url: str, timeout: int = 12) -> bytes:
    with urlopen(Request(url, headers=HEADERS), timeout=timeout) as response:
        return response.read()


def image_results(query: str) -> dict:
    """Rate-limit and retry the public endpoint rather than burning the queue."""
    global LAST_SEARCH
    error = None
    for delay in (0, 3, 8):
        if delay:
            time.sleep(delay)
        try:
            with SEARCH_LOCK:
                pause = 2.0 - (time.monotonic() - LAST_SEARCH)
                if pause > 0:
                    time.sleep(pause)
                page = read("https://duckduckgo.com/?" + urlencode({"q": query})).decode("utf-8", "ignore")
                LAST_SEARCH = time.monotonic()
            token = re.search(r"vqd=['\"]?([\d-]+)", page)
            if not token:
                raise ValueError("search token missing")
            with SEARCH_LOCK:
                pause = 2.0 - (time.monotonic() - LAST_SEARCH)
                if pause > 0:
                    time.sleep(pause)
                data = read("https://duckduckgo.com/i.js?" + urlencode({"q": query, "vqd": token.group(1), "o": "json", "l": "us-en"}))
                LAST_SEARCH = time.monotonic()
            return json.loads(data)
        except Exception as exc:
            error = exc
    raise error or RuntimeError("search failed")


def search(item: dict) -> tuple[dict | None, str | None]:
    if not item["authors"]:
        return None, "no_credited_author"
    query = f'"{item["title"]}" "{item["authors"][0]}" book cover -site:goodreads.com'
    try:
        payload = image_results(query)
    except Exception as error:
        return None, f"search_error: {str(error)[:150]}"
    title_norm, author_norm = norm(item["title"]), norm(item["authors"][0])
    surname = norm(item["authors"][0].split()[-1])
    for result in payload.get("results", []):
        source = str(result.get("url", ""))
        host = urlparse(source).netloc.casefold()
        text = f"{result.get('title', '')} {source}"
        title_ok, _ = same_title(item["title"], text)
        author_ok = author_norm in norm(text) or (len(surname) >= 4 and surname in norm(text))
        if not (title_ok and author_ok and any(domain in host for domain in TRUSTED)):
            continue
        image_url = str(result.get("image", ""))
        if not image_url.startswith(("https://", "http://")):
            continue
        try:
            image = read(image_url, timeout=15)
        except Exception:
            continue
        if len(image) < 1024:
            continue
        return {"image": image, "source_url": source, "image_url": image_url, "host": host}, None
    return None, "no_safe_web_result"


def completed_ids() -> set[int]:
    if not CACHE.exists():
        return set()
    done = set()
    for line in CACHE.read_text().splitlines():
        try:
            done.add(int(json.loads(line)["work_id"]))
        except (ValueError, KeyError, TypeError):
            continue
    return done


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=24)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--ranking-slug")
    parser.add_argument("--retry", action="store_true")
    args = parser.parse_args()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.settings")
    import django
    django.setup()
    from django.core.files.base import ContentFile
    from django.db import transaction
    from backend.core.models import Edition, Work
    RUN.mkdir(parents=True, exist_ok=True)
    done = set() if args.retry else completed_ids()
    candidates = []
    queryset = Work.objects.filter(is_archived=False)
    if args.ranking_slug:
        queryset = queryset.filter(rankingentry__ranking__slug=args.ranking_slug, rankingentry__is_archived=False).distinct()
    for work in queryset.select_related("default_edition").prefetch_related("authors").order_by("pk"):
        if work.pk in done or (work.default_edition_id and work.default_edition and work.default_edition.cover):
            continue
        candidates.append({"id": work.pk, "title": work.title, "authors": [p.name for p in work.authors.all()]})
        if args.limit and len(candidates) >= args.limit:
            break
    stats = {"queued": len(candidates), "covered": 0}
    with CACHE.open("a") as output, ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(search, item): item for item in candidates}
        for future in as_completed(futures):
            item = futures[future]
            row = {"work_id": item["id"], "title": item["title"], "authors": item["authors"]}
            try:
                match, reason = future.result()
            except Exception as error:
                match, reason = None, f"worker_error: {str(error)[:150]}"
            if reason:
                row["status"] = reason
                stats[reason.split(":", 1)[0]] = stats.get(reason.split(":", 1)[0], 0) + 1
            else:
                with transaction.atomic():
                    work = Work.objects.select_for_update().get(pk=item["id"], is_archived=False)
                    edition = work.default_edition
                    created = edition is None
                    if created:
                        edition = Edition(work=work, language="English")
                        edition.full_clean()
                        edition.save()
                        work.default_edition = edition
                        work.save(update_fields=["default_edition", "updated_at"])
                    digest = hashlib.sha256(match["image_url"].encode()).hexdigest()[:16]
                    edition.cover.save(f"web-cover-{digest}.jpg", ContentFile(match["image"]), save=False)
                    edition.source_url = match["source_url"]
                    edition.image_attribution = f"Web image result from {match['host']}: {match['source_url']} (image: {match['image_url']})"
                    edition.save(update_fields=["cover", "source_url", "image_attribution", "updated_at"])
                row.update(status="covered", source_url=match["source_url"], image_url=match["image_url"], edition_id=edition.pk)
                stats["covered"] += 1
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
            output.flush()
            print(f"[{row['work_id']}] {row['status']} — {row['title']}", flush=True)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
