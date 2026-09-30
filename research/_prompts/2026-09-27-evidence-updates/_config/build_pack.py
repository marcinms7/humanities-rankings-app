"""Export shared research handoffs. Reads SQLite in a read-only transaction."""
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parents[1]
CONFIG = OUT / "_config"
PART_LIMIT = 60_000


def js(value, pretty=False):
    return json.dumps(value, ensure_ascii=False, indent=2 if pretty else None)


def parsed(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            pass
    return value


def chosen(row, keys):
    return {k: row[k] for k in keys}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    config = {}
    for name in ("broad.json", "genres.json", "country_topics.json"):
        group = json.loads((CONFIG / name).read_text())
        assert not set(group) & set(config), f"Duplicate configs: {name}"
        config.update(group)
    common = (CONFIG / "common-instructions.txt").read_text().strip()
    connection = sqlite3.connect((ROOT / "data/db.sqlite3").as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("BEGIN")
    captured_at = datetime.now(timezone.utc).isoformat()
    rankings = [dict(r) for r in connection.execute(
        "SELECT * FROM core_ranking WHERE origin='curated' AND owner_id IS NULL AND is_archived=0 ORDER BY title,id"
    )]
    assert {r["slug"] for r in rankings} == set(config), "Config coverage differs from active curated rankings"
    audit_file = Path("/private/tmp/marginalia-ranking-evidence-audit-2026-09-27.csv")
    audit_rows = {r["slug"]: r for r in csv.DictReader(audit_file.open())}
    (OUT / "evidence-audit.csv").write_bytes(audit_file.read_bytes())
    for directory in ("prompts", "snapshots", "paste-parts"):
        (OUT / directory).mkdir(exist_ok=True)
    catalog_cache = {}

    def person(pid):
        r = connection.execute("SELECT * FROM core_person WHERE id=?", (pid,)).fetchone()
        if not r:
            return {"id": pid, "missing_catalog_record": True}
        p = chosen(r, ("id", "name", "biography", "countries", "source_url", "image_attribution", "is_archived"))
        p["countries"] = parsed(p["countries"])
        p["has_saved_portrait"] = bool(r["portrait"])
        return p

    def item(kind, iid):
        key = (kind, iid)
        if key in catalog_cache:
            return catalog_cache[key]
        if kind == "person":
            value = person(iid)
        else:
            r = connection.execute("SELECT * FROM core_work WHERE id=?", (iid,)).fetchone()
            if not r:
                return {"id": iid, "missing_catalog_record": True}
            value = chosen(r, ("id", "title", "form", "field", "original_year", "original_language", "countries", "description", "contained_in_id", "is_archived"))
            value["countries"] = parsed(value["countries"])
            value["authors"] = [person(a[0]) for a in connection.execute(
                "SELECT person_id FROM core_work_authors WHERE work_id=? ORDER BY id", (iid,))]
            edition = connection.execute("SELECT * FROM core_edition WHERE id=?", (r["default_edition_id"],)).fetchone()
            value["default_edition"] = None
            if edition:
                value["default_edition"] = chosen(edition, ("id", "language", "translator", "publisher", "isbn", "pages", "word_count", "abridged", "translation_notes", "source_url", "image_attribution", "is_archived"))
                value["default_edition"]["has_saved_cover"] = bool(edition["cover"])
        catalog_cache[key] = value
        return value

    manifest = []
    for rank in rankings:
        slug = rank["slug"]
        scope = parsed(rank["scope"])
        editorial = scope.get("editorial", {})
        editorial_entries = editorial.get("entries", {})
        entries = []
        for raw in connection.execute("SELECT * FROM core_rankingentry WHERE ranking_id=? AND is_archived=0 ORDER BY position,id", (rank["id"],)):
            e = dict(raw)
            e["groupings"] = parsed(e["groupings"])
            e["assessments"] = parsed(e["assessments"])
            iid = e["work_id"] if e["work_id"] is not None else e["person_id"]
            e["catalog_item"] = item(rank["item_type"], iid)
            e["editorial_mapping"] = editorial_entries.get(str(iid))
            entries.append(e)
        active_ids = {str(e["catalog_item"]["id"]) for e in entries}
        orphans = [{"item_id": key, "catalog_item": item(rank["item_type"], int(key)), "editorial_mapping": value}
                   for key, value in editorial_entries.items() if key not in active_ids]
        sources = []
        for raw in connection.execute("SELECT * FROM core_researchsource WHERE ranking_id=? ORDER BY id", (rank["id"],)):
            s = dict(raw)
            s["metadata"] = parsed(s["metadata"])
            s["eligible"] = bool(s["eligible"])
            s["is_archived"] = bool(s["is_archived"])
            sources.append(s)
        by_sid = {s["source_id"]: s for s in sources}
        assert len(by_sid) == len(sources), f"Duplicate target source IDs: {slug}"
        ledger_file = ROOT / "research" / slug / "sources.json"
        ledger_notes = {"path": f"research/{slug}/sources.json", "exists": ledger_file.exists()}
        supplements = []
        if ledger_file.exists():
            ledger = json.loads(ledger_file.read_text())
            ledger_sources = ledger.get("sources", []) if isinstance(ledger, dict) else ledger
            ledger_notes["record_count"] = len(ledger_sources)
            ledger_notes["sha256"] = digest(ledger_file)
            for record in ledger_sources:
                sid = record.get("source_id")
                url = record.get("canonical_url") or record.get("url") or record.get("access_url")
                db = by_sid.get(sid)
                if db is None or (url and url != db["url"]):
                    supplements.append({"namespace": "file-ledger", "reason": "source_id absent from database" if db is None else "same source_id identifies a different URL in the database", "record": record})
        ledger_notes["supplementary_conflict_records"] = len(supplements)
        citation_stubs = {}
        for mapping in editorial_entries.values():
            for citation in mapping.get("sources", []):
                sid = citation.get("source_id") if isinstance(citation, dict) else citation
                if sid and sid not in by_sid:
                    citation_stubs[sid] = citation
        for e in entries:
            for grouping in e["groupings"]:
                for sid in grouping.get("source_ids", []):
                    if sid not in by_sid:
                        citation_stubs.setdefault(sid, {"source_id": sid})
        audit = audit_rows[slug]
        assert int(audit["entries"]) == len(entries), f"Entry counts changed since audit: {slug}"
        assert int(audit["registered_sources"]) == sum(not s["is_archived"] for s in sources), f"Source counts changed since audit: {slug}"
        definition = chosen(rank, ("id", "slug", "title", "description", "domain", "item_type", "presentation", "origin", "target_size", "status", "source_url", "publisher", "last_researched_at", "last_sources_checked_at", "revision"))
        definition["criteria"] = parsed(rank["criteria"])
        definition["scope"] = scope
        snapshot = {"snapshot_at_utc": captured_at, "snapshot_kind": "shared curated research only; no private records", "ranking": definition, "entries": entries, "orphaned_editorial_mappings": orphans, "source_records": sources, "current_file_ledger_reconciliation": ledger_notes, "supplementary_file_ledger_records": supplements, "unregistered_citation_stubs": citation_stubs, "prior_audit": audit}
        snapshot_path = OUT / "snapshots" / f"{slug}.json"
        snapshot_path.write_text(js(snapshot, True) + "\n")

        cfg = config[slug]
        parts = [f"SELF-CONTAINED RANKING UPDATE REQUEST\nTARGET: {rank['title']}\nTARGET ID: {slug}\nSNAPSHOT: {captured_at}\nMODE: update an existing research synthesis\nCURRENT SIZE: {len(entries)} distinct entries\nCURRENT REGISTER: {len(sources)} source records; {sum(s['eligible'] and not s['is_archived'] for s in sources)} stored as eligible (historical flags, subject to audit)\nDESIRED SCOPE: {cfg['desired_scope']}\n\n{common}"]
        parts.append("TARGET-SPECIFIC FINDINGS AND WORK\n\n" + cfg["issue_summary"] + "\n\n" + "\n".join(f"{i}. {t}" for i, t in enumerate(cfg["tasks"], 1)))
        if supplements:
            parts.append(f"ADDITIONAL SOURCE-IDENTITY CONFLICT\nThe current file ledger has {len(supplements)} records with IDs missing from the database or matching different database URLs. They are included in a separate file-ledger namespace below. Compare actual URLs/identities before repairing citations. Never merge records solely by source-ID string. Database metadata can retain the old ledger ID as well; preserve and explicitly reconcile that disagreement.")
        if orphans:
            parts.append(f"ORPHAN MAPPING WARNING\n{len(orphans)} saved editorial mappings refer to item IDs outside the current active entry list. Their catalog identities and notes are included after the current entries. Saved alternate orders may still contain those IDs. Treat this as a repair task, not evidence that the old item should be restored without verification.")
        brief_definition = {k: v for k, v in definition.items() if k != "scope"}
        brief_definition["scope"] = {k: v for k, v in scope.items() if k != "editorial"}
        brief_definition["historical_editorial_method_and_notes"] = {k: v for k, v in editorial.items() if k not in ("entries", "orders")}
        parts.append("CURRENT TARGET DEFINITION AND HISTORICAL METHOD\n" + js(brief_definition, True))
        parts.append("CURRENT SAVED EDITORIAL ORDERS\nItem IDs below resolve to the complete current entries or the explicit orphan mapping appendix. A saved order is historical, not a requirement to retain the same order. For unranked/country-grouped records, these are display sequences, not global merit positions.\n" + js(editorial.get("orders", {}), True))
        parts.append(f"COMPLETE CURRENT ENTRY LIST: {len(entries)} ENTRIES\nDatabase position is the current saved display order; separate editorial views appear above. Saved bibliographic metadata is not independently reverified by this export.")
        for e in entries:
            obj = e["catalog_item"]
            heading = obj.get("title", obj.get("name", "Missing catalog record"))
            authors = "; ".join(a.get("name", "unknown") for a in obj.get("authors", []))
            record = {"entry_id": e["id"], "item_type": rank["item_type"], "item_id": obj["id"], "source_rank": e["source_rank"], "rationale": e["rationale"], "assessments": e["assessments"], "catalog": obj, "editorial_evidence_and_rationales": e["editorial_mapping"], "country_groupings": e["groupings"]}
            parts.append(f"ENTRY {e['position']} | {rank['item_type']}:{obj['id']} | {heading}" + (f" — {authors}" if authors else "") + "\n" + js(record))
        if orphans:
            parts.append("ORPHANED HISTORICAL EDITORIAL MAPPINGS\nThese are not extra current entries. Reconcile their identity/citations with the active list before use.")
            for orphan in orphans:
                parts.append("ORPHAN ITEM " + str(orphan["item_id"]) + "\n" + js(orphan))
        parts.append(f"COMPLETE CURRENT DATABASE SOURCE REGISTER: {len(sources)} RECORDS\nNamespace: current-db. Includes eligible, ineligible and any archived records. Evidence and access claims are supplied historical notes. No source was newly visited when this prompt was exported.")
        for s in sources:
            record = chosen(s, ("source_id", "title", "url", "family", "publisher", "evidence", "limitations", "consulted_on", "eligible", "underlying_source_id", "is_archived"))
            metadata = s["metadata"]
            if isinstance(metadata, dict):
                redundant = {"source_id": "source_id", "title": "title", "canonical_url": "url", "access_url": "url", "url": "url", "source_family": "family", "publisher": "publisher", "evidence_notes": "evidence", "disagreement_or_limitations": "limitations", "limitations": "limitations", "accessed_at": "consulted_on", "count_eligible": "eligible", "underlying_source_id": "underlying_source_id"}
                metadata = {k: v for k, v in metadata.items() if not (k in redundant and v == record[redundant[k]])}
                if metadata.get("target_ids") == [slug]:
                    metadata.pop("target_ids")
                if metadata.get("relevance_by_target") == {slug: s["evidence"]}:
                    metadata.pop("relevance_by_target")
            record["additional_saved_metadata"] = metadata
            parts.append(f"SOURCE [{s['source_id']}] — {s['title']}\n{s['url']}\n" + js(record))
        if supplements:
            parts.append(f"SUPPLEMENTARY CURRENT FILE-LEDGER CONFLICTS: {len(supplements)} RECORDS\nNamespace: file-ledger. These are alternative mappings, not automatically additional unique evidence. Current-db remains the displayed baseline; reconcile by actual source identity and URL.\n" + js(ledger_notes))
            for supplement in supplements:
                parts.append("FILE-LEDGER RECORD\n" + js(supplement))
        if citation_stubs:
            parts.append("UNREGISTERED CITATION STUBS\nSaved references with no source record in this target. Audit rather than count as consulted evidence.\n" + js(citation_stubs, True))
        parts.append(f"END OF COMPLETE INPUT — {slug}\nExpected totals: {len(entries)} active entries, {len(sources)} current database source records, {len(supplements)} supplementary file-ledger conflict records, {len(orphans)} orphan editorial mappings, {len(citation_stubs)} unregistered citation IDs.\nNow carry out the target-specific update and return the complete portable research package described above. No additional repository or earlier-chat context is required.")
        text = "\n\n".join(parts) + "\n"
        prompt_path = OUT / "prompts" / f"{slug}.txt"
        prompt_path.write_text(text)
        chunk_bodies, current = [], []
        current_size = 0
        for block in parts:
            assert len(block) <= PART_LIMIT, f"Oversized atomic block: {slug}"
            if current and current_size + len(block) + 2 > PART_LIMIT:
                chunk_bodies.append("\n\n".join(current))
                current, current_size = [], 0
            current.append(block)
            current_size += len(block) + 2
        if current:
            chunk_bodies.append("\n\n".join(current))
        chunk_dir = OUT / "paste-parts" / slug
        chunk_dir.mkdir(exist_ok=True)
        # Remove only previously generated parts for this same export target.
        for previous in chunk_dir.glob("part-*-of-*.txt"):
            previous.unlink()
        for i, body in enumerate(chunk_bodies, 1):
            header = (f"INPUT PART {i}/{len(chunk_bodies)} — {slug}\nThese numbered messages together are ONE complete research request. "
                      f"Expect {len(entries)} current entries and {len(sources)} current source records, plus the labelled supplements. "
                      "Until the final part arrives, acknowledge receipt briefly and wait; do not start the research or infer missing parts. "
                      "If the conversation cannot retain all parts, say so and request the complete prompt as a file instead of pretending full coverage.\n\n")
            footer = "\n\nEND OF THIS INPUT PART. " + ("All input parts have now been supplied. Begin the requested update." if i == len(chunk_bodies) else "Wait for the next numbered part.") + "\n"
            (chunk_dir / f"part-{i:02d}-of-{len(chunk_bodies):02d}.txt").write_text(header + body + footer)
        assert "\n\n".join(chunk_bodies) + "\n" == text
        assert text.count("\n\nSOURCE [") == len(sources)
        assert text.count("\n\nENTRY ") == len(entries)
        manifest.append({"target_id": slug, "title": rank["title"], "priority": cfg["priority"], "entry_count": len(entries), "country_placements": sum(len(e["groupings"]) for e in entries), "source_records": len(sources), "sources_flagged_eligible": sum(s["eligible"] and not s["is_archived"] for s in sources), "supplementary_ledger_records": len(supplements), "orphan_editorial_mappings": len(orphans), "unregistered_citation_ids": len(citation_stubs), "prompt_file": str(prompt_path.relative_to(OUT)), "snapshot_file": str(snapshot_path.relative_to(OUT)), "paste_parts_directory": str(chunk_dir.relative_to(OUT)), "paste_parts": len(chunk_bodies), "characters": len(text), "utf8_bytes": prompt_path.stat().st_size, "sha256": digest(prompt_path), "snapshot_sha256": digest(snapshot_path)})
    connection.rollback()
    connection.close()
    lead_order = ["books-every-country", "history-books-ancient-rome", "history-books-medieval", "books-africa", "books-historical-fiction", "books-horror-all-time", "manga-shonen-all-time", "manga-seinen-all-time", "manga-shojo-all-time", "manga-josei-all-time", "history-books-all-time", "poetry-all-time", "philosophy-books-all-time", "literature-all-time"]
    manifest.sort(key=lambda r: (r["priority"], lead_order.index(r["target_id"]) if r["target_id"] in lead_order else 999, r["title"]))
    totals = {"targets": len(manifest), "entries": sum(r["entry_count"] for r in manifest), "target_local_source_records": sum(r["source_records"] for r in manifest), "supplementary_ledger_records": sum(r["supplementary_ledger_records"] for r in manifest), "paste_parts": sum(r["paste_parts"] for r in manifest)}
    (OUT / "manifest.json").write_text(js({"snapshot_at_utc": captured_at, "totals": totals, "rankings": manifest}, True) + "\n")
    with (OUT / "manifest.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(manifest[0]))
        writer.writeheader()
        writer.writerows(manifest)
    readme = ["# Ranking update prompts — 27 September 2026", "Each prompt is complete and independent: it includes its task, current ranking, saved editorial orders, candidate evidence, and every current target-local source record with its saved evidence/access labels. Start a separate agent conversation for each target.", "## How to use", "1. Open a **complete prompt** below and copy the whole file into the other agent. You can attach the text file instead and say: ‘Read the entire attached request, including all entries and source records, and carry out the update.’\n2. If the paste is too large, use that target’s **numbered parts**, in order, in the same conversation. Each part instructs the agent to wait until the last part. These are message-size chunks; they do not increase the other agent’s total context capacity. If the full record does not fit, use an agent that can read attached files or a larger context.\n3. The requested return is a complete Word `.docx` report with the revised ranking, full source register, candidate citations and change log. Structured Markdown/text is accepted when document creation is unavailable. Return those files to the app integration agent for reconciliation/import.", f"Snapshot: `{captured_at}`. **{totals['targets']} rankings; {totals['entries']:,} current ranking entries; {totals['target_local_source_records']:,} source records.** Source totals are per-target records, including leads; they are not a count of globally unique or verified sources. Also included: {totals['supplementary_ledger_records']} conflicting current English-history ledger records in an explicit separate namespace. No live ranking, source record or private data was changed.", "The pack covers all researched/curated rankings. Priorities 1 and 2 cover the evidence/identity improvements flagged in the audit; priority 3 contains optional follow-ups for comparatively better-supported targets. Original publisher rankings and reading collections are outside this synthesis-update pack.", "Snapshots are exported directly from the current SQLite database in a single read-only transaction. Current `sources.json` ledgers were also reconciled; nonconflicting source records are already in the database export. The raw public research snapshot for each target is available in `snapshots/`. No account details, private preferences, library records or share tokens are included."]
    labels = {1: "First: evidence and identity repairs", 2: "Next: targeted evidence and coverage updates", 3: "Optional: focused follow-up and maintenance"}
    for priority in (1, 2, 3):
        rows = [r for r in manifest if r["priority"] == priority]
        readme.extend([f"## {labels[priority]} ({len(rows)})", "| Ranking | Entries | All source records | Complete prompt | Numbered parts |\n|---|---:|---:|---|---|"])
        for r in rows:
            readme.append(f"| {r['title']} | {r['entry_count']} | {r['source_records']} | [Open]({r['prompt_file']}) | [{r['paste_parts']} parts]({r['paste_parts_directory']}/INDEX.md) |")
            chunkdir = OUT / r["paste_parts_directory"]
            lines = [f"# {r['title']} — paste parts", f"Paste all {r['paste_parts']} parts, in order, into one conversation. Do not send them to different agents. The complete request contains {r['characters']:,} characters; splitting does not remove the need for enough total context.", f"[Complete prompt](../../{r['prompt_file']})", ""]
            for part in sorted(chunkdir.glob("part-*-of-*.txt")):
                lines.append(f"- [{part.stem}]({part.name})")
            (chunkdir / "INDEX.md").write_text("\n\n".join(lines) + "\n")
    readme.extend(["## Files and checks", "`manifest.json` and `manifest.csv` list exact counts, file sizes and SHA-256 hashes. `evidence-audit.csv` is the earlier saved evidence audit; its metrics are indicators of saved linkage, not independent source verification. The export checked that every current curated target, active entry and registered source is present, all prompt sections match their counts, and concatenating the paste-part bodies reproduces each complete prompt.", "Known input defects are preserved and labelled. Horror includes old editorial mappings after catalog repairs; English history includes conflicting file-ledger source IDs. Missing references are supplied as citation stubs rather than represented as verified sources. The other agent is instructed to report proposed repairs explicitly."])
    (OUT / "README.md").write_text("\n\n".join(readme) + "\n")
    verification = {"snapshot_at_utc": captured_at, "checks": {"read_only_database_transaction": True, "all_active_shared_curated_targets_have_specific_instructions": True, "entry_and_source_counts_match_prior_audit": True, "full_source_notes_preserved_with_exact_duplicate_metadata_condensed": True, "all_paste_parts_reassemble_to_complete_prompt": True, "private_tables_not_exported": True}, "totals": totals, "priority_counts": dict(Counter(r["priority"] for r in manifest))}
    (OUT / "verification.json").write_text(js(verification, True) + "\n")
    zip_path = OUT / "ranking-update-prompts-2026-09-27.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(OUT.rglob("*")):
            if path.is_file() and path != zip_path and "__pycache__" not in path.parts:
                z.write(path, Path(OUT.name) / path.relative_to(OUT))
    print(js({**verification, "zip_bytes": zip_path.stat().st_size, "largest_prompts": sorted(manifest, key=lambda r: r["characters"], reverse=True)[:3]}, True))


if __name__ == "__main__":
    main()
