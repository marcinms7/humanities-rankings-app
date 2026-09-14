"""Reconcile owner-supplied URL leads with existing target ledgers.

This does not promote unopened leads to consulted evidence.  It records exact and
canonical URL overlap so later small reviewed batches can preserve source IDs.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parent.parent
TARGETS = (
    "books-all-time",
    "philosophy-books-all-time",
    "history-books-all-time",
    "poetry-all-time",
    "nonfiction-all-time",
)
RUN = "2026-09-13-owner-paste"


def canonical_url(value: str) -> str:
    parts = urlsplit(value.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm_")]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def ledger_sources(target: str) -> list[dict]:
    path = ROOT / "research" / target / "sources.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return data.get("sources", data if isinstance(data, list) else [])


for target in TARGETS:
    incoming = ROOT / "research" / "incoming" / target / RUN
    leads_payload = json.loads((incoming / "source-leads.json").read_text())
    leads = [{"lead_id": f"owner-{number:03d}", "url": url}
             for number, url in enumerate(leads_payload["urls"], 1)]
    existing = ledger_sources(target)
    by_url = {}
    for source in existing:
        url = source.get("url") or source.get("canonical_url")
        if url:
            by_url.setdefault(canonical_url(url), []).append(source.get("source_id") or source.get("id"))
    rows = []
    for lead in leads:
        url = lead["url"]
        ids = [value for value in by_url.get(canonical_url(url), []) if value]
        rows.append({
            "lead_id": lead.get("lead_id") or lead.get("id"),
            "url": url,
            "status": "existing_exact_or_canonical_url" if ids else "new_unreviewed_lead",
            "existing_source_ids": ids,
        })
    result = {
        "target": target,
        "rule": "Unreviewed leads are not counted or imported as consulted evidence.",
        "lead_count": len(rows),
        "existing_overlap_count": sum(row["status"].startswith("existing") for row in rows),
        "new_unreviewed_count": sum(row["status"].startswith("new") for row in rows),
        "rows": rows,
    }
    (incoming / "reconciliation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(target, result["lead_count"], result["existing_overlap_count"], result["new_unreviewed_count"])
