#!/usr/bin/env python3
"""Import the four owner-supplied Manga 800 demographic Top 200s."""
import argparse, hashlib, json, os, re, shutil, sys
from pathlib import Path
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.config.settings')
import django;django.setup()
from django.db import transaction
from backend.core.models import Ranking,Work
DATE='2026-09-14';RUN='2026-09-14-owner-chat-attachment';ATTACHMENT=Path('/Users/marcinswierczewski/.codex/attachments/363d9340-b39e-4fbe-ad74-65f4b3412a9a/pasted-text.txt')
CONFIG={'manga-shonen-all-time':('SHONEN','SHN',276),'manga-seinen-all-time':('SEINEN','SEI',253),'manga-shojo-all-time':('SHOJO','SHJ',273),'manga-josei-all-time':('JOSEI','JOS',304)}
def compact(v):return ' '.join(v.split())
def norm(v):return re.sub(r'[^a-z0-9]+','',v.casefold())
def fam(t,u):
 v=(t+' '+u).casefold();return 'reader_community' if any(x in v for x in ('read','reddit','goodreads','forum')) else 'academic_or_institutional' if any(x in v for x in ('schol','award','university','museum','library')) else 'editorial_or_specialist'
def authors(v):return [x.strip() for x in re.split(r'\s+(?:and|&)\s+|\s*,\s*',v) if x.strip()]
def rows(text,label,prefix):
 start=text.index(f'{label} TOP 200');end=text.index(f'{label}: WHY THE TOP TEN',start);part=text[start:end];out=[]
 for m in re.finditer(r'(?m)^(\d{3})\.\s+(.+?)\s+—\s+(.+?)\s+\|\s+(.+?)\s+\|\s+\[('+prefix+r'-\d{3})\]\s*$',part):out.append({'position':int(m.group(1)),'title':m.group(2).strip(),'creators':m.group(3).strip(),'genres':m.group(4).strip(),'ref':m.group(5)})
 if [x['position'] for x in out]!=list(range(1,201)):raise ValueError(f'{label}: parsed {len(out)} ranks')
 return out
def sources(text,label,prefix,count):
 start=text.index(f'{label}: COMPLETE LINKED BIBLIOGRAPHY');end=text.index({'SHONEN':'2. SEINEN TOP 200','SEINEN':'3. SHOJO TOP 200','SHOJO':'4. JOSEI TOP 200'}.get(label,'END OF JOSEI'),start);part=text[start:end];hs=list(re.finditer(r'(?m)^\[('+prefix+r'-\d{3})\]\s+([A-Z]+)\s+\|\s+(.+?)\s+\|\s+(.+?)\s*$',part));out=[];seen=set()
 for i,h in enumerate(hs):
  c=part[h.end():hs[i+1].start() if i+1<len(hs) else len(part)];sid,typ,lang,title=h.group(1),h.group(2),h.group(3),h.group(4).strip();u=re.search(r'(?m)^(https?://\S+)\s*$',c)
  if not u:raise ValueError(f'{sid} missing URL')
  url=u.group(1).rstrip('.,;)');can=url.rstrip('/');
  if can in seen:raise ValueError(f'{sid} duplicate URL')
  seen.add(can);access=(re.search(r'(?m)^Access:\s*(.+?)\s*$',c) or [None,''])[1]
  # The supplied bibliography explicitly records accessed text/excerpts for
  # work identity, demographic classification and reception context.  These
  # are eligible only for those narrow claims, not claims of critical consensus.
  out.append({'source_id':sid,'underlying_source_id':'url:'+hashlib.sha256(can.encode()).hexdigest()[:24],'title':title,'canonical_url':url,'source_family':fam(typ,url),'publisher':urlparse(url).netloc,'access_level':'full_relevant_content' if 'retrieved' in access.casefold() else 'relevant_excerpt','accessed_at':DATE,'count_eligible':True,'target_ids':[],'relevance_by_target':{},'evidence_notes':f'Owner-supplied {typ} source; reported access: {access}. Supports identity, publication-demographic classification, reception or stated context.','disagreement_or_limitations':'The supplied report states that most work-specific references are publication/reference records, not independent endorsements or proof of an exact rank. Access can be excerpt-level.','depends_on_source_ids':[],'report_type':typ,'report_language':lang,'report_access':access})
 if {x['source_id'] for x in out}!={f'{prefix}-{i:03d}' for i in range(1,count+1)}:raise ValueError(f'{label}: parsed {len(out)} sources')
 return out
def existing(title,creator):
 ws=list(Work.objects.filter(title__iexact=title,is_archived=False).prefetch_related('authors'));a={norm(x) for x in authors(creator)};b={norm(p.name) for p in ws[0].authors.all()} if len(ws)==1 else set();return [p.name for p in ws[0].authors.all()] if a and a==b else None
