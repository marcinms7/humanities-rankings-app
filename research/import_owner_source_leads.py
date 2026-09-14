"""Merge owner-supplied source leads into canonical ledgers as unconsulted records."""
from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from urllib.parse import urlsplit

from reconcile_owner_source_universes import ROOT, RUN, TARGETS, canonical_url


def details(raw: str) -> dict[str, dict[str, str]]:
    records = {}
    for line in raw.splitlines():
        match = re.search(r"https?://[^\s\]|>]+", line)
        columns = line.split("\t")
        if not match or len(columns) < 5 or not columns[0].strip().isdigit():
            continue
        url = match.group(0).rstrip(".,;")
        if len(columns) >= 9:
            title, description = columns[1].strip(), columns[6].strip()
        else:
            title, description = columns[2].strip(), columns[-2].strip()
        records[canonical_url(url)] = {"title": title, "description": description}
    blocks = re.split(r"(?m)(?=^\s*(?:\d{1,3}[.)]|\*\*\d{1,3}\.|#{1,4}\s*\d{1,3}))", raw)
    for block in blocks:
        match = re.search(r"https?://[^\s\]|>]+", block)
        if not match:
            continue
        url = match.group(0).rstrip(".,;")
        match_line = next((line for line in block.splitlines() if url in line), "")
        columns = match_line.split("\t")
        if len(columns) >= 9 and columns[0].strip().isdigit():
            title = columns[1].strip()
        elif len(columns) >= 5 and columns[0].strip().isdigit():
            title = columns[2].strip()
        else:
            first = [line for line in block[:match.start()].strip().splitlines()
                     if line.strip() and line.strip().casefold() not in {"url:", "url"}]
            numbered = next((line for line in first if re.match(r"^\s*\d{1,3}[.)]\s+", line)), None)
            title = (numbered or (first[-1] if first else urlsplit(url).netloc)).strip(" #*\t")
        title = re.sub(r"^\d{1,3}[.)]\s*", "", title).strip()
        fields = {}
        for key in ("Region", "Language", "Type", "Description", "Caveat", "Priority", "Source family", "Signal type", "Coverage / description", "Why useful", "Main caveat"):
            found = re.search(rf"(?im)^\s*{re.escape(key)}\s*:\s*(.+)$", block)
            if found:
                fields[key.lower()] = found.group(1).strip()
        records.setdefault(canonical_url(url), {"title": title or urlsplit(url).netloc, **fields})
    return records


for target in TARGETS:
    incoming = ROOT / "research" / "incoming" / target / RUN
    raw = (incoming / "original.txt").read_text()
    supplied = details(raw)
    urls = json.loads((incoming / "source-leads.json").read_text())["urls"]
    ledger_path = ROOT / "research" / target / "sources.json"
    if ledger_path.exists():
        ledger = json.loads(ledger_path.read_text())
    else:
        ledger = {"target_id": target, "minimum_eligible_sources": 50,
                  "criteria_version": None, "ranking_entries": [], "sources": [],
                  "status": "source_leads_received", "saved_at": "2026-09-13"}
    known_urls = {canonical_url(s["canonical_url"]): s for s in ledger["sources"] if s.get("canonical_url")}
    known_ids = {s["source_id"] for s in ledger["sources"]}
    added = overlap = 0
    for number, url in enumerate(urls, 1):
        normalized = canonical_url(url)
        if normalized in known_urls:
            overlap += 1
            continue
        info = supplied.get(normalized, {})
        source_id = f"OWNER-{number:03d}"
        while source_id in known_ids:
            source_id += "A"
        known_ids.add(source_id)
        host = urlsplit(url).netloc.removeprefix("www.")
        limitation = info.get("caveat") or info.get("main caveat") or "Owner-provided discovery lead; relevant content has not yet been independently reviewed."
        ledger["sources"].append({
            "source_id": source_id,
            "underlying_source_id": f"owner-url-sha256:{hashlib.sha256(normalized.encode()).hexdigest()}",
            "title": info.get("title") or host,
            "author": None,
            "publisher": host,
            "publisher_group": host,
            "canonical_url": url,
            "access_url": url,
            "publication_date": None,
            "accessed_at": None,
            "source_family": "owner_supplied_lead",
            "domain_or_platform": host,
            "language": info.get("language") or "unreviewed",
            "access_level": "not_accessed",
            "depends_on_source_ids": [],
            "dependency_note": None,
            "target_ids": [target],
            "relevance_by_target": {target: info.get("description") or info.get("coverage / description") or "Owner supplied this URL for review for this ranking."},
            "evidence_notes": "",
            "location": None,
            "evidence_role": "discovery_lead",
            "candidates_or_claims_supported": [],
            "disagreement_or_limitations": limitation,
            "count_eligible": False,
            "exclusion_reason": "Awaiting independent access and review before it can count as consulted evidence.",
            "consultation_batch": f"research/incoming/{target}/{RUN}/original.txt",
            "owner_supplied": True,
            "owner_source_number": number,
        })
        known_urls[normalized] = ledger["sources"][-1]
        added += 1
    ledger["saved_at"] = "2026-09-13"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n")
    print(target, "added", added, "overlap", overlap, "ledger", len(ledger["sources"]))
