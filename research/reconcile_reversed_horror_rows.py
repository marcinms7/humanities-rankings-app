"""Repair exact reciprocal Author/Title rows from the horror intake.

Only rows in the known malformed import range are considered. A replacement
must already exist as an active Work whose title equals the malformed row's
credited placeholder and whose credited author equals the malformed title.
Current entries are rewired; revisions and the malformed row remain preserved.
"""
import json, os, re, sys, unicodedata
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent; sys.path.insert(0,str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE","backend.config.settings")
import django; django.setup()
from django.db import transaction
from backend.core.models import RankingEntry, Work

def norm(s):
    return re.sub(r"[^a-z0-9]","",unicodedata.normalize("NFKD",str(s)).encode("ascii","ignore").decode().casefold())

works=list(Work.objects.filter(is_archived=False).prefetch_related("authors").select_related("default_edition"))
by_title=defaultdict(list)
for work in works: by_title[norm(work.title)].append(work)
changes=[]
with transaction.atomic():
    for wrong in works:
        if not 8237 <= wrong.pk <= 8390: continue
        candidates={}
        for placeholder in wrong.authors.all():
            for candidate in by_title.get(norm(placeholder.name),[]):
                if candidate.pk != wrong.pk and any(norm(a.name)==norm(wrong.title) for a in candidate.authors.all()):
                    candidates[candidate.pk]=candidate
        if len(candidates)!=1: continue
        correct=next(iter(candidates.values()))
        if not (correct.default_edition_id and correct.default_edition.cover): continue
        entries=list(RankingEntry.objects.filter(work=wrong,is_archived=False).select_related("ranking"))
        if not entries: continue
        for entry in entries:
            collision=RankingEntry.objects.filter(ranking=entry.ranking,work=correct).exclude(pk=entry.pk).first()
            if collision:
                entry.is_archived=True; entry.save(update_fields=["is_archived"]); action="archived_duplicate_entry"
            else:
                entry.work=correct; entry.save(update_fields=["work"]); action="rewired_entry"
            changes.append({"entry_id":entry.pk,"ranking":entry.ranking.slug,"from_work_id":wrong.pk,
                            "from_title":wrong.title,"to_work_id":correct.pk,"to_title":correct.title,"action":action})
        wrong.is_archived=True; wrong.save(update_fields=["is_archived","updated_at"])
out=ROOT/"research/_runs/2026-09-14/reversed-horror-reconciliation.json"
out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(changes,indent=2,ensure_ascii=False)+"\n")
print(json.dumps({"entries_changed":len(changes),"malformed_works_archived":len({x['from_work_id'] for x in changes})},indent=2))
