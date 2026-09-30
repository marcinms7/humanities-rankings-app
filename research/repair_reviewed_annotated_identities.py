"""Correct reviewed report identities whose headings include date/scope annotations."""
import os,json,re,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.config.settings')
import django;django.setup()
from django.db import transaction
from django.utils import timezone
from backend.core.models import Work,Person,Ranking,RankingEntry
from backend.core.views import ensure_revision,save_revision
RUN=ROOT/'research/_runs/2026-09-28/completion'
# Explicit review avoids confusing Syme's Tacitus with the ancient author.
IDS={2141,2142,2143,2144,2148,2152,2153,2154,2155,2156,2163,2164,2181,2184,2202,2214,2219,2221,2223}
source=ROOT/'research/incoming/history-books-ancient-rome/2026-09-13-owner-paste/report.txt'
rows=json.loads((RUN/'remaining-report-identities.json').read_text());done=set();apply='--apply' in sys.argv
for row in rows:
 wid=row['id']
 if wid not in IDS or wid in done or row['target']!='history-books-ancient-rome':continue
 title=row['authors'][0];m=re.match(r'^\s*\d+[.)]\s+(.+?)\s+—\s+(.+)$',row['line'])
 if not m or not m[2].startswith(title):continue
 names=[] if wid==2148 else [v.strip() for v in re.split(r',\s*|\s+&\s+',row['title'])]
 w=Work.objects.get(pk=wid)
 if w.title==title:done.add(wid);continue
 assert w.title==row['title'] and list(w.authors.values_list('name',flat=True))==row['authors']
 receipt={**row,'new_title':title,'new_authors':names,'source':str(source.relative_to(ROOT)),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'before_description':w.description}
 if apply:
  with transaction.atomic():
   w=Work.objects.select_for_update().get(pk=wid)
   assert w.title==row['title']
   rankings=list(Ranking.objects.select_for_update().filter(entries__work=w).exclude(origin='personal').distinct())
   for r in rankings:ensure_revision(r)
   people=[]
   for name in names:
    matches=list(Person.objects.filter(name=name,is_archived=False))
    if len(matches)>1:raise RuntimeError('Ambiguous person '+name)
    people.append(matches[0] if matches else Person.objects.create(name=name))
   old=list(w.authors.all());w.authors.set(people);w.title=title
   w.description='Report title/contributor columns corrected on 28 September 2026. The original entry specifies: '+row['line']
   if wid==2148:w.description+=' This is a bounded group of edited volumes, not a single-author book; select a volume before assigning page counts.'
   w.save(update_fields=['title','description','updated_at'])
   for person in old:
    if not person.works.exists() and not RankingEntry.objects.filter(person=person).exists():person.is_archived=True;person.save(update_fields=['is_archived','updated_at'])
   for r in rankings:
    r.scope.setdefault('identity_repairs',[]).append({'work_id':wid,'source':receipt['source'],'sha256':receipt['sha256'],'raw_line':row['line']})
    save_revision(r,f'Corrected annotated report identity {wid}; positions retained')
  receipt['saved_at']=timezone.now().isoformat()
  with (RUN/'annotated-identity-receipts.jsonl').open('a') as f:f.write(json.dumps(receipt,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
 done.add(wid);print(json.dumps({'id':wid,'title':title,'authors':names,'applied':apply},ensure_ascii=False),flush=True)
assert done==IDS,(IDS-done)
