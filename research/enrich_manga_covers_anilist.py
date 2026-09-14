"""Attach manga covers from AniList after strict title and creator matching."""
from __future__ import annotations
import argparse, hashlib, json, os, re, sys, time, unicodedata
from pathlib import Path
from urllib.request import Request, urlopen
ROOT=Path(__file__).resolve().parent.parent; sys.path.insert(0,str(ROOT))
RUN=ROOT/'research/_runs/2026-09-14/catalog-manga-anilist'; CACHE=RUN/'outcomes.jsonl'
QUERY='query ($s: String) { Page(perPage: 12) { media(search: $s, type: MANGA) { id title { romaji english native } coverImage { extraLarge large } siteUrl staff(perPage: 15) { edges { node { name { full } } role } } } } }'
HEADERS={'Content-Type':'application/json','User-Agent':'Marginalia catalogue enrichment/1.0'}
def plain(s): return unicodedata.normalize('NFKD',str(s)).encode('ascii','ignore').decode().casefold()
def norm(s): return re.sub(r'[^a-z0-9]','',plain(s))
def toks(s): return set(re.findall(r'[a-z0-9]+',plain(s)))
def title_ok(a,b):
 a,bn=norm(a),norm(b)
 if a==bn:return True
 if min(len(a),len(bn))>=10 and (a in bn or bn in a):return True
 x,y=toks(a),toks(b);return bool(x and y and len(x&y)/len(x|y)>=.8)
def author_ok(expected,edges):
 creators=[e['node']['name']['full'] for e in edges if e.get('role','').casefold() in {'story & art','story','art','original creator','character design'}]
 for a in expected:
  at=toks(a)
  for b in creators:
   bt=toks(b)
   if norm(a)==norm(b) or (len(at)>=2 and at==bt):return True
   # Romanisations often differ in given-name vowels (Eiichiro/ Eiichirou),
   # while the family name remains stable. Require an exact title separately.
   if len(at)>=2 and any(len(x)>=4 and x in bt for x in at):return True
 return False
def search_title(s):
 s=re.sub(r'\s*\([^)]*(?:including|original|all |adaptation|main series|remake)[^)]*\)\s*',' ',s,flags=re.I)
 return re.split(r'\s+/\s+',s,maxsplit=1)[0].strip()
def lookup(item):
 query_title=search_title(item['title']);body=json.dumps({'query':QUERY,'variables':{'s':query_title}}).encode(); err=None
 for delay in (0,2,5):
  if delay:time.sleep(delay)
  try:
   req=Request('https://graphql.anilist.co',data=body,headers=HEADERS)
   with urlopen(req,timeout=25) as r:data=json.load(r)
   break
  except Exception as e:err=e
 else:raise err
 matches=[]
 for row in data['data']['Page']['media']:
  titles=[row['title'].get(k) for k in ('romaji','english','native')]
  if any(title_ok(query_title,t) for t in titles if t) and author_ok(item['authors'],row['staff']['edges']):matches.append(row)
 if not matches:return None,'no_verified_match'
 exact=[r for r in matches if any(norm(item['title'])==norm(t) for t in r['title'].values() if t)]
 row=(exact or matches)[0]; image_url=row['coverImage'].get('extraLarge') or row['coverImage'].get('large')
 with urlopen(Request(image_url,headers={'User-Agent':HEADERS['User-Agent']}),timeout=25) as r:image=r.read()
 if len(image)<1024:return None,'cover_too_small'
 return {'id':row['id'],'source_url':row['siteUrl'],'image_url':image_url,'image':image},None
def completed(retry_no_match=False):
 out=set()
 if CACHE.exists():
  for line in CACHE.read_text().splitlines():
   try:
    row=json.loads(line)
    terminal={'covered','no_credited_author'} if retry_no_match else {'covered','no_verified_match','no_credited_author'}
    if row.get('status') in terminal:out.add(int(row['work_id']))
   except Exception:pass
 return out
def main():
 p=argparse.ArgumentParser();p.add_argument('--limit',type=int,default=100);p.add_argument('--delay',type=float,default=1.4);p.add_argument('--retry-no-match',action='store_true');a=p.parse_args()
 os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.config.settings');import django;django.setup()
 from django.core.files.base import ContentFile
 from django.db import transaction
 from backend.core.models import Work,Edition
 RUN.mkdir(parents=True,exist_ok=True);done=completed(a.retry_no_match);items=[]
 for w in Work.objects.filter(is_archived=False,field='manga').select_related('default_edition').prefetch_related('authors').order_by('pk'):
  if w.pk in done or (w.default_edition_id and w.default_edition.cover):continue
  items.append({'id':w.pk,'title':w.title,'authors':[x.name for x in w.authors.all()]})
  if a.limit and len(items)>=a.limit:break
 stats={'queued':len(items),'covered':0}
 with CACHE.open('a') as log:
  for n,item in enumerate(items,1):
   try:match,reason=lookup(item) if item['authors'] else (None,'no_credited_author')
   except Exception as e:match,reason=None,'error: '+str(e)[:180]
   row={'work_id':item['id'],'title':item['title'],'authors':item['authors']}
   if match:
    with transaction.atomic():
     w=Work.objects.select_for_update().get(pk=item['id'],is_archived=False);ed=w.default_edition
     if not ed:ed=Edition.objects.create(work=w,language='English');w.default_edition=ed;w.save(update_fields=['default_edition','updated_at'])
     digest=hashlib.sha256(match['image']).hexdigest()[:16];ed.cover.save(f"anilist-{match['id']}-{digest}.jpg",ContentFile(match['image']),save=False)
     ed.source_url=match['source_url'];ed.image_attribution=f"AniList manga record {match['source_url']} (cover: {match['image_url']})";ed.save(update_fields=['cover','source_url','image_attribution','updated_at'])
    row.update(status='covered',anilist_id=match['id'],source_url=match['source_url'],image_url=match['image_url'],edition_id=ed.pk);stats['covered']+=1
   else:row['status']=reason;key=reason.split(':',1)[0];stats[key]=stats.get(key,0)+1
   log.write(json.dumps(row,ensure_ascii=False)+'\n');log.flush();print(f"[{n}/{len(items)}] [{item['id']}] {row['status']} — {item['title']}",flush=True);time.sleep(a.delay)
 (RUN/'latest-stats.json').write_text(json.dumps(stats,indent=2)+'\n');print(json.dumps(stats,indent=2))
if __name__=='__main__':main()
