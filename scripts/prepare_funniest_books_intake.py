#!/usr/bin/env python3
"""Normalize and publish the owner's funniest-books Top 150 report."""
import argparse, hashlib, json, os, re, shutil, sys
from pathlib import Path
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.config.settings')
import django; django.setup()
from django.db import transaction
from backend.core.models import Ranking, Work
TARGET='books-funniest-all-time'; DATE='2026-09-14'; RUN='2026-09-14-owner-chat-attachment'
ATTACHMENT=Path('/Users/marcinswierczewski/.codex/attachments/70c6cde7-3849-408d-8773-4fa94dece267/pasted-text.txt')
SUPPLEMENTS={
 22:('FUNNY-S352','Postgraduate English — Comedy and Madness in Swift: The Idiosyncrasies of Lemuel Gulliver','https://postgradenglishjournal.awh.durham.ac.uk/ojs/index.php/pgenglish/article/view/217','Directly read scholarly article on comedy, caricature and satire in Gulliver’s Travels.'),
 49:('FUNNY-S353','The Guardian — Broken Glass review','https://www.theguardian.com/books/2009/feb/21/broken-glass-mabanckou-review','Directly read review discussing Mabanckou’s comic brio and the novel’s spectrum of humour.'),
 107:('FUNNY-S354','O Eixo e a Roda — irony in Machado de Assis’s O alienista','https://periodicos.ufmg.br/index.php/o_eixo_ea_roda/article/view/28507','Directly read scholarly article on the novella’s irony and satire.'),
}

def compact(v): return ' '.join(v.split())
def norm(v): return re.sub(r'[^a-z0-9]+','',v.casefold())
def year(v):
 m=re.search(r'(?<!\d)(\d{3,4})(?!\d)',v); return int(m.group(1)) if m else None
def family(v,u):
 v=(v+' '+u).casefold()
 return 'academic_or_institutional' if any(x in v for x in ('scholarly','university','library','institution','academic','museum','reference')) else 'reader_community' if any(x in v for x in ('reader community','reddit','goodreads','forum','storygraph')) else 'editorial_or_specialist'
def form(v):
 v=v.casefold()
 if 'play' in v: return 'play'
 if 'essay' in v or 'column' in v: return 'essay'
 if 'poem' in v or 'verse' in v: return 'poem'
 if 'short stor' in v or 'miniature' in v: return 'collection'
 return 'collection' if 'cycle' in v or 'collection' in v else 'book'
def authors(v):
 low=v.casefold()
 if any(x in low for x in ('anonymous','multiple authors','collective','traditionally attributed')): return []
 return [x.strip() for x in re.split(r'\s+(?:and|&)\s+|\s*;\s*',v) if x.strip()]
def entries(text):
 section=text[text.index('RANKED TOP 150'):text.index('SOURCE LEDGER')]
 pat=re.compile(r'(?ms)^(\d{3})\.\s+(.+?)\s+—\s+(.+?)\nDate:\s*(.+?)\nForm:\s*(.+?)\nTradition:\s*(.+?)\s*\|\s*Original language:\s*(.+?)\nWhy here:\s*(.+?)(?:\nEdition/context:\s*(.+?))?\nSources:\s*(.+?)(?=\n\n\d{3}\.\s+|\Z)')
 out=[]
 for m in pat.finditer(section): out.append({'position':int(m.group(1)),'title':m.group(2).strip(),'attribution':m.group(3).strip(),'date':m.group(4).strip(),'form_reported':m.group(5).strip(),'tradition':m.group(6).strip(),'language':m.group(7).strip(),'rationale':compact(m.group(8)),'context':compact(m.group(9) or ''),'refs':re.findall(r'S\d{3}',m.group(10))})
 if [r['position'] for r in out]!=list(range(1,151)) or any(not r['refs'] for r in out): raise ValueError(f'entry parse failed: {len(out)}')
 return out
