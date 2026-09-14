"""Import Benjamin McEvoy's Goodreads-derived ranking of TIME novels.

The source video explicitly announces ranks 50 through 1.  It says that the
candidate set is TIME's alphabetical 100 Best Novels selection and that the
derived order reflects Goodreads readership/rating reception rather than
objective worth or influence.  This importer therefore reuses only works
already present in ``time-100-best-novels-2005`` and publishes the completely
enumerated top 50 as a separate external ranking.

Run without ``--apply`` for a read-only reconciliation.  The apply path does
not create or alter catalogue identities, editions, media, or private data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
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

from backend.core.models import Ranking, ResearchSource
from research.import_historical_published_rankings import norm

CHECKED_ON = "2026-09-14"
SLUG = "mcevoy-time-novels-goodreads-top-50"
PARENT_SLUG = "time-100-best-novels-2005"
VIDEO_URL = "https://www.youtube.com/watch?v=lB_rjfkMCEw"
TIME_URL = "https://time.com/archive/6675063/times-100-best-novels/"
RUN = ROOT / "research" / "_runs" / CHECKED_ON / "mcevoy-time-goodreads-top-50"

TITLE = "Benjamin McEvoy · TIME novels by Goodreads reception (Top 50)"
METHOD = (
    "Benjamin McEvoy takes the novels in TIME's alphabetical 100 Best Novels "
    "selection and presents ranks 50 through 1 from a reverse ranking based on "
    "Goodreads readership/number of ratings and rating levels."
)
LIMITATION = (
    "This is a derivative Goodreads-reception ranking, not TIME's original order "
    "and not McEvoy's personal or objective literary assessment. The video does "
    "not publish the Goodreads snapshot date, values, weighting formula, or a "
    "complete bottom 50; Goodreads data can change. The spoken introduction says "
    "1923–2010, but the underlying TIME selection is explicitly 1923–2005."
)

# Exact ranks announced in the video, stored best-first for app display.
TOP_50 = """1\tTo Kill a Mockingbird\tHarper Lee
2\t1984\tGeorge Orwell
3\tThe Lord of the Rings\tJ. R. R. Tolkien
4\tThe Catcher in the Rye\tJ. D. Salinger
5\tThe Great Gatsby\tF. Scott Fitzgerald
6\tThe Lion, the Witch and the Wardrobe\tC. S. Lewis
7\tLord of the Flies\tWilliam Golding
8\tAnimal Farm\tGeorge Orwell
9\tCatch-22\tJoseph Heller
10\tThe Grapes of Wrath\tJohn Steinbeck
11\tGone with the Wind\tMargaret Mitchell
12\tSlaughterhouse-Five\tKurt Vonnegut
13\tOne Flew Over the Cuckoo's Nest\tKen Kesey
14\tA Clockwork Orange\tAnthony Burgess
15\tLolita\tVladimir Nabokov
16\tAre You There God? It's Me, Margaret\tJudy Blume
17\tWatchmen\tAlan Moore and Dave Gibbons
18\tAtonement\tIan McEwan
19\tThings Fall Apart\tChinua Achebe
20\tNever Let Me Go\tKazuo Ishiguro
21\tInvisible Man\tRalph Ellison
22\tMrs. Dalloway\tVirginia Woolf
23\tBeloved\tToni Morrison
24\tOn the Road\tJack Kerouac
25\tThe Sun Also Rises\tErnest Hemingway
26\tThe Big Sleep\tRaymond Chandler
27\tPossession\tA. S. Byatt
28\tA Passage to India\tE. M. Forster
29\tI, Claudius\tRobert Graves
30\tTheir Eyes Were Watching God\tZora Neale Hurston
31\tThe Sound and the Fury\tWilliam Faulkner
32\tAll the King's Men\tRobert Penn Warren
33\tThe Blind Assassin\tMargaret Atwood
34\tNative Son\tRichard Wright
35\tRagtime\tE. L. Doctorow
36\tLight in August\tWilliam Faulkner
37\tTo the Lighthouse\tVirginia Woolf
38\tThe French Lieutenant's Woman\tJohn Fowles
39\tThe Spy Who Came in from the Cold\tJohn le Carré
40\tThe Heart Is a Lonely Hunter\tCarson McCullers
41\tBlood Meridian\tCormac McCarthy
42\tNaked Lunch\tWilliam S. Burroughs
43\tBrideshead Revisited\tEvelyn Waugh
44\tWhite Noise\tDon DeLillo
45\tInfinite Jest\tDavid Foster Wallace
46\tRevolutionary Road\tRichard Yates
47\tSnow Crash\tNeal Stephenson
48\tMidnight's Children\tSalman Rushdie
49\tThe Prime of Miss Jean Brodie\tMuriel Spark
50\tDeath Comes for the Archbishop\tWilla Cather"""

TITLE_ALIASES = {norm("1984"): norm("Nineteen Eighty-Four")}


def source_rows() -> list[dict]:
    rows = []
    for line in TOP_50.splitlines():
        rank, title, author = line.split("\t")
        rows.append({"source_rank": int(rank), "title": title, "author": author})
    if [row["source_rank"] for row in rows] != list(range(1, 51)):
        raise RuntimeError("The source transcription must contain ranks 1–50 exactly once")
    if len({norm(row["title"]) for row in rows}) != 50:
        raise RuntimeError("The source transcription contains duplicate titles")
    return rows


def reconcile() -> list[dict]:
    parent = Ranking.objects.get(slug=PARENT_SLUG, is_archived=False)
    entries = list(
        parent.entries.filter(is_archived=False)
        .select_related("work")
        .prefetch_related("work__authors")
    )
    by_title: dict[str, list] = {}
    for entry in entries:
        by_title.setdefault(norm(entry.work.title), []).append(entry)

    mapped = []
    problems = []
    for row in source_rows():
        key = TITLE_ALIASES.get(norm(row["title"]), norm(row["title"]))
        matches = by_title.get(key, [])
        if len(matches) != 1:
            problems.append({**row, "parent_matches": len(matches)})
            continue
        entry = matches[0]
        mapped.append({
            **row,
            "work_id": entry.work_id,
            "catalog_title": entry.work.title,
            "catalog_authors": [author.name for author in entry.work.authors.all()],
        })
    if problems or len(mapped) != 50 or len({row["work_id"] for row in mapped}) != 50:
        raise RuntimeError(f"Parent-list reconciliation failed: {json.dumps(problems, ensure_ascii=False)}")
    return mapped


def ensure_definition() -> Ranking:
    ranking, created = Ranking.objects.get_or_create(slug=SLUG, defaults={
        "title": TITLE,
        "description": LIMITATION,
        "domain": "collections",
        "item_type": "work",
        "presentation": "ranked",
        "origin": "external",
        "is_public": True,
        "status": "pending_import",
        "source_url": VIDEO_URL,
        "publisher": "Benjamin McEvoy / Hardcore Literature",
        "target_size": 50,
        "scope": {},
    })
    if not created and (
        ranking.origin != "external" or ranking.owner_id or
        ranking.presentation != "ranked" or ranking.item_type != "work"
    ):
        raise RuntimeError(f"Existing target definition conflicts with {SLUG}")
    ranking.full_clean()
    return ranking


def source_records() -> list[dict]:
    return [
        {
            "source_id": "PUBLISHED-LIST-01",
            "underlying_source_id": "published-video:" + VIDEO_URL,
            "title": "The 50 Greatest Modern Novels According to Time Magazine — Reaction",
            "canonical_url": VIDEO_URL,
            "source_family": "video_reader_rating_ranking",
            "publisher": "Benjamin McEvoy / Hardcore Literature",
            "target_ids": [SLUG],
            "relevance_by_target": {
                SLUG: "Primary publication: McEvoy explicitly announces each rank from 50 through 1 and explains the Goodreads-reception method."
            },
            "evidence_notes": "Primary publication: McEvoy explicitly announces each rank from 50 through 1 and explains the Goodreads-reception method.",
            "accessed_at": CHECKED_ON,
            "eligible": True,
            "limitations": LIMITATION + " Auto-generated captions were checked against the spoken rank announcements.",
        },
        {
            "source_id": "PUBLISHED-LIST-02",
            "underlying_source_id": "underlying-selection:" + TIME_URL,
            "title": "TIME · 100 Best Novels (1923–2005) — underlying selection",
            "canonical_url": TIME_URL,
            "source_family": "underlying_editorial_selection",
            "publisher": "TIME",
            "target_ids": [SLUG],
            "relevance_by_target": {
                SLUG: "Defines the 100-novel candidate universe and confirms that TIME's own displayed selection is alphabetical rather than ranked."
            },
            "evidence_notes": "Defines the 100-novel candidate universe and confirms that TIME's own displayed selection is alphabetical rather than ranked.",
            "accessed_at": CHECKED_ON,
            "eligible": True,
            "limitations": "Underlying candidate list only; it does not independently support McEvoy's derivative Goodreads order.",
        },
    ]


def write_artifacts(mapped: list[dict], ranking: Ranking, imported: bool) -> dict:
    directory = ROOT / "research" / SLUG
    directory.mkdir(parents=True, exist_ok=True)
    reviewed_path = directory / "source-list-reviewed-20260914.json"
    reviewed_path.write_text(json.dumps([
        {key: row[key] for key in ("source_rank", "title", "author", "catalog_title", "catalog_authors", "work_id")}
        for row in mapped
    ], ensure_ascii=False, indent=2) + "\n")

    records = source_records()
    ledger = {"target_id": SLUG, "status": "named_external_list_import", "saved_at": CHECKED_ON, "sources": records}
    (directory / "sources.json").write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n")

    input_path = directory / "reviewed-contents-20260914.json"
    if not input_path.is_file():
        raise RuntimeError("The revisioned import input is missing")

    (directory / "RESEARCH.md").write_text(
        f"# {TITLE}\n\n"
        f"Status: fully imported named Published ranking (50 entries), checked {CHECKED_ON}.\n\n"
        f"Primary source: {VIDEO_URL}\n\n"
        f"Method: {METHOD}\n\n"
        "Presentation: Published ranking. Exact announced ranks 1–50 are retained; "
        "the video's reverse countdown is displayed best-first in the app. No criteria, "
        "weights, personal scores, editions, covers, or missing bottom-50 positions were invented.\n\n"
        f"Limitations: {LIMITATION}\n\n"
        "All entries reuse the established work identities in the separate TIME 100 Reading collection. "
        f"Artifacts: `{reviewed_path.name}`, `{input_path.name}`, its import receipt when changed, and `sources.json`.\n"
    )

    RUN.mkdir(parents=True, exist_ok=True)
    snapshots = {}
    for path in [
        Path("/private/tmp/youtube-lB_rjfkMCEw.html"),
        Path("/private/tmp/youtube-lB_rjfkMCEw-transcript.json"),
    ]:
        if path.is_file():
            snapshots[path.name] = {
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
    audit = {
        "checked_on": CHECKED_ON,
        "ranking_id": ranking.pk,
        "target": SLUG,
        "parent_target": PARENT_SLUG,
        "entries": len(mapped),
        "revision": ranking.revision,
        "sources": ranking.sources.filter(is_archived=False).count(),
        "imported_this_run": imported,
        "catalog_created": {"works": 0, "people": 0, "editions": 0},
        "all_work_ids_reused_from_parent": True,
        "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        "source_snapshots": snapshots,
    }
    (RUN / "publication-audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
    return audit


def apply_import(mapped: list[dict]) -> tuple[Ranking, bool]:
    with transaction.atomic():
        ranking = ensure_definition()
        desired = [(row["work_id"], row["source_rank"]) for row in mapped]
        current = list(
            ranking.entries.filter(is_archived=False)
            .order_by("position")
            .values_list("work_id", "source_rank")
        )
        imported = current != desired or ranking.status != "imported"

        directory = ROOT / "research" / SLUG
        directory.mkdir(parents=True, exist_ok=True)
        input_path = directory / "reviewed-contents-20260914.json"
        payload = {
            "target": SLUG,
            "presentation": "ranked",
            "expected_revision": ranking.revision,
            "source_checked_on": CHECKED_ON,
            "status": "imported",
            "unresolved_count": 0,
            "method_note": METHOD,
            "allow_reviewed_replacement": bool(current),
            "entries": [
                {
                    "work_id": row["work_id"],
                    "source_rank": row["source_rank"],
                    "note": f"Rank {row['source_rank']} in McEvoy's Goodreads-reception ordering of TIME's selection; credited in the source to {row['author']}.",
                }
                for row in mapped
            ],
        }
        if imported:
            input_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
            call_command("import_external_list", str(input_path))
            ranking.refresh_from_db()

        now = timezone.now()
        external_metadata = {
            "title": TITLE,
            "publisher": "Benjamin McEvoy / Hardcore Literature",
            "presentation": "ranked",
            "url": VIDEO_URL,
            "publication_date": "2024-08-17",
            "source_edition": "YouTube video published 17 August 2024",
            "method": METHOD,
            "limitation": LIMITATION,
            "display_semantics": "source_rank",
        }
        ranking.title = TITLE
        ranking.description = LIMITATION
        ranking.publisher = external_metadata["publisher"]
        ranking.source_url = VIDEO_URL
        ranking.target_size = 50
        ranking.last_researched_at = now
        ranking.last_sources_checked_at = now
        ranking.scope = {
            **ranking.scope,
            "external_metadata": external_metadata,
            "entry_semantics": "individual works from the underlying TIME selection",
            "source_entry_count": 50,
            "source_method": METHOD,
            "source_limitations": LIMITATION,
            "display_semantics": "source_rank",
            "derived_from_ranking": PARENT_SLUG,
        }
        ranking.full_clean()
        ranking.save()

        for record in source_records():
            source, created = ResearchSource.objects.get_or_create(
                ranking=ranking,
                underlying_source_id=record["underlying_source_id"],
                defaults={
                    "source_id": record["source_id"],
                    "title": record["title"],
                    "url": record["canonical_url"],
                    "family": record["source_family"],
                    "publisher": record["publisher"],
                    "evidence": record["evidence_notes"],
                    "limitations": record["limitations"],
                    "consulted_on": date.fromisoformat(CHECKED_ON),
                    "eligible": record["eligible"],
                    "metadata": record,
                },
            )
            source.full_clean()

    ranking.refresh_from_db()
    return ranking, imported


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    mapped = reconcile()
    if not args.apply:
        print(json.dumps({
            "mode": "read_only",
            "target": SLUG,
            "entries": len(mapped),
            "parent_entries": 100,
            "catalog_creations": 0,
            "ranks": [mapped[0]["source_rank"], mapped[-1]["source_rank"]],
        }, ensure_ascii=False, indent=2))
        return
    ranking, imported = apply_import(mapped)
    audit = write_artifacts(mapped, ranking, imported)
    print(json.dumps({"mode": "applied", **audit}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
