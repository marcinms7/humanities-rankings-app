"""Second-source manga cover fallback using Kitsu's public catalogue."""
from __future__ import annotations
import argparse,hashlib,json,os,re,sys,time,unicodedata
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT));RUN=ROOT/'research/_runs/2026-09-14/catalog-manga-kitsu';CACHE=RUN/'outcomes.jsonl';UA='Marginalia catalogue enrichment/1.0'
def norm(s):return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',str(s)).encode('ascii','ignore').decode().casefold())
def clean(s):
 s=re.sub(r'\s*\([^)]*\)\s*',' ',s).strip();return re.split(r'\s+/\s+',s,maxsplit=1)[0].strip()
def fetch(url):
 with urlopen(Request(url,headers={'Accept':'application/vnd.api+json','User-Agent':UA}),timeout=25) as r:return json.load(r)
def lookup(item):
 q=clean(item['title']);url='https://kitsu.io/api/edge/manga?'+urlencode({'filter[text]':q,'page[limit]':20});data=fetch(url);choices=[]
 for row in data.get('data',[]):
  a=row.get('attributes',{});names=[a.get('canonicalTitle'),*(a.get('titles') or {}).values()]
  if not any(norm(q)==norm(x) for x in names if x):continue
  year=None
  try:year=int((a.get('startDate') or '')[:4])
  except Exception:pass
  if item['year'] and year and abs(item['year']-year)>3:continue
  image=(a.get('posterImage') or {}).get('original') or (a.get('posterImage') or {}).get('large')
  if image:choices.append((row,year,image))
 if len(choices)!=1:return None,'ambiguous_or_no_exact_match'
 row,year,image_url=choices[0]
 with urlopen(Request(image_url,headers={'User-Agent':UA}),timeout=25) as r:image=r.read()
 if len(image)<1024:return None,'cover_too_small'
 return {'id':row['id'],'source_url':f"https://kitsu.app/manga/{row['id']}",'image_url':image_url,'image':image},None
def main():
 p=argparse.ArgumentParser();p.add_argument('--limit',type=int,default=0);p.add_argument('--delay',type=float,default=.7);a=p.parse_args();os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.config.settings');import django;django.setup()
 from django.core.files.base import ContentFile
 from django.db import transaction
 from backend.core.models import Work,Edition
 RUN.mkdir(parents=True,exist_ok=True);items=[]
 for w in Work.objects.filter(is_archived=False,field='manga').select_related('default_edition').order_by('pk'):
  if w.default_edition_id and w.default_edition.cover:continue
  items.append({'id':w.pk,'title':w.title,'year':w.original_year})
  if a.limit and len(items)>=a.limit:break
 stats={'queued':len(items),'covered':0}
 with CACHE.open('a') as log:
  for n,item in enumerate(items,1):
   try:m,reason=lookup(item)
   except Exception as e:m,reason=None,'error: '+str(e)[:180]
   row={'work_id':item['id'],'title':item['title'],'year':item['year']}
   if m:
    with transaction.atomic():
     w=Work.objects.select_for_update().get(pk=item['id'],is_archived=False);ed=w.default_edition
     if not ed:ed=Edition.objects.create(work=w,language='English');w.default_edition=ed;w.save(update_fields=['default_edition','updated_at'])
     digest=hashlib.sha256(m['image']).hexdigest()[:16];ed.cover.save(f"kitsu-{m['id']}-{digest}.jpg",ContentFile(m['image']),save=False);ed.source_url=m['source_url'];ed.image_attribution=f"Kitsu manga record {m['source_url']} (cover: {m['image_url']})";ed.save(update_fields=['cover','source_url','image_attribution','updated_at'])
    row.update(status='covered',kitsu_id=m['id'],source_url=m['source_url'],image_url=m['image_url'],edition_id=ed.pk);stats['covered']+=1
   else:row['status']=reason;key=reason.split(':',1)[0];stats[key]=stats.get(key,0)+1
   log.write(json.dumps(row,ensure_ascii=False)+'\n');log.flush();print(f"[{n}/{len(items)}] [{item['id']}] {row['status']} — {item['title']}",flush=True);time.sleep(a.delay)
 (RUN/'latest-stats.json').write_text(json.dumps(stats,indent=2)+'\n');print(json.dumps(stats,indent=2))
if __name__=='__main__':main()
