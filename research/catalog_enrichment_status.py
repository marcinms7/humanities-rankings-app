"""Show durable page-count and cover-enrichment progress."""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
PAGE_LEDGER = ROOT / "research/_runs/2026-09-15/catalog-page-counts/outcomes.jsonl"
COVER_LEDGER = ROOT / "research/_runs/2026-09-13/catalog-public-cover-fallback/outcomes.jsonl"
STATE = ROOT / "research/_runs/catalog-enrichment-supervisor"


def latest(path: Path) -> dict[int, dict]:
    # Prefer the compact read-only index; stream the audit only before initialization.
    import sqlite3
    from enrichment_queue import STATE as QUEUE_STATE, records
    kind = 'pages' if path == PAGE_LEDGER else 'covers'
    index = QUEUE_STATE / f'{kind}.sqlite3'
    if index.exists():
        with sqlite3.connect(f'file:{index}?mode=ro', uri=True) as connection:
            return {wid: json.loads(result) for wid, result in connection.execute('SELECT work_id,result FROM attempts')}
    return {int(row['work_id']): row for row in records(path)}


def timestamp(path: Path) -> str | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.settings")
    import django
    django.setup()
    from django.db.models import F
    from backend.core.models import Edition, Work

    works = Work.objects.filter(is_archived=False)
    defaults = Edition.objects.filter(work__is_archived=False, work__default_edition_id=F("id"))
    pages, covers = latest(PAGE_LEDGER), latest(COVER_LEDGER)
    pid = (STATE / "supervisor.pid").read_text().strip() if (STATE / "supervisor.pid").exists() else None
    print(json.dumps({
        "active_works": works.count(),
        "displayed_editions": defaults.count(),
        "page_counts": {"present": defaults.filter(pages__isnull=False).count(), "missing": works.count() - defaults.filter(pages__isnull=False).count(),
                        "page_ledger_unique_works": len(pages), "ledger_updated_at": timestamp(PAGE_LEDGER),
                        "latest_statuses": dict(Counter(str(r.get("status", "")) for r in pages.values()).most_common(6))},
        "covers": {"present": works.filter(default_edition__cover__isnull=False).exclude(default_edition__cover="").count(),
                   "missing": works.count() - works.filter(default_edition__cover__isnull=False).exclude(default_edition__cover="").count(),
                   "cover_ledger_unique_works": len(covers), "ledger_updated_at": timestamp(COVER_LEDGER),
                   "latest_statuses": dict(Counter(str(r.get("status", "")) for r in covers.values()).most_common(6))},
        "supervisor_pid": pid,
        "supervisor_status": json.loads((STATE / "status.json").read_text()) if (STATE / "status.json").exists() else {"status": "stopped"},
        "supervisor_log": str(STATE / "supervisor.log"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
