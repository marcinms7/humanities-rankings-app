"""Reconcile stale editorial IDs left by the older revisionless horror repair."""
import json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.config.settings')
import django;django.setup()
from django.db import transaction
from backend.core.models import Ranking,Work
from backend.core.views import ensure_revision,save_revision
from research.repair_report_column_reversals import norm
RUN=ROOT/'research/_runs/2026-09-28/completion'
with transaction.atomic():
 r=Ranking.objects.select_for_update().get(slug='books-horror-all-time');orders=r.scope['editorial']['orders'];entries=list(r.entries.filter(is_archived=False).select_related('work').order_by('position'));mapping={};receipt=[]
 for old,e in zip(orders['standing']['item_ids'],entries):
  if old==e.work_id:continue
  w=Work.objects.get(pk=old);names=list(w.authors.values_list('name',flat=True))
  assert w.is_archived and len(names)==1 and norm(names[0])==norm(e.work.title) and norm(w.title) in {norm(p.name) for p in e.work.authors.all()},old
  mapping[old]=e.work_id;receipt.append({'work_id':old,'saved_work_id':e.work_id,'before_title':w.title,'before_authors':names,'title':e.work.title,'reason':'Historical entry already canonical; saved editorial references were stale'})
 if mapping:
  ensure_revision(r)
  for order in orders.values():
   order['item_ids']=[mapping.get(i,i) for i in order['item_ids']]
   assert len(order['item_ids'])==len(entries) and set(order['item_ids'])=={e.work_id for e in entries}
  explanations=r.scope['editorial'].get('entries',{})
  for old,new in mapping.items():
   if str(old) in explanations:
    previous=explanations.pop(str(old))
    if str(new) not in explanations:explanations[str(new)]=previous
    else:r.scope.setdefault('retained_identity_explanations',{})[str(old)]=previous
  r.scope.setdefault('identity_repairs',[]).extend(receipt);save_revision(r,'Reconciled 30 historical horror identity references in both editorial orders; source positions unchanged')
  (RUN/'historical-horror-order-repairs.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'corrected_order_references':len(mapping),'revision':r.revision}))
