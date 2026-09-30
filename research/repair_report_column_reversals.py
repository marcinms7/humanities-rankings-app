"""Repair only exact swapped pairs confirmed by preserved report column formats."""
import argparse,hashlib,json,os,re,sys,unicodedata
from pathlib import Path
from collections import defaultdict
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
RUN=ROOT/'research/_runs/2026-09-28/completion'
FORMATS={
 'history-books-ancient-world':('2026-09-13-owner-paste', 'author_title'),
 'history-books-ancient-rome':('2026-09-13-owner-paste', 'author_title'),
 'history-books-england':('2026-09-13-owner-paste', 'author_title'),
 'history-books-chinese-history':('2026-09-13-owner-paste', 'author_title'),
 'books-horror-all-time':('2026-09-14-owner-chat-attachments','title_author'),
}
def norm(s):return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().casefold())
def main():
 p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');args=p.parse_args()
 os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.config.settings');import django;django.setup()
 from django.db import transaction
 from django.utils import timezone
 from backend.core.models import Work,Person,Ranking,RankingEntry
 from backend.core.views import ensure_revision,save_revision
 works=list(Work.objects.filter(is_archived=False).prefetch_related('authors'));by=defaultdict(list);titles=defaultdict(list)
 for w in works:
  names=[a.name for a in w.authors.all()]
  if len(names)==1:by[(norm(w.title),norm(names[0]))].append(w)
  titles[norm(w.title)].append(w)
 proposed={};skipped=[]
 for target,(folder,fmt) in FORMATS.items():
  file=ROOT/'research/incoming'/target/folder/'report.txt';body=file.read_text();digest=hashlib.sha256(file.read_bytes()).hexdigest()
  for line in body.splitlines():
   match=re.match(r'^\s*(\d{1,3})[.)]\s+(.+?)\s+[—–]\s+(.+?)\s*$',line)
   if not match:continue
   author,title=(match[2],match[3]) if fmt=='author_title' else (match[3],match[2])
   title=re.sub(r'\s*\(\d{3,4}(?:[–-]\d{2,4})?\)\s*$','',title).strip();author=author.strip()
   for wrong in by.get((norm(author),norm(title)),[]):
    if any(x in author for x in (' & ',' and ',';',' et al.')) or author == 'The Cambridge Ancient History' or re.search(r'\beds?\.',author):
     skipped.append({'work_id':wrong.pk,'reason':'Multiple contributors/editor roles need separate normalization','line':line});continue
    canonical=[w for w in titles.get(norm(title),[]) if w.pk!=wrong.pk and any(norm(a.name)==norm(author) for a in w.authors.all())]
    proposed[wrong.pk]={'work_id':wrong.pk,'before_title':wrong.title,'before_authors':[a.name for a in wrong.authors.all()], 'title':title,'author':author,
      'canonical_id':canonical[0].pk if len(canonical)==1 else None,'duplicate_review':len(canonical)>1,
      'source':str(file.relative_to(ROOT)),'sha256':digest,'raw_line':line,'column_format':fmt}
 RUN.mkdir(parents=True,exist_ok=True)
 plan={'proposed':list(proposed.values()),'skipped':skipped}
 encoded=json.dumps(plan,ensure_ascii=False,indent=2)+'\n'
 # Preserve the original review input used by the contributor follow-up.
 if not (RUN/'column-reversal-plan.json').exists():
  (RUN/'column-reversal-plan.json').write_text(encoded)
 (RUN/'column-reversal-plan.latest.json').write_text(encoded)
 if not args.apply:print(json.dumps({'proposed':len(proposed),'skipped':len(skipped),'canonical_matches':sum(bool(r['canonical_id']) for r in proposed.values())}));return
 receipts=[]
 # Each repaired identity is an independently saved, revisioned batch.
 for row in proposed.values():
  with transaction.atomic():
   wrong=Work.objects.select_for_update().get(pk=row['work_id'])
   old_people=list(wrong.authors.all())
   if wrong.title!=row['before_title'] or [p.name for p in old_people]!=row['before_authors']:raise RuntimeError('Catalog changed after preview')
   entries=list(RankingEntry.objects.filter(work=wrong,is_archived=False).exclude(ranking__origin='personal'))
   rankings=list(Ranking.objects.select_for_update().filter(pk__in=[e.ranking_id for e in entries]))
   canonical=Work.objects.get(pk=row['canonical_id']) if row['canonical_id'] else wrong
   collisions=RankingEntry.objects.filter(ranking__in=rankings,work=canonical).exists() if canonical!=wrong else False
   # Do not collapse ranked positions or private override identities on collision.
   if collisions:canonical=wrong;row['canonical_merge_deferred']='Existing target entry; corrected in place without deleting positions'
   for ranking in rankings:ensure_revision(ranking)
   people=list(Person.objects.filter(is_archived=False,name=row['author']))
   if len(people)>1:
    row['deferred']='Ambiguous person IDs';receipts.append(row);continue
   person=people[0] if people else Person.objects.create(name=row['author'])
   wrong.title=row['title'];wrong.is_archived=canonical!=wrong
   wrong.save(update_fields=['title','is_archived','updated_at']);wrong.authors.set([person])
   if canonical!=wrong:
    for entry in entries:entry.work=canonical;entry.save(update_fields=['work'])
   for ranking in rankings:
    editorial=ranking.scope.get('editorial',{})
    for order in editorial.get('orders',{}).values():order['item_ids']=[canonical.pk if i==wrong.pk else i for i in order.get('item_ids',[])]
    explanations=editorial.get('entries',{})
    if str(wrong.pk) in explanations and canonical!=wrong:explanations[str(canonical.pk)]=explanations.pop(str(wrong.pk))
    ranking.scope.setdefault('identity_repairs',[]).append({'from':wrong.pk,'to':canonical.pk,'source':row['source'],'sha256':row['sha256']})
    save_revision(ranking,f'Corrected swapped report columns for work {wrong.pk}; positions and entry IDs retained')
   archived_people=[]
   for old in old_people:
    if old.pk!=person.pk and not old.works.exists() and not RankingEntry.objects.filter(person=old).exists():
     old.is_archived=True;old.save(update_fields=['is_archived','updated_at']);archived_people.append(old.pk)
   row.update(saved_work_id=canonical.pk,archived_placeholder_people=archived_people,rankings=[r.slug for r in rankings],saved_at=timezone.now().isoformat())
   receipts.append(row)
   with (RUN/'column-reversal-receipts.jsonl').open('a') as output:output.write(json.dumps(row,ensure_ascii=False)+'\n');output.flush();os.fsync(output.fileno())
  print(json.dumps({'work_id':wrong.pk,'title':row['title'],'saved_work_id':canonical.pk},ensure_ascii=False),flush=True)
 print(json.dumps({'repaired':sum('saved_at' in r for r in receipts),'deferred':sum('deferred' in r for r in receipts)}))
if __name__=='__main__':main()
