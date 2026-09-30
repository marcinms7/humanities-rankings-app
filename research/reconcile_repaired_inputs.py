"""Reconcile generated import identities with saved repair receipts; keep originals."""
import json,os,sys,hashlib,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.config.settings')
import django;django.setup()
from backend.core.models import Work
from research.repair_report_column_reversals import norm
RUN=ROOT/'research/_runs/2026-09-28/completion';receipts=[]
for name in ['column-reversal-receipts.jsonl','contributor-repair-receipts.jsonl','annotated-identity-receipts.jsonl']:
 for line in (RUN/name).read_text().splitlines():receipts.append(json.loads(line))
receipts += json.loads((RUN/'historical-horror-order-repairs.json').read_text())
changes={};idmap={}
for r in receipts:
 wid=r.get('saved_work_id',r.get('work_id',r.get('id')));w=Work.objects.get(pk=wid)
 title=r.get('before_title',r.get('title'));authors=r.get('before_authors',r.get('authors'))
 changes[(norm(title),tuple(sorted(norm(a) for a in authors)))]=(w.title,list(w.authors.values_list('name',flat=True)))
 oldid=r.get('work_id',r.get('id'));idmap[oldid]=wid
from backend.core.management.commands.repair_reviewed_identities import REPAIRS
for oldid,author,old_author,canonical in REPAIRS:
 w=Work.objects.get(pk=canonical or oldid)
 changes[(norm(author),(norm(old_author),))]=(w.title,list(w.authors.values_list('name',flat=True)))
 idmap[oldid]=w.pk
out=[]
for target in ['history-books-ancient-world','history-books-ancient-rome','history-books-england','books-horror-all-time']:
 for p in (ROOT/'research'/target).glob('*.json'):
  if not any(x in p.name for x in ['catalog','selection']) or 'receipt' in p.name or 'plan' in p.name:continue
  d=json.loads(p.read_text());n=0
  for r in d.get('works',[]):
   if r.get('item_id') in idmap and idmap[r['item_id']]!=r['item_id']:r['item_id']=idmap[r['item_id']];n+=1
   authors=r.get('authors') or ([r['attribution']] if r.get('attribution') else [])
   if not authors or not r.get('title'):continue
   identity=(norm(r['title']),tuple(sorted(norm(a) for a in authors)))
   if identity in changes:
    title,names=changes[identity]
    if (title,names)!=(r['title'],authors):
     r['title']=title
     if 'authors' in r:r['authors']=names
     else:r['attribution']='; '.join(names)
     n+=1
  for r in d.get('entries',[]):
   if r.get('item_id') in idmap and idmap[r['item_id']]!=r['item_id']:r['item_id']=idmap[r['item_id']];n+=1
  if not n:continue
  saved=RUN/'pre-repair-generated-inputs'/target/p.name;saved.parent.mkdir(parents=True,exist_ok=True)
  if not saved.exists():shutil.copyfile(p,saved)
  digest=hashlib.sha256(saved.read_bytes()).hexdigest()
  d['identity_reconciliation']={'date':'2026-09-28','receipts':'research/_runs/2026-09-28/completion/','previous_sha256':digest,'note':'Title/author fields and canonical IDs reconciled with saved repairs; source order and entry keys retained. Previous import receipts remain historical.'}
  p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');out.append({'file':str(p.relative_to(ROOT)),'changed_identities':n,'previous_sha256':digest})
manifest=[{'file':str(p.relative_to(RUN/'pre-repair-generated-inputs')),'original_sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in (RUN/'pre-repair-generated-inputs').glob('*/*.json')]
(RUN/'generated-input-reconciliation.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(out,indent=2))
