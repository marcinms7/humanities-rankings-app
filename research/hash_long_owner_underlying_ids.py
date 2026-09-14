"""Shorten unimported owner-lead identity keys that exceed the model limit."""
import hashlib
import json
from pathlib import Path

for target in ("poetry-all-time", "nonfiction-all-time"):
    path = Path(__file__).resolve().parent / target / "sources.json"
    ledger = json.loads(path.read_text())
    changed = 0
    for source in ledger["sources"]:
        value = source.get("underlying_source_id", "")
        if source.get("owner_supplied") and len(value) > 200:
            source["underlying_source_id"] = "owner-url-sha256:" + hashlib.sha256(source["canonical_url"].encode()).hexdigest()
            changed += 1
    path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n")
    print(target, changed)
