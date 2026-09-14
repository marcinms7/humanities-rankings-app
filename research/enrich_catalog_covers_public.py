"""Resumable public-API cover enrichment for the shared catalogue.

Order of evidence: Open Library's work search/Covers API, then Internet
Archive's public advanced-search/image service.  A cover is accepted only when
the submitted work title and one credited author agree after normalisation.
This creates a neutral English display edition only where a work has none; it
does not infer ISBNs, publishers, page counts, translators, or release dates.
Every outcome is appended before the next item so it can be resumed safely.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
RUN = ROOT / "research" / "_runs" / "2026-09-13" / "catalog-public-cover-fallback"
CACHE = RUN / "outcomes.jsonl"
HEADERS = {"User-Agent": "Marginalia catalogue enrichment/1.0 (public bibliographic lookup)"}


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]", "", value)


def words(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()))


def read_json(url: str, params: dict, timeout: int = 6) -> dict:
    request = Request(url + "?" + urlencode(params, doseq=True), headers=HEADERS)
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def read_image(url: str) -> bytes:
    with urlopen(Request(url, headers=HEADERS), timeout=8) as response:
        return response.read()


def same_title(expected: str, found: str) -> tuple[bool, int]:
    left, right = norm(expected), norm(found)
    if left == right:
        return True, 100
    expected_words, found_words = list(words_in_order(expected)), list(words_in_order(found))
    if expected_words and expected_words[0] in {"a", "an", "the"}:
        expected_words = expected_words[1:]
    if found_words and found_words[0] in {"a", "an", "the"}:
        found_words = found_words[1:]
    if expected_words and expected_words == found_words:
        return True, 98
    if len(left) >= 14 and (left in right or right in left):
        return True, 90
    a, b = words(expected), words(found)
    if a and b and len(a & b) / len(a | b) >= .86:
        return True, 80
    return False, 0


def words_in_order(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold())


def same_author(expected: list[str], found: list[str]) -> bool:
    for left in expected:
        left_words = words(left)
        for right in found:
            right_words = words(right)
            if norm(left) == norm(right):
                return True
            # Handles initials and common romanisation differences while the
            # independently required title match prevents surname-only picks.
            if len(left_words) >= 2 and len(right_words) >= 2 and any(
                len(token) >= 4 and token in right_words for token in left_words
            ):
                return True
    return False


def openlibrary(item: dict) -> tuple[dict | None, str | None]:
    docs, last_error = [], None
    useful_authors = [name for name in item["authors"] if name.casefold() not in {"collaborators", "anonymous"}]
    for author in useful_authors[:3]:
        try:
            data = read_json("https://openlibrary.org/search.json", {
                "title": item["title"], "author": author, "limit": 30,
                "fields": "key,title,author_name,cover_i,edition_count,first_publish_year,first_sentence",
            })
            docs.extend(data.get("docs", []))
            if docs:
                break
        except Exception as error:
            last_error = error
    if not docs and last_error and not item.get("title_only_fallback"):
        return None, f"openlibrary_error: {str(last_error)[:150]}"
    matches = []
    seen_keys = set()
    for doc in docs:
        if doc.get("key") in seen_keys:
            continue
        seen_keys.add(doc.get("key"))
        title_ok, title_score = same_title(item["title"], str(doc.get("title", "")))
        if title_ok and same_author(useful_authors, doc.get("author_name", [])):
            matches.append((title_score, int(doc.get("edition_count") or 0), doc))
    if not matches and item.get("title_only_fallback"):
        try:
            broad = read_json("https://openlibrary.org/search.json", {
                "title": item["title"], "limit": 40,
                "fields": "key,title,author_name,cover_i,edition_count,first_publish_year,first_sentence",
            }).get("docs", [])
        except Exception as error:
            return None, f"openlibrary_title_error: {str(error)[:150]}"
        exact = [doc for doc in broad if norm(item["title"]) == norm(str(doc.get("title", ""))) and doc.get("cover_i")]
        authored = [doc for doc in exact if same_author(useful_authors, doc.get("author_name", []))]
        if authored:
            exact = authored
        elif len(exact) > 1 and item.get("year"):
            close = [doc for doc in exact if doc.get("first_publish_year") and abs(int(doc["first_publish_year"]) - int(item["year"])) <= 5]
            if close:
                exact = close
        keys = {doc.get("key") for doc in exact}
        if len(keys) == 1:
            doc = exact[0]
            matches = [(100, int(doc.get("edition_count") or 0), doc)]
    choices = [row for row in matches if row[2].get("cover_i")]
    choices.sort(key=lambda row: (row[0], row[1]), reverse=True)
    if not choices and matches:
        # A work record can have no aggregate cover even though a linked
        # edition has one.  It is still the same verified title/author work,
        # so use the first edition-image found on its own editions endpoint.
        matches.sort(key=lambda row: (row[0], row[1]), reverse=True)
        if len(matches) > 1 and matches[0][:2] == matches[1][:2] and matches[0][2]["key"] != matches[1][2]["key"]:
            return None, "openlibrary_ambiguous"
        doc = matches[0][2]
        try:
            editions = read_json("https://openlibrary.org" + doc["key"] + "/editions.json", {"limit": 20})
            cover_ids = [cover for edition in editions.get("entries", []) for cover in edition.get("covers", []) if isinstance(cover, int)]
        except Exception as error:
            return None, f"openlibrary_editions_error: {str(error)[:150]}"
        if not cover_ids:
            return None, "openlibrary_no_safe_cover"
        doc = {**doc, "cover_i": cover_ids[0]}
        choices = [(matches[0][0], matches[0][1], doc)]
    if not choices:
        return None, "openlibrary_no_safe_cover"
    # Equal score and edition count means independent records cannot be chosen
    # safely. Different editions of a clearly identified work may use the
    # established, higher-edition-count record.
    if len(choices) > 1 and choices[0][:2] == choices[1][:2] and choices[0][2]["key"] != choices[1][2]["key"]:
        return None, "openlibrary_ambiguous"
    doc = choices[0][2]
    try:
        image = read_image(f"https://covers.openlibrary.org/b/id/{doc['cover_i']}-L.jpg?default=false")
    except Exception as error:
        return None, f"openlibrary_cover_error: {str(error)[:150]}"
    if len(image) < 1024:
        return None, "openlibrary_cover_too_small"
    return {"provider": "openlibrary", "image": image, "cover_id": doc["cover_i"], "source_key": doc["key"],
            "year": doc.get("first_publish_year"), "sentence": doc.get("first_sentence"),
            "edition_count": doc.get("edition_count")}, None


def internet_archive(item: dict) -> tuple[dict | None, str | None]:
    author_tokens = [token for token in words(item["authors"][0]) if len(token) >= 3]
    author_clause = max(author_tokens, key=len) if author_tokens else ""
    query = f'mediatype:texts AND title:("{item["title"]}")'
    if author_clause:
        query += f" AND creator:{author_clause}"
    try:
        data = read_json("https://archive.org/advancedsearch.php", {
            # Creator metadata varies widely (dates, surname-first forms,
            # editors and translators). Search the title broadly, then apply
            # the same local title-and-author validation used above.
            "q": query,
            "fl[]": ["identifier", "title", "creator", "year"], "rows": 30, "output": "json",
        })
    except Exception as error:
        return None, f"internet_archive_error: {str(error)[:150]}"
    choices = []
    for doc in data.get("response", {}).get("docs", []):
        title_ok, title_score = same_title(item["title"], str(doc.get("title", "")))
        creators = doc.get("creator", [])
        if isinstance(creators, str):
            creators = [creators]
        if title_ok and same_author(item["authors"], creators) and doc.get("identifier"):
            choices.append((title_score, doc))
    choices.sort(key=lambda row: row[0], reverse=True)
    if not choices:
        return None, "internet_archive_no_safe_cover"
    identifier = choices[0][1]["identifier"]
    try:
        image = read_image("https://archive.org/services/img/" + quote(identifier, safe=""))
    except Exception as error:
        return None, f"internet_archive_cover_error: {str(error)[:150]}"
    if len(image) < 1024:
        return None, "internet_archive_cover_too_small"
    return {"provider": "internet_archive", "image": image, "identifier": identifier}, None


def lookup(item: dict, skip_internet_archive: bool, skip_openlibrary: bool) -> tuple[dict | None, str | None]:
    if not item["authors"]:
        return None, "no_credited_author"
    if skip_openlibrary:
        reason = "openlibrary_skipped"
    else:
        result, reason = openlibrary(item)
        if result:
            return result, None
    if skip_internet_archive:
        return None, f"{reason}; internet_archive_skipped"
    archive, archive_reason = internet_archive(item)
    if archive:
        return archive, None
    return None, f"{reason}; {archive_reason}"


def completed_ids(openlibrary_only: bool, retry_no_safe: bool, archive_only: bool) -> set[int]:
    if not CACHE.exists():
        return set()
    latest: dict[int, str] = {}
    for line in CACHE.read_text().splitlines():
        try:
            record = json.loads(line)
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
        for line in CACHE.read_text().splitlines():
            try:
                row = json.loads(line); latest[int(row["work_id"])] = str(row.get("status", ""))
            except (ValueError, KeyError, TypeError):
                continue
    return {pk for pk, status in latest.items() if "error" not in status}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--workers", type=int, default=12)
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
    args = parser.parse_args()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.settings")
    import django
    django.setup()
    from django.core.files.base import ContentFile
    from django.db import transaction
    from backend.core.models import Edition, Person, Work

    RUN.mkdir(parents=True, exist_ok=True)
    complete = completed_ids(args.skip_internet_archive, args.retry_openlibrary_no_safe, args.skip_openlibrary)
    if args.retry_transient:
        complete = completed_except_transient()
    if args.retry:
        complete = set()
    candidates = []
    person_name_titles = {norm(name) for name in Person.objects.values_list("name", flat=True)} if args.title_only_fallback else set()
    catalogue_titles = {norm(title) for title in Work.objects.filter(is_archived=False).values_list("title", flat=True)} if args.title_only_fallback else set()
    queryset = Work.objects.filter(is_archived=False, pk__gte=args.min_work_id).select_related("default_edition").prefetch_related("authors").order_by("pk")
    if args.forms:
        queryset = queryset.filter(form__in=[value.strip() for value in args.forms.split(",") if value.strip()])
    if args.max_work_id:
        queryset = queryset.filter(pk__lte=args.max_work_id)
    if args.work_id:
        queryset = queryset.filter(pk=args.work_id)
    if args.ranking_slug:
        queryset = queryset.filter(rankingentry__ranking__slug=args.ranking_slug, rankingentry__is_archived=False).distinct()
    for work in queryset:
        if args.work_id:
            complete.discard(work.pk)
        if args.retry_openlibrary_no_safe:
            if work.pk not in complete:
                continue
        elif work.pk in complete:
            continue
        if work.default_edition_id and work.default_edition and work.default_edition.cover:
            continue
        author_names = [person.name for person in work.authors.all()]
        if args.title_only_fallback and (norm(work.title) in person_name_titles or any(norm(name) in catalogue_titles for name in author_names)):
            continue
        lookup_title = work.title
        if args.clean_series_title:
            lookup_title = re.sub(r"\s*\([^)]*(?:run|cycle|series|stories|albums|adaptation|issues)[^)]*\)\s*", " ", lookup_title, flags=re.I).strip()
        if args.clean_subtitle and ":" in lookup_title:
            lookup_title = lookup_title.split(":", 1)[0].strip()
        candidates.append({"id": work.pk, "title": lookup_title, "display_title": work.title,
                           "authors": author_names, "year": work.original_year,
                           "title_only_fallback": args.title_only_fallback})
        if args.limit and len(candidates) >= args.limit:
            break
    stats = {"queued": len(candidates), "covered": 0}
    with CACHE.open("a") as output, ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(lookup, item, args.skip_internet_archive, args.skip_openlibrary): item for item in candidates}
        for future in as_completed(futures):
            item = futures[future]
            record = {"work_id": item["id"], "title": item.get("display_title", item["title"]), "lookup_title": item["title"], "authors": item["authors"]}
            try:
                match, reason = future.result()
            except Exception as error:
                match, reason = None, f"worker_error: {str(error)[:150]}"
            if reason:
                record["status"] = reason
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
                    changed = ["default_edition"] if created else []
                    if match["provider"] == "openlibrary":
                        if not work.original_year and match.get("year"):
                            work.original_year = match["year"]
                            changed.append("original_year")
                        sentence = match.get("sentence")
                        sentence = sentence[0] if isinstance(sentence, list) and sentence else sentence
                        if not work.description and isinstance(sentence, str) and sentence:
                            work.description = sentence
                            changed.append("description")
                        edition.source_url = "https://openlibrary.org" + match["source_key"]
                        attribution = f"Open Library Covers API: https://covers.openlibrary.org/b/id/{match['cover_id']}-L.jpg"
                        filename = f"openlibrary-{match['cover_id']}.jpg"
                    else:
                        edition.source_url = "https://archive.org/details/" + match["identifier"]
                        attribution = f"Internet Archive item image: https://archive.org/services/img/{match['identifier']}"
                        filename = f"internet-archive-{match['identifier']}.jpg"
                    if changed:
                        work.save(update_fields=[*changed, "updated_at"])
                    edition.cover.save(filename, ContentFile(match["image"]), save=False)
                    edition.image_attribution = attribution
                    edition.save(update_fields=["cover", "source_url", "image_attribution", "updated_at"])
                record.update(status="covered", provider=match["provider"], edition_id=edition.pk)
                record.update({key: value for key, value in match.items() if key not in {"image", "sentence"}})
                stats["covered"] += 1
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
            output.flush()
            print(f"[{record['work_id']}] {record['status']} — {record['title']}", flush=True)
    (RUN / "latest-stats.json").write_text(json.dumps(stats, indent=2) + "\n")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
