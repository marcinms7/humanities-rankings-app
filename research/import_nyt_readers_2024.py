"""Import the New York Times readers' 100 Best Books of the 21st Century.

Without ``--apply`` this performs a read-only catalogue reconciliation.  The
apply path creates only missing public identities and publishes through the
revision-aware external-list importer.  Existing and private data are not
deleted or replaced.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.settings")

import django

django.setup()

from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from backend.core.models import Person, Ranking, ResearchSource, Work
from research.import_community_published_rankings import proposed_form, split_authors, title_keys
from research.import_recommended_published_rankings import make_indexes, resolve_work, unorm

CHECKED_ON = "2026-09-14"
SLUG = "new-york-times-readers-best-books-21st-century-2024"
TITLE = "The New York Times · Readers' 100 Best Books of the 21st Century (2024)"
PRIMARY_URL = "https://www.nytimes.com/interactive/2024/books/reader-best-books-21st-century.html"
MIRROR_URL = "https://thegreatestbooks.org/lists/432"
SOURCE_SNAPSHOT = ROOT / "research" / "_runs" / "2026-09-13" / "supplied-corpus" / "b509be258f28654cc244c33adacfdef4c31ab6739133101260f4f4bc29f465d4.json"
DIRECTORY = ROOT / "research" / SLUG
RUN = ROOT / "research" / "_runs" / CHECKED_ON / "nyt-readers-2024"
METHOD = ("All 100 positions from the New York Times Book Review's 2024 reader companion to its expert list; "
          "the publisher reports 39 titles overlapping the two lists.")
LIMITATION = ("Reader popularity within the New York Times audience and a 2000–2024 publication window; this is not the "
              "Book Review's expert ordering. Automated access to the primary interactive was blocked during this run, so "
              "the complete row order was transcribed from a previously saved independent mirror and checked against the "
              "publisher's identified list and description.")

REVIEWED_WORK_IDS = {
    20: 1172,  # Source uses "and"; established catalogue title uses ampersand.
    51: 2681,  # Source shortens Caste: The Origins of Our Discontents.
}


def reviewed_path() -> Path:
    return DIRECTORY / "source-list-reviewed-20260914.json"


def parse_source() -> list[dict]:
    if reviewed_path().exists():
        return json.loads(reviewed_path().read_text())
    payload = json.loads(SOURCE_SNAPSHOT.read_text())
    text = payload["text"]
    start = text.find("Demon Copperhead\nby Barbara Kingsolver")
    if start < 0:
        raise RuntimeError("NYT readers list start marker not found")
    text = text[start:]
    markers = list(re.finditer(r"\nThe \d+(?:st|nd|rd|th) Greatest Book of All Time\n", text))
    rows, previous = [], 0
    for rank, marker in enumerate(markers, 1):
        block = text[previous:marker.start()]
        authors = list(re.finditer(r"(?m)^by (.+)$", block))
        if not authors:
            raise RuntimeError(f"Missing author marker at position {rank}")
        author_marker = authors[-1]
        title = block[:author_marker.start()].rstrip().splitlines()[-1].strip()
        author = author_marker.group(1).strip()
        rows.append({"source_rank": rank, "title": title, "author": author,
                     "source_title": title, "source_credits": author})
        previous = marker.end()
    if len(rows) != 100 or [row["source_rank"] for row in rows] != list(range(1, 101)):
        raise RuntimeError(f"Expected complete positions 1–100, got {len(rows)}")
    return rows


def ensure_ranking():
    ranking, created = Ranking.objects.get_or_create(slug=SLUG, defaults={
        "title": TITLE, "origin": "external", "presentation": "ranked", "domain": "collections",
        "item_type": "work", "is_public": True, "source_url": PRIMARY_URL,
        "publisher": "The New York Times Book Review", "status": "pending_import",
        "description": LIMITATION,
        "scope": {"external_metadata": {"family": "public_poll", "method": METHOD,
                                           "limitation": LIMITATION, "url": PRIMARY_URL}},
    })
    if created:
        ranking.full_clean()
    return ranking


def prepare(apply: bool):
    rows = parse_source()
    unicode_index, latin_index = make_indexes()
    people_index = defaultdict(list)
    for person in Person.objects.filter(is_archived=False):
        people_index[unorm(person.name)].append(person)
    mapped, created_works, created_people, problems = [], [], [], []
    with transaction.atomic():
        if apply:
            ensure_ranking()
        used = set()
        for row in rows:
            reviewed_id = REVIEWED_WORK_IDS.get(row["source_rank"])
            if reviewed_id:
                work, resolution = Work.objects.get(pk=reviewed_id, is_archived=False), "reviewed_alias_choice"
            else:
                work, resolution = resolve_work(SLUG, row, unicode_index, latin_index)
            if work is None and resolution.startswith("ambiguous"):
                problems.append({**row, "reason": resolution})
                continue
            if work is None and not apply:
                mapped.append({**row, "work_id": None, "resolution": "would_create"})
                continue
            if work is None:
                authors = []
                for name in split_authors(row["author"]):
                    candidates = people_index[unorm(name)]
                    person = min(candidates, key=lambda value: value.pk) if candidates else None
                    if person is None:
                        person = Person(name=name, source_url=PRIMARY_URL)
                        person.full_clean(); person.save()
                        people_index[unorm(name)].append(person)
                        created_people.append({"id": person.pk, "name": name})
                    authors.append(person)
                work = Work(title=row["title"], form=proposed_form(row["title"]), field="literature",
                            description=f"Source-defined entry in {TITLE}; edition and cover metadata pending.")
                work.full_clean(); work.save(); work.authors.set(authors)
                unicode_index[unorm(work.title)].append(work)
                for key in title_keys(work.title):
                    latin_index[key].append(work)
                created_works.append({"id": work.pk, "title": work.title,
                                      "authors": [author.name for author in authors]})
                resolution = "created"
            if work.pk in used:
                problems.append({**row, "reason": f"duplicate_work:{work.pk}"})
                continue
            used.add(work.pk)
            mapped.append({**row, "work_id": work.pk, "resolution": resolution})
        if problems:
            raise RuntimeError(f"Resolve {len(problems)} rows before import: {problems[:20]}")
        if not apply:
            transaction.set_rollback(True)
    return {"mapped": mapped, "created_works": created_works, "created_people": created_people,
            "would_create": sum(row["resolution"] == "would_create" for row in mapped)}


def save_and_import(result):
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    RUN.mkdir(parents=True, exist_ok=True)
    source_rows = [{key: row[key] for key in ("source_rank", "title", "author", "source_title", "source_credits")}
                   for row in result["mapped"]]
    reviewed_path().write_text(json.dumps(source_rows, ensure_ascii=False, indent=2) + "\n")
    sources = [
        {"source_id": "PUBLISHED-LIST-01", "underlying_source_id": "published-list:" + PRIMARY_URL,
         "title": TITLE + " — primary interactive", "canonical_url": PRIMARY_URL,
         "source_family": "public_poll", "publisher": "The New York Times Book Review",
         "evidence_notes": "Identifies the publisher, scope, reader-list status and relationship to the expert list.",
         "limitations": "The primary interactive returned an automated-access block during this run; its row order was checked through the saved transcription mirror.",
         "eligible": False},
        {"source_id": "PUBLISHED-LIST-02", "underlying_source_id": "published-list:" + MIRROR_URL,
         "title": TITLE + " — complete transcription mirror", "canonical_url": MIRROR_URL,
         "source_family": "list_transcription", "publisher": "The Greatest Books",
         "evidence_notes": "Complete row-level transcription used for all 100 source positions, titles and authors.",
         "limitations": "Dependent transcription of the New York Times list, not an independent vote or opinion source.",
         "eligible": True},
    ]
    ledger = {"target_id": SLUG, "status": "named_external_list_import", "saved_at": CHECKED_ON,
              "sources": [{**source, "target_ids": [SLUG],
                           "relevance_by_target": {SLUG: source["evidence_notes"]},
                           "accessed_at": CHECKED_ON} for source in sources]}
    (DIRECTORY / "sources.json").write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n")
    ranking = Ranking.objects.get(slug=SLUG)
    entries = [{"work_id": row["work_id"], "source_rank": row["source_rank"],
                "note": f"{row['source_credits']} — source-defined reader-list entry"} for row in result["mapped"]]
    payload = {"target": SLUG, "presentation": "ranked", "expected_revision": ranking.revision,
               "source_checked_on": CHECKED_ON, "status": "imported", "unresolved_count": 0,
               "method_note": METHOD, "allow_reviewed_replacement": ranking.entries.filter(is_archived=False).exists(),
               "entries": entries}
    input_path = DIRECTORY / "reviewed-contents-20260914.json"
    input_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    call_command("import_external_list", str(input_path))
    ranking.refresh_from_db()
    now = timezone.now()
    ranking.target_size = 100
    ranking.last_researched_at = now
    ranking.last_sources_checked_at = now
    ranking.description = LIMITATION
    ranking.scope = {**ranking.scope, "entry_semantics": "publisher-defined books",
                     "source_entry_count": 100, "source_expected_count": 100,
                     "source_unresolved_count": 0, "source_method": METHOD, "source_limitations": LIMITATION}
    ranking.full_clean(); ranking.save()
    for source_record in sources:
        source, created = ResearchSource.objects.get_or_create(
            ranking=ranking, underlying_source_id=source_record["underlying_source_id"],
            defaults={"source_id": source_record["source_id"], "title": source_record["title"],
                      "url": source_record["canonical_url"], "family": source_record["source_family"],
                      "publisher": source_record["publisher"], "evidence": source_record["evidence_notes"],
                      "limitations": source_record["limitations"], "consulted_on": date.fromisoformat(CHECKED_ON),
                      "eligible": source_record["eligible"], "metadata": source_record})
        if created:
            source.full_clean()
    (DIRECTORY / "RESEARCH.md").write_text(
        f"# {TITLE}\n\nStatus: fully imported named Published ranking (100 entries), checked {CHECKED_ON}.\n\n"
        f"Primary source: {PRIMARY_URL}\n\nTranscription: {MIRROR_URL}\n\nMethod: {METHOD}\n\n"
        "All source positions are retained separately from the existing New York Times expert ranking and from Marginalia's "
        "curated or personal assessments. No criteria, weights or private scores were assigned.\n\n"
        f"Limitations: {LIMITATION}\n\nArtifacts: `{reviewed_path().name}`, `{input_path.name}`, its import receipt, and `sources.json`.\n")
    audit = {"checked_on": CHECKED_ON, "target": SLUG, "ranking_id": ranking.pk,
             "entries": ranking.entries.filter(is_archived=False).count(), "revision": ranking.revision,
             "sources": ranking.sources.filter(is_archived=False).count(),
             "eligible_sources": ranking.sources.filter(is_archived=False, eligible=True).count(),
             "created_works": result["created_works"], "created_people": result["created_people"],
             "source_snapshot": {"path": str(SOURCE_SNAPSHOT.relative_to(ROOT)),
                                 "bytes": SOURCE_SNAPSHOT.stat().st_size,
                                 "sha256": hashlib.sha256(SOURCE_SNAPSHOT.read_bytes()).hexdigest()},
             "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest()}
    (RUN / "publication-audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        result = prepare(False)
        print(json.dumps({"mode": "read_only", "entries": len(result["mapped"]),
                          "would_create": result["would_create"]}, ensure_ascii=False, indent=2))
        return
    with transaction.atomic():
        result = prepare(True)
        save_and_import(result)
    print(json.dumps({"mode": "applied", "entries": len(result["mapped"]),
                      "created_works": len(result["created_works"]),
                      "created_people": len(result["created_people"])}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
