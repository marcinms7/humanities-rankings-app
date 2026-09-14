"""Fill covers for duplicated Open Library work records, conservatively.

Open Library sometimes keeps several work records for the same title and author.
For a title and author that match exactly after normalisation, its longest-lived
record normally has the greatest edition count.  This script accepts that record
only when it has a strictly greater edition count than the next candidate.  It
does not overwrite covers or claim edition-specific bibliographic data.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from enrich_new_catalog_openlibrary import norm, request_bytes, request_json

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
RUN = ROOT / "research" / "_runs" / "2026-09-13" / "new-catalog-openlibrary-canonical"
CACHE = RUN / "outcomes.jsonl"


def completed_ids() -> set[int]:
    if not CACHE.exists():
        return set()
    done = set()
    for line in CACHE.read_text().splitlines():
        try:
            row = json.loads(line)
            # Transient connection errors can be retried; a substantive result
            # is retained so restarting a small batch never repeats it.
            if not str(row.get("status", "")).startswith(("lookup_error", "cover_error")):
                done.add(int(row["work_id"]))
        except (ValueError, KeyError, TypeError):
            continue
    return done


def find_canonical(item: dict) -> tuple[dict | None, str | None]:
    if not item["authors"]:
        return None, "no_credited_author"
    try:
        data = request_json("https://openlibrary.org/search.json", {
            "title": item["title"], "author": item["authors"][0], "limit": 30,
            "fields": "key,title,author_name,cover_i,edition_count,first_publish_year,first_sentence",
        })
    except Exception as error:
        return None, f"lookup_error: {str(error)[:180]}"
    title = norm(item["title"])
    authors = {norm(name) for name in item["authors"]}
    candidates = [doc for doc in data.get("docs", [])
                  if norm(doc.get("title", "")) == title
                  and authors.intersection({norm(name) for name in doc.get("author_name", [])})]
    # Keep only records that can actually provide a cover, then accept a clear
    # canonical record rather than guessing between equally established works.
    candidates = [doc for doc in candidates if doc.get("cover_i")]
    candidates.sort(key=lambda doc: int(doc.get("edition_count") or 0), reverse=True)
    if not candidates:
        return None, "no_exact_cover_candidate"
    if len(candidates) > 1 and int(candidates[0].get("edition_count") or 0) <= int(candidates[1].get("edition_count") or 0):
        return None, "ambiguous_canonical_candidate"
    doc = candidates[0]
    try:
        image = request_bytes(f"https://covers.openlibrary.org/b/id/{doc['cover_i']}-L.jpg?default=false")
    except Exception as error:
        return None, f"cover_error: {str(error)[:180]}"
    if len(image) < 1024:
        return None, "cover_response_too_small"
    return {**doc, "_image": image}, None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-work-id", type=int, required=True)
    parser.add_argument("--max-work-id", type=int, required=True)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.settings")
    import django
    django.setup()
    from django.core.files.base import ContentFile
    from django.db import transaction
    from backend.core.models import Edition, Work

    RUN.mkdir(parents=True, exist_ok=True)
    candidates = []
    done = completed_ids()
    works = Work.objects.filter(is_archived=False, pk__gte=args.min_work_id, pk__lte=args.max_work_id).select_related("default_edition").prefetch_related("authors")
    for work in works:
        if work.pk in done or (work.default_edition_id and work.default_edition and work.default_edition.cover):
            continue
        candidates.append({"id": work.pk, "title": work.title, "authors": [person.name for person in work.authors.all()]})
    if args.limit:
        candidates = candidates[:args.limit]
    stats = {"queued": len(candidates), "covered": 0}
    with CACHE.open("a") as output, ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(find_canonical, item): item for item in candidates}
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
                    created_default = edition is None
                    if created_default:
                        edition = Edition(work=work, language="English", source_url="https://openlibrary.org" + doc["key"],
                            translation_notes="Matched canonical Open Library work record; exact edition, translator, publisher and page count remain to be verified.")
                        edition.full_clean()
                        edition.save()
                        work.default_edition = edition
                    changed = ["default_edition"] if created_default else []
                    if not work.original_year and doc.get("first_publish_year"):
                        work.original_year = doc["first_publish_year"]
                        changed.append("original_year")
                    sentence = doc.get("first_sentence")
                    sentence = sentence[0] if isinstance(sentence, list) and sentence else sentence
                    if not work.description and isinstance(sentence, str) and sentence:
                        work.description = sentence
                        changed.append("description")
                    if changed:
                        work.save(update_fields=[*changed, "updated_at"])
                    edition.cover.save(f"openlibrary-{doc['cover_i']}.jpg", ContentFile(image), save=False)
                    edition.image_attribution = f"Open Library Covers API: https://covers.openlibrary.org/b/id/{doc['cover_i']}-L.jpg"
                    edition.save(update_fields=["cover", "image_attribution", "updated_at"])
                row.update(status="covered", cover_id=doc["cover_i"], source_key=doc["key"], edition_id=edition.pk,
                           canonical_edition_count=doc.get("edition_count"))
                stats["covered"] += 1
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
            output.flush()
    (RUN / "latest-stats.json").write_text(json.dumps(stats, indent=2) + "\n")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
