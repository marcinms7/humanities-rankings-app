"""Print live catalogue-cover enrichment progress from its durable ledger."""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
LEDGER = ROOT / "research" / "_runs" / "2026-09-13" / "catalog-public-cover-fallback" / "outcomes.jsonl"
WEB_LEDGER = ROOT / "research" / "_runs" / "2026-09-14" / "catalog-web-cover-fallback" / "outcomes.jsonl"
PROVIDER_LEDGERS = {
    "anilist": ROOT / "research/_runs/2026-09-14/catalog-manga-anilist/outcomes.jsonl",
    "kitsu": ROOT / "research/_runs/2026-09-14/catalog-manga-kitsu/outcomes.jsonl",
    "jikan": ROOT / "research/_runs/2026-09-14/catalog-manga-jikan/outcomes.jsonl",
}


def load_latest(path: Path) -> dict:
    latest = {}
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                row = json.loads(line)
                latest[row["work_id"]] = row
            except (ValueError, KeyError):
                continue
    return latest


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.settings")
    import django
    django.setup()
    from backend.core.models import Work

    latest = load_latest(LEDGER)
    web_latest = load_latest(WEB_LEDGER)
    provider_latest = {name: load_latest(path) for name, path in PROVIDER_LEDGERS.items()}
    works = Work.objects.filter(is_archived=False)
    covered = works.filter(default_edition__cover__isnull=False).exclude(default_edition__cover="").count()
    statuses = Counter(str(row.get("status", "")) for row in latest.values())
    modified = datetime.fromtimestamp(LEDGER.stat().st_mtime).astimezone().isoformat(timespec="seconds") if LEDGER.exists() else None
    print(json.dumps({
        "checked_unique_works": len(latest),
        "active_catalogue_works": works.count(),
        "visible_covers": covered,
        "without_visible_cover": works.count() - covered,
        "ledger_modified_at": modified,
        "fallback_covers": statuses.get("covered", 0),
        "web_checked_unique_works": len(web_latest),
        "web_fallback_covers": sum(row.get("status") == "covered" for row in web_latest.values()),
        "specialist_providers": {
            name: {"checked": len(rows), "covered": sum(row.get("status") == "covered" for row in rows.values())}
            for name, rows in provider_latest.items()
        },
        "recent_statuses": dict(statuses.most_common(8)),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