def sources(text):
 section=text[text.index('SOURCE LEDGER'):]; hs=list(re.finditer(r'(?m)^\[S(\d{3})\]\s+(.+?)\s*$',section)); result=[]; seen=set()
 for i,h in enumerate(hs):
  c=section[h.end():hs[i+1].start() if i+1<len(hs) else len(section)]; n,title=h.group(1),h.group(2).strip(); u=re.search(r'(?m)^URL:\s*(https?://\S+)',c)
  if not u: raise ValueError(f'S{n} no URL')
  url=u.group(1).rstrip('.,;)'); can=url.rstrip('/')
  if can in seen: raise ValueError(f'S{n} duplicate URL')
  seen.add(can); typ=(re.search(r'(?m)^Type:\s*(.+?)\s*$',c) or [None,''])[1]; access=(re.search(r'(?m)^.*Evidence viewed:\s*(.+?)\s*$',c) or [None,''])[1]; use=(re.search(r'(?m)^Used for:\s*(.+?)\s*$',c) or [None,'Owner-supplied source-register context.'])[1]
  eligible='page passages' in access.casefold() or 'full' in access.casefold()
  result.append({'source_id':f'FUNNY-S{n}','underlying_source_id':'url:'+hashlib.sha256(can.encode()).hexdigest()[:24],'title':title,'canonical_url':url,'source_family':family(typ,url),'publisher':urlparse(url).netloc,'access_level':'full_relevant_content' if eligible else 'relevant_excerpt','accessed_at':DATE,'count_eligible':eligible,'target_ids':[TARGET],'relevance_by_target':{TARGET:'Owner-supplied global humour synthesis source for comic form, reception, critical context, comparative method or stated limitation.'},'evidence_notes':compact(use),'disagreement_or_limitations':'Access is reported by the supplied source ledger. A source supports comic reception, context or form rather than the exact editorial position; indexed-only records remain uncounted.','depends_on_source_ids':[],'report_source_number':f'S{n}','report_type':typ,'report_access':access})
 if {x['report_source_number'] for x in result}!={f'S{i:03d}' for i in range(1,352)}: raise ValueError(f'source parse failed: {len(result)}')
 return result
def append_supplements(src):
 # The report labelled S338 indexed-only, but its exact direct page was read
 # during this intake for its limited parody/reception context.
 for record in src:
  if record['source_id']=='FUNNY-S338':
   record['count_eligible']=True;record['access_level']='full_relevant_content';record['evidence_notes'] += ' Directly read during intake for the page’s limited parody/satire and reception context.';record['disagreement_or_limitations']='The supplied ledger labelled this source indexed-only; direct intake review supports only its narrow bibliographic and satire-context use, not the exact placement.'
 for pos,(sid,title,url,note) in SUPPLEMENTS.items(): src.append({'source_id':sid,'underlying_source_id':'url:'+hashlib.sha256(url.rstrip('/').encode()).hexdigest()[:24],'title':title,'canonical_url':url,'source_family':'academic_or_institutional' if pos in {22,107} else 'editorial_or_specialist','publisher':urlparse(url).netloc,'access_level':'full_relevant_content','accessed_at':DATE,'count_eligible':True,'target_ids':[TARGET],'relevance_by_target':{TARGET:f'Directly read supplementary source for rank {pos}; supports comic form/reception context rather than its exact composite position.'},'evidence_notes':note,'disagreement_or_limitations':'A narrow supplementary source; original indexed-only leads remain retained and uncounted.','depends_on_source_ids':[],'report_source_number':None,'report_type':'Supplementary directly read source','report_access':'READ'})
 return src
def existing(title, attribution):
 ws=list(Work.objects.filter(title__iexact=title,is_archived=False).prefetch_related('authors')); supplied={norm(x) for x in authors(attribution)}; actual={norm(a.name) for a in ws[0].authors.all()} if len(ws)==1 else set()
 return [a.name for a in ws[0].authors.all()] if supplied and supplied==actual else None
