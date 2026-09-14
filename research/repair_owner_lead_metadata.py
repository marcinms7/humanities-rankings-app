"""Refresh display metadata for owner leads from the preserved source files."""
import json
from pathlib import Path
from urllib.parse import urlsplit

from import_owner_source_leads import ROOT, RUN, TARGETS, canonical_url, details

for target in TARGETS:
    incoming = ROOT / "research" / "incoming" / target / RUN
    supplied = details((incoming / "original.txt").read_text())
    path = ROOT / "research" / target / "sources.json"
    ledger = json.loads(path.read_text())
    changed = 0
    for source in ledger["sources"]:
        if not source.get("owner_supplied"):
            continue
        info = supplied.get(canonical_url(source["canonical_url"]), {})
        title = info.get("title") or urlsplit(source["canonical_url"]).netloc.removeprefix("www.")
        if title and source["title"] != title:
            source["title"] = title
            changed += 1
        relevance = info.get("description") or info.get("coverage / description")
        if relevance:
            source["relevance_by_target"][target] = relevance
        limitation = info.get("caveat") or info.get("main caveat")
        if limitation:
            source["disagreement_or_limitations"] = limitation
    path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n")
    print(target, changed)
