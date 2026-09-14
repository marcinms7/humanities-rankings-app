#!/usr/bin/env python3
"""Prepare a revisioned import of the owner's laughter-weighted Funny Books report.

This is deliberately a narrow, file-driven reconciler.  It does not conduct
new research or alter the target's source ledger: the supplied revision says
that the same 150 works and 351 source documents are retained.  It verifies
that assertion against the active target before making an editorial-selection
payload for the normal guarded publishing command.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.settings")
import django
django.setup()

from backend.core.models import Ranking, Work


TARGET = "books-funniest-all-time"
RECEIVED = "2026-09-14"
INTAKE_DIR = ROOT / "research" / "incoming" / TARGET / "2026-09-14-laughter-70-revision"
TARGET_DIR = ROOT / "research" / TARGET


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def line(block: str, label: str) -> str:
    found = re.search(rf"(?m)^{re.escape(label)}:\s*(.+)$", block)
    return found.group(1).strip() if found else ""


def parse_sources(text: str) -> dict[str, dict[str, str]]:
    heading = re.search(r"(?m)^SOURCE LEDGER — 351 DISTINCT DOCUMENTS\s*$", text)
    if not heading:
        raise ValueError("The 351-document source-ledger heading was not found.")
    ledger = text[heading.end():]
    matches = list(re.finditer(r"(?m)^\[S(\d{3})\]\s+(.+?)\s*$", ledger))
    sources: dict[str, dict[str, str]] = {}
    for index, match in enumerate(matches):
        block = ledger[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(ledger)]
        url = line(block, "URL")
        if not url.startswith(("https://", "http://")):
            raise ValueError(f"S{match.group(1)} has no direct HTTP(S) URL.")
        source_id = f"FUNNY-S{match.group(1)}"
        if source_id in sources:
            raise ValueError(f"Repeated source identifier {source_id}.")
        sources[source_id] = {"title": match.group(2).strip(), "url": url.rstrip(".,;")}
    if len(sources) != 351:
        raise ValueError(f"Expected 351 sources, parsed {len(sources)}.")
    return sources


def parse_entries(text: str) -> list[dict[str, object]]:
    heading = re.search(r"(?m)^RANKED TOP 150 — LAUGHTER WEIGHTED AT 70%\s*$", text)
    ledger = re.search(r"(?m)^SOURCE LEDGER — 351 DISTINCT DOCUMENTS\s*$", text)
    if not heading or not ledger or ledger.start() <= heading.end():
        raise ValueError("The revised ranking or source-ledger boundary was not found.")
    ranking = text[heading.end():ledger.start()]
    matches = list(re.finditer(r"(?m)^(\d{3})\.\s+(.+?)\s+—\s+(.+?)\s*$", ranking))
    entries: list[dict[str, object]] = []
    for index, match in enumerate(matches):
        position = int(match.group(1))
        block = ranking[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(ranking)]
        score = re.search(r"Laughter estimate:\s*([\d.]+)/10\s*\|\s*Weighted total:\s*([\d.]+)/10\s*\|\s*Previous rank:\s*(\d{3})", block)
        components = line(block, "Other editorial components /10")
        approach = line(block, "Comic approach")
        why = line(block, "Why here with laughter at 70%")
        source_ids = [f"FUNNY-S{number}" for number in re.findall(r"\[S(\d{3})\]", line(block, "Sources"))]
        if not score or not approach or not why or not source_ids:
            raise ValueError(f"Rank {position} is missing scores, rationale, or source references.")
        entries.append({
            "position": position,
            "title": match.group(2).strip(),
            "author": match.group(3).strip(),
            "date": line(block, "Date"),
            "form": line(block, "Form"),
            "tradition": line(block, "Tradition"),
            "laughter": score.group(1),
            "weighted_total": score.group(2),
            "previous_rank": score.group(3),
            "components": components,
            "approach": approach,
            "why": why,
            "context": line(block, "Edition/context"),
            "source_ids": source_ids,
        })
    entries.sort(key=lambda entry: int(entry["position"]))
    if [entry["position"] for entry in entries] != list(range(1, 151)):
        raise ValueError(f"Expected consecutive positions 1–150, parsed {len(entries)} entries.")
    return entries


def reconcile(entries: list[dict[str, object]], sources: dict[str, dict[str, str]]) -> dict:
    ranking = Ranking.objects.get(slug=TARGET, origin="curated", owner__isnull=True, is_archived=False)
    if ranking.revision != 2:
        raise ValueError(f"Expected target revision 2, found {ranking.revision}; refuse stale update.")
    active = ranking.entries.filter(is_archived=False).select_related("work").prefetch_related("work__authors")
    if active.count() != 150:
        raise ValueError(f"Expected 150 active target entries, found {active.count()}.")
    works: dict[tuple[str, str], Work] = {}
    works_by_title: dict[str, list[Work]] = {}
    for entry in active:
        work = entry.work
        works_by_title.setdefault(normalized(work.title), []).append(work)
        authors = {normalized(author.name) for author in work.authors.all()}
        for author in authors:
            key = (normalized(work.title), author)
            if key in works:
                raise ValueError(f"Ambiguous existing work identity for {work.title}.")
            works[key] = work
    active_sources = ranking.sources.filter(is_archived=False)
    known_sources = set(active_sources.values_list("source_id", flat=True))
    eligible_sources = set(active_sources.filter(eligible=True).values_list("source_id", flat=True))
    missing_report_sources = set(sources) - known_sources
    if missing_report_sources:
        raise ValueError(f"The existing source ledger is missing report sources: {sorted(missing_report_sources)[:8]}")
    report_urls = {source_id: source["url"] for source_id, source in sources.items()}
    saved_urls = dict(active_sources.filter(source_id__in=sources).values_list("source_id", "url"))
    changed_urls = [source_id for source_id, url in report_urls.items() if saved_urls.get(source_id) != url]
    if changed_urls:
        raise ValueError(f"Source URLs differ from the retained ledger (first: {changed_urls[:8]}). Source changes need separate review.")

    payload_entries: list[dict] = []
    seen_work_ids: set[int] = set()
    for record in entries:
        key = (normalized(str(record["title"])), normalized(str(record["author"])))
        work = works.get(key)
        if work is None:
            title_matches = works_by_title.get(key[0], [])
            # The supplied report occasionally reverses co-author order.  A
            # title-only fallback is safe only when the active target has one
            # unique identity with that title; it never edits its attribution.
            if len(title_matches) == 1:
                work = title_matches[0]
        if work is None:
            raise ValueError(f"No active target work matches rank {record['position']}: {record['title']} — {record['author']}")
        if work.pk in seen_work_ids:
            raise ValueError(f"The report maps more than once to {work.title}.")
        seen_work_ids.add(work.pk)
        unknown_refs = set(record["source_ids"]) - known_sources
        if unknown_refs:
            raise ValueError(f"Rank {record['position']} has unresolved evidence: {sorted(unknown_refs)}")
        eligible_refs = [source_id for source_id in record["source_ids"] if source_id in eligible_sources]
        needs_prior_supplement = False
        if not eligible_refs:
            prior = ranking.scope.get("editorial", {}).get("entries", {}).get(str(work.pk), {})
            eligible_refs = [source.get("source_id") for source in prior.get("sources", [])
                             if source.get("source_id") in eligible_sources]
            if not eligible_refs:
                raise ValueError(f"Rank {record['position']} has no eligible report citation or retained direct supplement.")
            needs_prior_supplement = True
        standing = (
            f"Position {record['position']} in the owner-supplied 14 September 2026 laughter-weighted revision. "
            f"Laughter estimate {record['laughter']}/10; weighted editorial total {record['weighted_total']}/10 "
            f"(previous rank {record['previous_rank']}). {record['approach']} {record['why']}"
        )
        reading = (
            f"Laughter estimate {record['laughter']}/10 under the report's 70% laughter weighting. "
            f"{record['approach']} {record['why']}"
        )
        caveat = (
            f"{record['context'] + ' ' if record['context'] else ''}"
            f"Other editorial components /10: {record['components']}. The scores and exact position are transparent editorial estimates, "
            "not measurements or claims that any cited source endorses this precise order."
            + (" The report's cited documents for this entry remain visible below as uncounted leads; the retained direct supplement supplies the app's eligible evidence link."
               if needs_prior_supplement else "")
        )
        payload_entries.append({
            "key": f"funniest-laughter70-{work.pk}",
            "item_id": work.pk,
            "source_ids": eligible_refs,
            "reported_source_ids": list(dict.fromkeys([*record["source_ids"], *eligible_refs])),
            "standing": standing,
            "reading": reading,
            "caveat": caveat,
            "metadata_status": "edition_and_media_pending",
            "source_positions": [],
        })
    if seen_work_ids != {entry.work_id for entry in active}:
        raise ValueError("The revised report does not map one-to-one to the active target works.")
    keys = [record["key"] for record in payload_entries]
    return {
        "target": TARGET,
        "expected_revision": 2,
        "allow_expansion": True,
        "version": "owner-chat-funniest-books-top-150-laughter-70-2026-09-14",
        "published_on": RECEIVED,
        "allow_pending_metadata": True,
        "reviewed_exclusions": [],
        "notice": "Revised edition: the same 150 works and 351 source documents are retained, but the published order now gives sustained laughter 70% of its explicit editorial weighting. Small score gaps are close calls, not measured differences.",
        "method": "Owner-supplied revised global humour synthesis (14 September 2026). It explicitly weights laughter 70%; comic invention 9%; literary quality 7%; influence 5%; tradition-specific achievement 5%; cultural reach 2%; and translation/cross-language reception 2%. The report says it targeted consequential changes with rereading of existing evidence rather than adding a fresh exhaustive corpus. Its numerical components are transparent editorial estimates, not empirical laugh counts or personal scores.",
        "entries": payload_entries,
        "orders": {
            "standing": {"label": "Laughter-weighted order", "description": "The report's revised 70%-laughter editorial order; close score gaps are not scientific measurements.", "keys": keys},
            "reading": {"label": "Reading experience (same order)", "description": "No separate reading-value order was supplied, so this keeps the transparent laughter-weighted sequence.", "keys": keys},
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--write", action="store_true", help="Preserve original and write reviewed selection JSON after validation.")
    args = parser.parse_args()
    raw = args.report.read_bytes()
    text = raw.decode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    sources = parse_sources(text)
    entries = parse_entries(text)
    payload = reconcile(entries, sources)
    print(f"Validated {len(entries)} entries and {len(sources)} unchanged report sources; SHA-256={digest}")
    if not args.write:
        return
    INTAKE_DIR.mkdir(parents=True, exist_ok=True)
    destination = INTAKE_DIR / "report.txt"
    if destination.exists() and destination.read_bytes() != raw:
        raise ValueError(f"Refusing to replace a different preserved report at {destination}.")
    if not destination.exists():
        shutil.copyfile(args.report, destination)
    (INTAKE_DIR / "RECEIPT.md").write_text(
        "# Owner attachment receipt\n\n"
        f"- Received: {RECEIVED}\n"
        "- Requested action: revise the existing funniest-books order using the owner-supplied 70% laughter weighting.\n"
        f"- Original attachment: `{args.report}`\n"
        f"- SHA-256: `{digest}`\n"
        "- Parsed: 150 ranked works and 351 direct-URL source records.\n"
        "- Reconciliation: every report work and source URL matches the active target one-to-one; no works or source records were added, removed, or overwritten.\n"
        "- Caveat: this file-driven revision preserves the report's stated targeted rereading and access limits; source pages were not independently revisited during intake.\n"
    )
    output = TARGET_DIR / "owner-chat-selection-laughter-70-2026-09-14.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote preserved report and revision payload: {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
