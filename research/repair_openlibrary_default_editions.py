"""Repair the small pre-bulk trial where editions were saved before default pointers."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.settings")
import django
django.setup()

from backend.core.models import Edition, Work

records = [json.loads(line) for line in (ROOT / "research" / "_runs" / "2026-09-13" / "new-catalog-openlibrary" / "outcomes.jsonl").read_text().splitlines()]
fixed = []
for record in records:
    if record.get("status") != "covered" or not record.get("edition_id"):
        continue
    work = Work.objects.get(pk=record["work_id"], is_archived=False)
    edition = Edition.objects.get(pk=record["edition_id"], work=work, is_archived=False)
    if work.default_edition_id is None:
        work.default_edition = edition
        work.save(update_fields=["default_edition", "updated_at"])
        fixed.append({"work_id": work.pk, "edition_id": edition.pk})
print(json.dumps({"repaired": fixed}, indent=2))