def main():
 p=argparse.ArgumentParser(); p.add_argument('--apply-scope',action='store_true');p.add_argument('--import-unattributed',action='store_true');p.add_argument('--build-selection',action='store_true');a=p.parse_args()
 incoming=ROOT/'research/incoming'/TARGET/RUN/'report.txt';incoming.parent.mkdir(parents=True,exist_ok=True)
 if not incoming.exists(): shutil.copy2(ATTACHMENT,incoming)
 text=incoming.read_text(); rows=entries(text); src=append_supplements(sources(text));by={x['report_source_number']:x for x in src};out=ROOT/'research'/TARGET;out.mkdir(parents=True,exist_ok=True);digest=hashlib.sha256(incoming.read_bytes()).hexdigest();ranking=Ranking.objects.get(slug=TARGET,origin='curated',owner__isnull=True,is_archived=False)
 if a.apply_scope:
  if ranking.entries.filter(is_archived=False).exists(): raise ValueError('Target already published.')
  ranking.scope={'forms':['book','collection','essay','play','poem','short_story'],'theme':'humour','ranking_question':'Literary works of exceptional comic force across global traditions and forms.','allow_unresolved_attribution':True};ranking.description='A global, cross-form researched ranking of literary works by sustained comic effectiveness, invention, literary quality, influence and translation-sensitive reception.';ranking.full_clean();ranking.save(update_fields=['scope','description','updated_at'])
 named=[];unresolved=[]
 for r in rows:
  names=existing(r['title'],r['attribution']) or authors(r['attribution']);rec={'key':f'funniest-owner-{r["position"]:03d}','title':r['title'],'authors':names,'form':form(r['form_reported']),'field':'literature','original_year':year(r['date']),'original_language':r['language'],'countries':[r['tradition']],'description':f"Position {r['position']} in the owner-supplied funniest-books synthesis. Attribution: {r['attribution']}. Date: {r['date']}. Form: {r['form_reported']}. {r['rationale']}",'work_source_url':by[r['refs'][0]]['canonical_url'],'evidence_ids':[by[x]['source_id'] for x in r['refs']],'edition':None,'english_availability_note':'Specific edition, translation and media remain to be verified.'};(named if names else unresolved).append(rec)
 (out/'sources.owner-chat-2026-09-14.json').write_text(json.dumps({'target_id':TARGET,'ranking_entries':[],'sources':src},ensure_ascii=False,indent=2)+'\n');(out/'owner-chat-candidates-2026-09-14.json').write_text(json.dumps({'target_id':TARGET,'source_report':str(incoming.relative_to(ROOT)),'candidates':rows},ensure_ascii=False,indent=2)+'\n');(out/'owner-chat-catalog-2026-09-14.json').write_text(json.dumps({'schema_version':1,'allow_pending_editions':True,'works':named},ensure_ascii=False,indent=2)+'\n');(out/'owner-chat-unresolved-2026-09-14.json').write_text(json.dumps(unresolved,ensure_ascii=False,indent=2)+'\n');(incoming.parent/'RECEIPT.md').write_text(f'# Owner attachment receipt\n\n- Received: {DATE}\n- Requested action: populate existing funniest-books template.\n- SHA-256: `{digest}`\n- Parsed: 150 entries and 351 sources.\n')
 if a.import_unattributed:
  got=[]
  with transaction.atomic():
   for r in unresolved:
    ms=list(Work.objects.filter(title__iexact=r['title'],authors__isnull=True,is_archived=False));
    if len(ms)>1: raise ValueError(r['title'])
    w=ms[0] if ms else Work(title=r['title'],form=r['form'],field=r['field'],original_year=r['original_year'],original_language=r['original_language'],countries=r['countries'],description=r['description']);created=not ms
    if created: w.full_clean();w.save()
    got.append({'key':r['key'],'work_id':w.pk,'created_work':created})
  (out/'owner-chat-unresolved-2026-09-14-import-receipt.json').write_text(json.dumps({'records':got},ensure_ascii=False,indent=2)+'\n')
 if a.build_selection:
  ids={x['key']:x['work_id'] for x in json.loads((out/'owner-chat-catalog-2026-09-14-import-receipt.json').read_text())['records']};ur=out/'owner-chat-unresolved-2026-09-14-import-receipt.json'
  if ur.exists():ids.update({x['key']:x['work_id'] for x in json.loads(ur.read_text())['records']})
  items=[];keys=[]
  for r in rows:
   key=f'funniest-owner-{r["position"]:03d}';sids=[by[x]['source_id'] for x in r['refs'] if by[x]['count_eligible']]
   if not sids and r['position'] in SUPPLEMENTS:sids=[SUPPLEMENTS[r['position']][0]]
   if not sids:raise ValueError(f'No eligible entry evidence: {r["position"]} {r["title"]}')
   items.append({'key':key,'item_id':ids[key],'source_ids':sids,'standing':f"Position {r['position']} in the owner-supplied 14 September 2026 funniest-books synthesis. {r['rationale']}",'reading':f"The supplied order reflects comic force and reception. {r['rationale']}",'caveat':f"{r['context']} The supplied source references are {', '.join(r['refs'])}; they support comic form, reception or context rather than an exact consensus position.",'metadata_status':'edition_and_media_pending','source_positions':[]});keys.append(key)
  batch={'target':TARGET,'expected_revision':ranking.revision,'allow_expansion':True,'version':'owner-chat-funniest-books-top-150-2026-09-14','published_on':DATE,'allow_pending_metadata':True,'reviewed_exclusions':[],'notice':'Owner-supplied global humour Top 150; source access limits are retained and no personal numerical scores are set.','method':'Owner-supplied editorial synthesis of 351 linked target-local sources. The supplied order is retained in both views pending a separately reasoned alternative.','entries':items,'orders':{'standing':{'label':'Comic force','description':'The supplied editorial Top 150 order.','keys':keys},'reading':{'label':'Supplied order (alternative view pending)','description':'No separately reasoned alternative order was supplied.','keys':keys}}};(out/'owner-chat-selection-2026-09-14.json').write_text(json.dumps(batch,ensure_ascii=False,indent=2)+'\n')
 print(f'Parsed 150 entries, {len(src)} sources ({sum(x["count_eligible"] for x in src)} eligible), {len(named)} named and {len(unresolved)} authorless; SHA-256 {digest}')
if __name__=='__main__':main()
