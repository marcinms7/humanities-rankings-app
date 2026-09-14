"""Conservatively enrich recently added books and manga from Open Library.

The lookup requires a title match and a credited-author match. It fills only
missing cover/year fields, appends a short sourced summary only to blank or
import-placeholder descriptions, and adds controlled genres without removing
anything. Results are checkpointed one record at a time for safe resumption.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
RUN = ROOT / "research" / "_runs" / "2026-09-14" / "catalog-added-openlibrary"
CACHE = RUN / "outcomes.jsonl"
HEADERS = {"User-Agent": "Marginalia catalog metadata enrichment/1.0 (Open Library API)"}


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]", "", value)


def words(value: str) -> set[str]:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()
    return set(re.findall(r"[a-z0-9]+", value))


def title_score(expected: str, found: str) -> int:
    left, right = norm(expected), norm(found)
    if left == right:
        return 100
    if len(left) >= 14 and (left in right or right in left):
        return 90
    a, b = words(expected), words(found)
    return 80 if a and b and len(a & b) / len(a | b) >= .86 else 0


GENRE_PATTERNS = {
    "Adventure": (r"\badventure (fiction|stories)\b",),
    "Autobiographical": (r"\bautobiograph", r"\bmemoirs?\b"),
    "Children's": (r"\bchildren'?s (fiction|stories|literature)\b", r"\bjuvenile fiction\b"),
    "Comedy": (r"\bcomedy\b", r"\bhumorous (fiction|stories)\b"),
    "Coming of Age": (r"\bcoming of age\b", r"\bbildungsroman\b"),
    "Crime": (r"\bcrime fiction\b", r"\bdetective fiction\b"),
    "Cyberpunk": (r"\bcyberpunk\b",),
    "Drama": (r"\bdrama\b",),
    "Dystopian": (r"\bdystop",),
    "Erotica": (r"\berotic (fiction|literature|stories)\b", r"\berotica\b"),
    "Fantasy": (r"\bfantasy fiction\b", r"\bfantasy comic",),
    "Gothic": (r"\bgothic fiction\b",),
    "Historical Fiction": (r"\bhistorical fiction\b",),
    "Horror": (r"\bhorror (fiction|stories|tales|comic)",),
    "Literary Fiction": (r"\bliterary fiction\b",),
    "Magical Realism": (r"\bmagical realism\b", r"\bmagic realism\b"),
    "Martial Arts": (r"\bmartial arts\b",),
    "Mystery": (r"\bmystery fiction\b", r"\bdetective and mystery stories\b"),
    "Myth & Folklore": (r"\bfolklore\b", r"\bmythology\b"),
    "Post-Apocalyptic": (r"\bpost apocalyptic\b", r"\bpost-apocalyptic\b"),
    "Psychological": (r"\bpsychological fiction\b",),
    "Romance": (r"\blove stories\b", r"\bromance fiction\b", r"\bromantic fiction\b"),
    "Satire": (r"\bsatire\b",),
    "Science Fiction": (r"\bscience fiction\b",),
    "Sports": (r"\bsports (fiction|stories|comic)",),
    "Superhero": (r"\bsuperheroes?\b",),
    "Supernatural": (r"\bsupernatural fiction\b",),
    "Surrealism": (r"\bsurrealism\b",),
    "Thriller": (r"\bthrillers? \(fiction\)\b", r"\bsuspense fiction\b"),
    "War": (r"\bwar (fiction|stories)\b",),
    "Western": (r"\bwestern (fiction|stories)\b",),
}


def mapped_genres(subjects: list[str]) -> list[str]:
    genres = []
    for genre, patterns in GENRE_PATTERNS.items():
        if any(re.search(pattern, subject.casefold().replace("_", " ")) for subject in subjects for pattern in patterns):
            genres.append(genre)
    return genres


def read_json(url: str, params: dict, timeout: int = 10) -> dict:
    request = Request(url + "?" + urlencode(params, doseq=True), headers=HEADERS)
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def read_image(cover_id: int) -> bytes:
    url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg?default=false"
    with urlopen(Request(url, headers=HEADERS), timeout=12) as response:
        return response.read()


def lookup(item: dict) -> dict:
    if not item["authors"]:
        return {"status": "no_credited_author"}
    try:
        data = read_json("https://openlibrary.org/search.json", {
            "title": item["title"], "author": item["authors"][0], "limit": 30,
            "fields": "key,title,author_name,cover_i,edition_count,first_publish_year,first_sentence,subject",
        })
    except Exception as error:
        return {"status": "lookup_error", "error": str(error)[:240]}
    expected_authors = {norm(name) for name in item["authors"]}
    choices = []
    for doc in data.get("docs", []):
        score = title_score(item["title"], str(doc.get("title", "")))
        found_authors = {norm(name) for name in doc.get("author_name", [])}
        if score and expected_authors & found_authors:
            choices.append((score, int(doc.get("edition_count") or 0), doc))
    choices.sort(key=lambda row: (row[0], row[1]), reverse=True)
    if not choices:
        return {"status": "no_safe_match"}
    if len(choices) > 1 and choices[0][:2] == choices[1][:2] and choices[0][2].get("key") != choices[1][2].get("key"):
        return {"status": "ambiguous_match", "keys": [choices[0][2].get("key"), choices[1][2].get("key")]}
    doc = choices[0][2]
    result = {
        "status": "matched", "source_key": doc.get("key"), "matched_title": doc.get("title"),
        "matched_authors": doc.get("author_name", []), "edition_count": doc.get("edition_count"),
        "year": doc.get("first_publish_year"), "subjects": doc.get("subject", [])[:200],
        "genres": mapped_genres(doc.get("subject", [])), "cover_id": doc.get("cover_i"),
    }
    sentence = doc.get("first_sentence")
    sentence = sentence[0] if isinstance(sentence, list) and sentence else sentence
    if isinstance(sentence, str) and 20 <= len(sentence.strip()) <= 700:
        result["sentence"] = sentence.strip()
    if item["needs_cover"] and result["cover_id"]:
        try:
            image = read_image(int(result["cover_id"]))
            if len(image) >= 1024:
                result["image"] = image
            else:
                result["cover_error"] = "cover_too_small"
        except Exception as error:
            result["cover_error"] = str(error)[:240]
    return result


def completed_ids() -> set[int]:
    if not CACHE.exists():
        return set()
    ids = set()
    for line in CACHE.read_text().splitlines():
        try:
            record = json.loads(line)
            if record.get("status") not in {"lookup_error"}:
                ids.add(int(record["work_id"]))
        except (ValueError, KeyError, TypeError):
            continue
    return ids


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-work-id", type=int, default=5613)
    parser.add_argument("--include-manga", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.settings")
    import django
    django.setup()
    from django.core.files.base import ContentFile
    from django.db import connection, transaction
    from django.db.models import Q
    from backend.core.models import Edition, Tag, Work

    if connection.vendor == "sqlite":
        # A separate resumable cover sweep may be finishing in the local app.
        # Wait for its short write transactions instead of abandoning a safe
        # metadata match or competing with it.
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA busy_timeout = 30000")

    RUN.mkdir(parents=True, exist_ok=True)
    done = completed_ids()
    scope = Q(pk__gte=args.min_work_id)
    if args.include_manga:
        scope |= Q(field="manga")
    candidates = []
    queryset = Work.objects.filter(scope, is_archived=False).select_related("default_edition").prefetch_related("authors").order_by("pk")
    for work in queryset:
        if work.pk in done:
            continue
        candidates.append({
            "id": work.pk, "title": work.title, "authors": [author.name for author in work.authors.all()],
            "needs_cover": not bool(work.default_edition_id and work.default_edition and work.default_edition.cover),
        })
        if args.limit and len(candidates) >= args.limit:
            break

    stats = {"queued": len(candidates), "matched": 0, "covers_added": 0, "years_added": 0, "descriptions_added": 0, "genre_relationships_added": 0}
    with CACHE.open("a") as output, ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(lookup, item): item for item in candidates}
        for future in as_completed(futures):
            item = futures[future]
            try:
                result = future.result()
            except Exception as error:
                result = {"status": "worker_error", "error": str(error)[:240]}
            record = {"work_id": item["id"], "title": item["title"], "authors": item["authors"], **{k: v for k, v in result.items() if k != "image"}}
            if result["status"] == "matched":
                stats["matched"] += 1
                if args.apply:
                    with transaction.atomic():
                        work = Work.objects.select_for_update().select_related("default_edition").get(pk=item["id"], is_archived=False)
                        changed = []
                        year = result.get("year")
                        if work.original_year is None and isinstance(year, int) and int(result.get("edition_count") or 0) >= 5 and year != 0 and -10000 <= year <= datetime.now().year:
                            work.original_year = year
                            changed.append("original_year")
                            record["year_added"] = True
                            stats["years_added"] += 1
                        sentence = result.get("sentence")
                        if sentence and (not work.description.strip() or work.description.startswith("Source-defined entry in")) and sentence not in work.description:
                            prefix = f"Open Library summary: {sentence}"
                            work.description = f"{prefix}\n\n{work.description}" if work.description else prefix
                            changed.append("description")
                            record["description_added"] = True
                            stats["descriptions_added"] += 1
                        if changed:
                            work.save(update_fields=[*changed, "updated_at"])
                        added_genres = []
                        for genre in result.get("genres", []):
                            term, _ = Tag.objects.get_or_create(name=genre, defaults={"kind": "genre"})
                            if term.kind != "genre":
                                continue
                            _, created = work.tags.through.objects.get_or_create(work_id=work.pk, tag_id=term.pk)
                            if created:
                                added_genres.append(genre)
                        stats["genre_relationships_added"] += len(added_genres)
                        record["genres_added"] = added_genres
                        record["genre_relationships_added"] = len(added_genres)
                        if result.get("image") and not (work.default_edition_id and work.default_edition and work.default_edition.cover):
                            edition = work.default_edition or Edition.objects.create(work=work, language="English")
                            if not work.default_edition_id:
                                work.default_edition = edition
                                work.save(update_fields=["default_edition", "updated_at"])
                            cover_id = int(result["cover_id"])
                            edition.cover.save(f"openlibrary-{cover_id}.jpg", ContentFile(result["image"]), save=False)
                            edition.source_url = "https://openlibrary.org" + result["source_key"]
                            edition.image_attribution = f"Open Library Covers API: https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
                            edition.save(update_fields=["cover", "source_url", "image_attribution", "updated_at"])
                            record["edition_id"] = edition.pk
                            record["cover_added"] = True
                            stats["covers_added"] += 1
            else:
                stats[result["status"]] = stats.get(result["status"], 0) + 1
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
            output.flush()
    stats["completed_at"] = datetime.now(timezone.utc).isoformat()
    stats["mode"] = "apply" if args.apply else "lookup-only"
    (RUN / "latest-stats.json").write_text(json.dumps(stats, indent=2) + "\n")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