def main():
 p=argparse.ArgumentParser();p.add_argument('--target',choices=CONFIG,required=True);p.add_argument('--import-unattributed',action='store_true');p.add_argument('--build-selection',action='store_true');a=p.parse_args();target=a.target;label,prefix,count=CONFIG[target]
 incoming=ROOT/'research/incoming'/target/RUN/'report.txt';incoming.parent.mkdir(parents=True,exist_ok=True)
 if not incoming.exists():shutil.copy2(ATTACHMENT,incoming)
 text=incoming.read_text();rs=rows(text,label,prefix);ss=sources(text,label,prefix,count);digest=hashlib.sha256(incoming.read_bytes()).hexdigest();out=ROOT/'research'/target;out.mkdir(parents=True,exist_ok=True);ranking=Ranking.objects.get(slug=target,origin='curated',owner__isnull=True,is_archived=False)
 for s in ss:s['target_ids']=[target];s['relevance_by_target']={target:'Owner-supplied Manga 800 demographic synthesis source for this specific publishing/readership category.'}
 by={s['source_id']:s for s in ss};named=[];unresolved=[]
 for r in rs:
  names=existing(r['title'],r['creators']) or authors(r['creators']);rec={'key':f'{prefix.lower()}-{r["position"]:03d}','title':r['title'],'authors':names,'form':'collection','field':'manga','original_year':None,'original_language':'Japanese','countries':['Japan'],'description':f"Position {r['position']} in the owner-supplied {label.title()} Manga Top 200. Principal creator attribution: {r['creators']}. Genres/themes: {r['genres']}.",'work_source_url':by[r['ref']]['canonical_url'],'evidence_ids':[r['ref']],'edition':None,'english_availability_note':'Specific edition, translation and media remain to be verified.'};(named if names else unresolved).append(rec)
 (out/'sources.owner-chat-2026-09-14.json').write_text(json.dumps({'target_id':target,'ranking_entries':[],'sources':ss},ensure_ascii=False,indent=2)+'\n');(out/'owner-chat-candidates-2026-09-14.json').write_text(json.dumps({'target_id':target,'source_report':str(incoming.relative_to(ROOT)),'candidates':rs},ensure_ascii=False,indent=2)+'\n');(out/'owner-chat-catalog-2026-09-14.json').write_text(json.dumps({'schema_version':1,'allow_pending_editions':True,'works':named},ensure_ascii=False,indent=2)+'\n');(out/'owner-chat-unresolved-2026-09-14.json').write_text(json.dumps(unresolved,ensure_ascii=False,indent=2)+'\n');(incoming.parent/'RECEIPT.md').write_text(f'# Owner attachment receipt\n\n- Received: {DATE}\n- Requested action: populate {label.title()} manga Top 200.\n- SHA-256: `{digest}`\n- Parsed: 200 entries and {len(ss)} bibliography records.\n')
 if a.import_unattributed:
  got=[]
  with transaction.atomic():
   for r in unresolved:
    ms=list(Work.objects.filter(title__iexact=r['title'],authors__isnull=True,is_archived=False));
    if len(ms)>1:raise ValueError(r['title'])
    w=ms[0] if ms else Work(title=r['title'],form='collection',field='manga',original_language='Japanese',countries=['Japan'],description=r['description']);created=not ms
    if created:w.full_clean();w.save()
    got.append({'key':r['key'],'work_id':w.pk,'created_work':created})
  (out/'owner-chat-unresolved-2026-09-14-import-receipt.json').write_text(json.dumps({'records':got},indent=2)+'\n')
 if a.build_selection:
  ids={x['key']:x['work_id'] for x in json.loads((out/'owner-chat-catalog-2026-09-14-import-receipt.json').read_text())['records']};u=out/'owner-chat-unresolved-2026-09-14-import-receipt.json'
  if u.exists():ids.update({x['key']:x['work_id'] for x in json.loads(u.read_text())['records']})
  es=[];keys=[]
  for r in rs:
   key=f'{prefix.lower()}-{r["position"]:03d}';es.append({'key':key,'item_id':ids[key],'source_ids':[r['ref']],'standing':f"Position {r['position']} in the owner-supplied {label.title()} Manga Top 200. Genres/themes: {r['genres']}.",'reading':'No separately reasoned reading-value order was supplied; this view retains the demographic ranking order.','caveat':'The linked bibliography supports work identity, publishing-demographic classification, reception and context rather than an exact global consensus position. Source access varies and many records are excerpt-level.','metadata_status':'edition_and_media_pending','source_positions':[]});keys.append(key)
  batch={'target':target,'expected_revision':ranking.revision,'allow_expansion':True,'version':f'owner-chat-manga-800-{label.lower()}-2026-09-14','published_on':DATE,'allow_pending_metadata':True,'reviewed_exclusions':[],'notice':f'Owner-supplied Manga 800 {label.title()} Top 200. Source access limits and category-boundary qualifications are retained; no personal numerical scores are set.','method':f'Owner-supplied editorial demographic manga synthesis with {len(ss)} linked bibliography records. The supplied order is retained in both views pending a separately reasoned alternative.','entries':es,'orders':{'standing':{'label':f'{label.title()} editorial order','description':'The supplied Top 200 demographic order.','keys':keys},'reading':{'label':'Supplied order (reading-value view pending)','description':'No separate reading-value order was supplied.','keys':keys}}};(out/'owner-chat-selection-2026-09-14.json').write_text(json.dumps(batch,ensure_ascii=False,indent=2)+'\n')
 print(f'{target}: 200 entries, {len(ss)} sources, {len(named)} named and {len(unresolved)} authorless; SHA-256 {digest}')
if __name__=='__main__':main()
