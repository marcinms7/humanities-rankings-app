"""Stage ISBN-specific English edition candidates for bibliographic review.

Open Library may conflate shortened texts, individual volumes and full works.
Candidates remain archived until publisher/library confirmation; they must not
become selectable merely because an ISBN and page count occur in one provider.
Every candidate retains the actual provider edition record in its receipt.
"""
import argparse,json,os,re,sys,time
from pathlib import Path
from urllib.error import HTTPError
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'research')]
from enrichment_queue import Queue,exclusive,rotate
from enrich_catalog_covers_public import read_json,same_title,same_author
RUN=ROOT/'research/_runs/2026-09-28/exact-editions';LEDGER=RUN/'outcomes.jsonl'
def valid_isbn(value):
 s=value.replace('-','').replace(' ','').upper()
 if len(s)==13 and s.isdigit() and sum(int(c)*(1 if i%2==0 else 3) for i,c in enumerate(s))%10==0:return s
 if len(s)==10 and s[:9].isdigit() and (s[-1].isdigit() or s[-1]=='X') and sum((10-i)*(10 if c=='X' else int(c)) for i,c in enumerate(s))%11==0:return s
 return None

def main():
 p=argparse.ArgumentParser();p.add_argument('--limit',type=int,default=100);args=p.parse_args()
 os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.config.settings');import django;django.setup()
 from django.db import transaction
 from django.db.models import Count,Q
 from backend.core.models import Work,Edition
 RUN.mkdir(parents=True,exist_ok=True);q=Queue('exact-editions',LEDGER);rotate(LEDGER)
 works=Work.objects.filter(is_archived=False).prefetch_related('authors','editions').annotate(ranked=Count('rankingentry',filter=Q(rankingentry__is_archived=False,rankingentry__ranking__is_archived=False),distinct=True)).order_by('-ranked','pk')
 stats={'processed':0,'added':0};failures=0;author_cache={}
 with LEDGER.open('a') as audit:
  for work in works:
   if any(e.language=='English' and e.isbn and e.pages and e.pages_basis=='isbn_matched' and not e.is_archived for e in work.editions.all()):continue
   item={'id':work.pk,'title':work.title,'authors':sorted(a.name for a in work.authors.all())}
   if not item['authors'] or not q.due(item,'exact-title-author-english-isbn-v2'):continue
   record={'work_id':work.pk,'title':work.title,'authors':item['authors']}
   try:
    time.sleep(1.5)
    data=read_json('https://openlibrary.org/search.json',{'title':work.title,'author':item['authors'][0],'limit':20,'fields':'key,title,author_name,author_key,edition_count'},timeout=15)
    matches={}
    for d in data.get('docs',[]):
     if not d.get('key') or not same_title(work.title,d.get('title',''))[0]:continue
     names=list(d.get('author_name',[]));identities=[]
     if not same_author(item['authors'],names):
      for author_key in d.get('author_key',[])[:3]:
       if author_key not in author_cache:
        time.sleep(1.5)
        author_cache[author_key]=read_json('https://openlibrary.org/authors/'+author_key+'.json',{},timeout=15)
       identity=author_cache[author_key];identities.append(identity)
       names += [identity.get('name','')]+identity.get('alternate_names',[])
     if same_author(item['authors'],names):matches[d['key']]={**d,'verified_author_records':identities}
    choices=sorted(matches.values(),key=lambda d:int(d.get('edition_count',0)),reverse=True)
    ambiguous=len(choices)>1 and choices[0].get('edition_count',0)==choices[1].get('edition_count',0)
    if not choices or ambiguous:record['status']='identity_review' if choices else 'no_matching_work'
    else:
     key=choices[0]['key'];time.sleep(1.5)
     data=read_json('https://openlibrary.org'+key+'/editions.json',{'limit':100},timeout=15)
     options=[]
     for e in data.get('entries',[]):
      if not any(l.get('key')=='/languages/eng' for l in e.get('languages',[])):continue
      if key not in [w.get('key') for w in e.get('works',[])]:continue
      titles=[e.get('title',''),(e.get('title','')+': '+e.get('subtitle','')).strip(': ')]
      if not any(same_title(work.title,t)[0] for t in titles):continue
      if type(e.get('number_of_pages')) is not int or not 1<=e['number_of_pages']<=20000:continue
      isbn=next((v for raw in e.get('isbn_13',[])+e.get('isbn_10',[]) if (v:=valid_isbn(raw))),None)
      if not isbn or not e.get('key'):continue
      # Provider-labelled abridgments/adaptations are separate reading units.
      flags=' '.join(str(e.get(k,'')) for k in ['title','edition_name','physical_format']).casefold()
      # "Unabridged" contains "abridg" but identifies a complete text.
      if re.search(r'\babridg\w*',flags) or any(s in flags for s in ['adaptation','large type','braille']):continue
      options.append((e,isbn))
     if not options:record.update(status='no_verified_english_option',work_key=key)
     else:
      e,isbn=options[0];url='https://openlibrary.org'+e['key']
      with transaction.atomic():
       current=Work.objects.select_for_update().get(pk=work.pk)
       if current.is_archived or current.title!=item['title'] or sorted(current.authors.values_list('name',flat=True))!=item['authors']:
        record['status']='identity_review_changed_during_lookup'
       elif Edition.objects.filter(isbn=isbn).exists():record.update(status='existing_isbn_preserved',isbn=isbn)
       else:
        edition=Edition.objects.create(work=current,is_archived=True,language='English',isbn=isbn,pages=e['number_of_pages'],pages_basis='isbn_matched',pages_source_url=url,source_url=url,publisher='; '.join(e.get('publishers',[]))[:240],translation_notes='Archived bibliographic candidate from Open Library. Publication: '+str(e.get('publish_date','unspecified'))+'. Publisher/library confirmation of identity, volume scope, completeness and physical pagination is required before making this edition selectable.')
        stats['added']+=1;record.update(status='found',disposition='archived_pending_bibliographic_confirmation',edition_id=edition.pk,isbn=isbn,source_url=url,provider_record=e,matched_work=matches[key])
      # Existing defaults, library choices, progress and plan allocations stay frozen.
    failures=0
   except Exception as error:
    record.update(status='provider_error',error=str(error)[:300]);failures+=1
   q.finish(item,record,audit);stats['processed']+=1
   (RUN/'latest-stats.json').write_text(json.dumps({**stats,**q.summary()},indent=2)+'\n')
   print(json.dumps({k:v for k,v in record.items() if k in ['work_id','title','status','edition_id','error']},ensure_ascii=False),flush=True)
   if failures>=3 or '429' in record.get('error','') or (args.limit and stats['processed']>=args.limit):break
 q.close();print(json.dumps(stats),flush=True)
if __name__=='__main__':
 with exclusive('exact-editions'):main()
