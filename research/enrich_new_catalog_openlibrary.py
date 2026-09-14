"""Resumable, conservative Open Library cover and basic-metadata enrichment.

This only fills records that have no displayed default-edition cover. A match
requires an exact normalized title and at least one exact normalized credited
author. Open Library search results are work-level aggregates, so publisher,
page count and ISBN are deliberately not represented as a verified edition.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
RUN = ROOT / "research" / "_runs" / "2026-09-13" / "new-catalog-openlibrary"
CACHE = RUN / "outcomes.jsonl"


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]", "", value)


def request_json(url: str, params: dict) -> dict:
    request = Request(url + "?" + urlencode(params), headers={"User-Agent": "Marginalia catalogue enrichment/1.0"})
    with urlopen(request, timeout=12) as response:
        return json.loads(response.read())


def request_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "Marginalia catalogue enrichment/1.0"})
    with urlopen(request, timeout=12) as response:
        return response.read()


def find_match(item: dict) -> tuple[dict | None, str | None]:
    if not item["authors"]:
        return None, "no_credited_author"
    try:
        data = request_json("https://openlibrary.org/search.json", {
            "title": item["title"], "author": item["authors"][0], "limit": 10,
            "fields": "key,title,author_name,cover_i,first_publish_year,first_sentence",
        })
    except Exception as error:
        return None, f"lookup_error: {str(error)[:180]}"
    title = norm(item["title"])
    authors = {norm(name) for name in item["authors"]}
    exact = [doc for doc in data.get("docs", [])
             if norm(doc.get("title", "")) == title
             and authors.intersection({norm(name) for name in doc.get("author_name", [])})]
    if len(exact) != 1:
        return None, "no_unique_exact_title_author_match"
    doc = exact[0]
    if not doc.get("cover_i"):
        return doc, "matched_without_cover"
    try:
        image = request_bytes(f"https://covers.openlibrary.org/b/id/{doc['cover_i']}-L.jpg?default=false")
    except Exception as error:
        return None, f"cover_error: {str(error)[:180]}"
    if len(image) < 1024:
        return None, "cover_response_too_small"
    return {**doc, "_image": image}, None


def load_cache() -> dict[str, dict]:
    if not CACHE.exists():
        return {}
    records = {}
    for line in CACHE.read_text().splitlines():
        try:
            row = json.loads(line)
            records[str(row["work_id"])] = row
        except (ValueError, KeyError):
            continue
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-work-id", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.settings")
    import django
    django.setup()
    from django.core.files.base import ContentFile
    from django.db import transaction
    from backend.core.models import Edition, Work

    RUN.mkdir(parents=True, exist_ok=True)
    cached = load_cache()
    candidates = []
    for work in Work.objects.filter(is_archived=False, pk__gte=args.min_work_id).prefetch_related("authors").select_related("default_edition"):
        if work.default_edition_id and work.default_edition and work.default_edition.cover:
            continue
        if str(work.pk) in cached and cached[str(work.pk)].get("status") not in {"lookup_error", "cover_error"}:
            continue
        candidates.append({"id": work.pk, "title": work.title, "authors": [p.name for p in work.authors.all()]})
    if args.limit:
        candidates = candidates[:args.limit]
    stats = {"queued": len(candidates), "covered": 0, "matched_without_cover": 0, "no_unique_exact_title_author_match": 0,
             "no_credited_author": 0, "lookup_error": 0, "cover_error": 0, "cover_response_too_small": 0}
    with CACHE.open("a") as output, ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(find_match, item): item for item in candidates}
        for future in as_completed(futures):
            item = futures[future]
            row = {"work_id": item["id"], "title": item["title"], "authors": item["authors"]}
            try:
                doc, reason = future.result()
            except Exception as error:
                doc, reason = None, f"lookup_error: worker failed: {str(error)[:180]}"
            if reason:
                row["status"] = reason
                stats[reason.split(":", 1)[0]] = stats.get(reason.split(":", 1)[0], 0) + 1
            else:
                image = doc.pop("_image")
                with transaction.atomic():
                    work = Work.objects.select_for_update().get(pk=item["id"], is_archived=False)
                    edition = work.default_edition
                    created_default = False
                    if edition is None:
                        edition = Edition(work=work, language="English", source_url="https://openlibrary.org" + doc["key"],
                                          translation_notes="Matched Open Library work record; exact edition, translator, publisher and page count remain to be verified.")
                        edition.full_clean()
                        edition.save()
                        work.default_edition = edition
                        created_default = True
                    changed = []
                    if not work.original_year and doc.get("first_publish_year"):
                        work.original_year = doc["first_publish_year"]
                        changed.append("original_year")
                    sentence = doc.get("first_sentence")
                    if isinstance(sentence, list):
                        sentence = sentence[0] if sentence else ""
                    if not isinstance(sentence, str):
                        sentence = ""
                    if not work.description and sentence:
                        work.description = sentence
                        changed.append("description")
                    if created_default:
                        changed.append("default_edition")
                    if changed:
                        changed.append("updated_at")
                        work.save(update_fields=changed)
                    edition.cover.save(f"openlibrary-{doc['cover_i']}.jpg", ContentFile(image), save=False)
                    edition.image_attribution = f"Open Library Covers API: https://covers.openlibrary.org/b/id/{doc['cover_i']}-L.jpg"
                    edition.save(update_fields=["cover", "image_attribution", "updated_at"])
                row.update(status="covered", cover_id=doc["cover_i"], source_key=doc["key"], edition_id=edition.pk,
                           first_publish_year=doc.get("first_publish_year"))
                stats["covered"] += 1
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
            output.flush()
            cached[str(item["id"])] = row
    (RUN / "latest-stats.json").write_text(json.dumps(stats, indent=2) + "\n")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
