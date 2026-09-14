"""Copy credited covers between exact duplicate active catalogue works.

The import corpus occasionally contains separate Work rows for the same title
and authors.  This reuses the already saved edition image without downloading
or guessing, and records every mutation in the public-cover outcome ledger.
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.settings")

import django
django.setup()

from django.db import transaction
from backend.core.models import Edition, Work

LEDGER = ROOT / "research/_runs/2026-09-13/catalog-public-cover-fallback/outcomes.jsonl"


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]", "", value)


groups = defaultdict(list)
for work in Work.objects.filter(is_archived=False).select_related("default_edition").prefetch_related("authors"):
    key = (norm(work.title), tuple(sorted(norm(author.name) for author in work.authors.all())))
    groups[key].append(work)

copied = 0
with LEDGER.open("a") as output:
    for works in groups.values():
        donors = [w for w in works if w.default_edition_id and w.default_edition.cover]
        recipients = [w for w in works if not (w.default_edition_id and w.default_edition.cover)]
        if not donors:
            continue
        donor = donors[0].default_edition
        for recipient in recipients:
            with transaction.atomic():
                edition = recipient.default_edition
                if edition is None:
                    edition = Edition.objects.create(work=recipient, language=donor.language or "English")
                    recipient.default_edition = edition
                    recipient.save(update_fields=["default_edition", "updated_at"])
                edition.cover.name = donor.cover.name
                edition.source_url = donor.source_url
                edition.image_attribution = donor.image_attribution
                edition.save(update_fields=["cover", "source_url", "image_attribution", "updated_at"])
            output.write(json.dumps({
                "work_id": recipient.pk, "title": recipient.title,
                "status": "covered", "provider": "catalogue_exact_duplicate",
                "donor_work_id": donors[0].pk, "edition_id": edition.pk,
            }, ensure_ascii=False) + "\n")
            output.flush()
            copied += 1
            print(f"[{recipient.pk}] copied from exact duplicate [{donors[0].pk}] — {recipient.title}", flush=True)
print(json.dumps({"covered": copied}))
