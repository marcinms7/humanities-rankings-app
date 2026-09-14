"""Repair two over-broad rules from the first added-catalog enrichment pass.

The first pass accidentally read the bibliographic subject ``Comic books`` as
the genre Comedy, and accepted first-publication years from single/very small
Open Library work records. This removes only relationships demonstrably added
by that pass and clears only low-confidence years that were absent in the
pre-write backup (or explicitly null in the newly imported source catalog).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
RUN = ROOT / "research" / "_runs" / "2026-09-14" / "catalog-added-openlibrary"
OUTCOMES = RUN / "outcomes.jsonl"
SOURCE_AUDIT = ROOT / "research" / "_runs" / "2026-09-14" / "catalog-genres" / "import-audit-v2.json"
PREWRITE = ROOT / "data" / "backups" / "manual-20260913T231019315827Z.sqlite3"
COVER_OUTCOMES = ROOT / "research" / "_runs" / "2026-09-13" / "catalog-public-cover-fallback" / "outcomes.jsonl"
NEW_SOURCE = ROOT / "research" / "comics-graphic-novels-all-time" / "owner-paste-catalog.json"


def latest_rows(path: Path) -> dict[int, dict]:
    rows = {}
    for line in path.read_text().splitlines():
        record = json.loads(line)
        rows[int(record["work_id"])] = record
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.settings")
    import django
    django.setup()
    from django.db import transaction
    from backend.core.models import Tag, Work

    latest = latest_rows(OUTCOMES)
    cover_latest = latest_rows(COVER_OUTCOMES)
    source_audit = json.loads(SOURCE_AUDIT.read_text())
    source_genres: dict[int, set[str]] = {}
    for row in source_audit["assignments"]:
        source_genres.setdefault(int(row["work_id"]), set()).update(row["mapped_genres"])

    with sqlite3.connect(PREWRITE) as connection:
        before_year = dict(connection.execute("SELECT id, original_year FROM core_work"))
    new_null_titles = {
        row["title"].casefold() for row in json.loads(NEW_SOURCE.read_text())["works"]
        if row.get("original_year") is None
    }

    comedy_repairs = []
    year_repairs = []
    for work_id, row in latest.items():
        subjects = " ".join(row.get("subjects", [])).casefold()
        if ("Comedy" in row.get("genres", []) and "Comedy" not in source_genres.get(work_id, set())
                and not re.search(r"\b(comedy|humorous)\b", subjects)):
            comedy_repairs.append({"work_id": work_id, "title": row["title"], "subjects": row.get("subjects", [])})

        year = row.get("year")
        existed_without_year = work_id in before_year and before_year[work_id] is None
        newly_imported_without_year = work_id not in before_year and row["title"].casefold() in new_null_titles
        cover_row = cover_latest.get(work_id, {})
        independently_set_by_cover_sweep = cover_row.get("status") == "covered" and cover_row.get("year") == year
        if (row.get("status") == "matched" and isinstance(year, int) and int(row.get("edition_count") or 0) < 5
                and (existed_without_year or newly_imported_without_year) and not independently_set_by_cover_sweep):
            year_repairs.append({"work_id": work_id, "title": row["title"], "year": year,
                                 "edition_count": row.get("edition_count")})

    audit = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "dry-run",
        "reason": "Correct over-broad Comic books→Comedy mapping and low-confidence first-publication years from Open Library records with fewer than five editions.",
        "comedy_relationships": comedy_repairs,
        "low_confidence_years": year_repairs,
    }
    if args.apply:
        with transaction.atomic():
            comedy = Tag.objects.get(name="Comedy", kind="genre")
            for row in comedy_repairs:
                Work.tags.through.objects.filter(work_id=row["work_id"], tag_id=comedy.pk).delete()
            for row in year_repairs:
                Work.objects.filter(pk=row["work_id"], original_year=row["year"]).update(original_year=None)

    output = RUN / ("repair-audit.json" if args.apply else "repair-dry-run.json")
    output.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"comedy_relationships": len(comedy_repairs), "low_confidence_years": len(year_repairs), "audit": str(output.relative_to(ROOT))}, indent=2))


if __name__ == "__main__":
    main()
