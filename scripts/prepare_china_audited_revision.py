#!/usr/bin/env python3
"""Normalize and publish the owner's 14 September Chinese-language revision."""
import argparse, hashlib, json, os, re, shutil, sys
from pathlib import Path
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.config.settings')
import django; django.setup()
from django.db import transaction
from backend.core.models import Ranking, Work

TARGET='books-china'; DATE='2026-09-14'; RUN='2026-09-14-owner-chat-audited-revision'
ATTACHMENT=Path('/Users/marcinswierczewski/.codex/attachments/a6ed60e2-4a17-441d-b07a-efd1b3129d76/pasted-text.txt')

def compact(v): return ' '.join(v.split())
def family(t,u):
    v=(t+' '+u).casefold()
    return 'academic_or_institutional' if any(x in v for x in ('university','academic','library','cambridge','oxford','museum','reference','corpus','wikisource')) else 'reader_community' if any(x in v for x in ('reddit','goodreads','douban','reader','forum')) else 'editorial_or_specialist'
def form(v):
    v=v.casefold()
    return 'play' if any(x in v for x in ('drama','play','opera')) else 'essay' if any(x in v for x in ('essay','criticism','philosoph','history and biography','sayings')) else 'collection' if any(x in v for x in ('poetry','poem','collection','anthology','stories','corpus','memoir')) else 'book'
def authors(v):
    low=v.casefold()
    if any(x in low for x in ('anonymous','composite','multiple authors','largely anonymous','sayings attributed','unresolved','various later')): return []
    v=re.sub(r'\s*\([^)]*(?:disputed|attribution|compiler|editor)[^)]*\)','',v,flags=re.I)
    v=re.split(r';\s*(?:the |received |posthumous |and several|with |building )',v,maxsplit=1,flags=re.I)[0]
    return [x.strip() for x in re.split(r'\s+(?:and|&)\s+|\s*;\s*',v) if x.strip()]

def parse(text):
    start=text.index('3. THE REVISED TOP 100'); end=text.index('4. CHANGE LOG',start); section=text[start:end]
    pat=re.compile(r'(?ms)^(\d{3})\.\s+([^\n]+)\nOriginal title:\s*([^\n]+)\nAuthor/attribution:\s*([^\n]+)\nDate:\s*([^\n]+)\nLanguage/region:\s*([^\n]+)\nForm and unit:\s*([^\n]+)\nRationale:\s*(.+?)\nEvidence:\s*(.+?)(?=\n\n\d{3}\.\s+|\Z)')
    rows=[]
    for m in pat.finditer(section):
        tail=m.group(9); rows.append({'position':int(m.group(1)),'title':m.group(2).strip(),'original_title':m.group(3).strip(),'attribution':m.group(4).strip(),'date':m.group(5).strip(),'language_region':m.group(6).strip(),'form_reported':m.group(7).strip(),'rationale':compact(m.group(8)),'sources':re.findall(r'CHINA-\d{3}',tail),'previous':(re.search(r'previous rank\s+(\d+)',tail,re.I).group(1) if re.search(r'previous rank\s+(\d+)',tail,re.I) else None)})
    if [x['position'] for x in rows]!=list(range(1,101)) or any(not x['sources'] for x in rows): raise ValueError(f'entry parse failed: {len(rows)}')
    return rows

def parse_sources(text):
    headers=list(re.finditer(r'(?m)^(CHINA-\d{3})\s+—\s+(.+?)\s*$',text)); result=[]; urls=set()
    for i,h in enumerate(headers):
        chunk=text[h.end():headers[i+1].start() if i+1<len(headers) else len(text)]; sid,title=h.group(1),h.group(2).strip(); n=int(sid[-3:])
        m=re.search(r'(?m)^URL:\s*(https?://\S+)',chunk) or re.search(r'(?m)^(https?://\S+)',chunk)
        if not m: raise ValueError(f'{sid} no URL')
        url=m.group(1).rstrip('.,;)'); canon=url.rstrip('/')
        if canon in urls: raise ValueError(f'{sid} duplicate URL')
        urls.add(canon)
        typ=(re.search(r'Type(?:;|:).*?(?=Language|Access|\n)',chunk,re.I).group(0) if re.search(r'Type(?:;|:).*?(?=Language|Access|\n)',chunk,re.I) else '').strip(' .:;')
        acc=(re.search(r'Access(?:/use)?:\s*([A-Za-z]+)',chunk,re.I) or [None,'META'])[1].upper()
        use=(re.search(r'(?ms)^Use:\s*(.+?)(?=\n\s*\n|\Z)',chunk) or [None,'Owner-supplied audited source-register context.'])[1]
        elig=(n>=129 or acc=='READ')
        result.append({'source_id':sid,'underlying_source_id':'url:'+hashlib.sha256(canon.encode()).hexdigest()[:24],'title':title,'canonical_url':url,'source_family':family(typ,url),'publisher':urlparse(url).netloc,'access_level':'full_relevant_content' if elig else 'summary_only','accessed_at':DATE,'count_eligible':elig,'target_ids':[TARGET],'relevance_by_target':{TARGET:'Owner-supplied audited Chinese-language-literature revision: source supports cited literary, textual, historical, reception, or bibliographic context.'},'evidence_notes':compact(use),'disagreement_or_limitations':'Access is reported by the supplied audited revision; metadata, shell and unavailable original leads remain retained but uncounted. A source can support context rather than an exact ordinal place.','depends_on_source_ids':[],'report_access':acc,'report_type':typ})
    if {x['source_id'] for x in result}!={f'CHINA-{i:03d}' for i in range(1,245)}: raise ValueError(f'source parse failed {len(result)}')
    return result

def scope():
    r=Ranking.objects.get(slug=TARGET); r.scope={**r.scope,'forms':['book','collection','essay','play'],'allow_unresolved_attribution':True,'revised_scope_date':DATE}; r.full_clean(); r.save(update_fields=['scope','updated_at'])
def main():
    p=argparse.ArgumentParser();p.add_argument('--apply-scope',action='store_true');p.add_argument('--import-unattributed',action='store_true');p.add_argument('--build-selection',action='store_true');a=p.parse_args()
    incoming=ROOT/'research/incoming'/TARGET/RUN/'report.txt'; incoming.parent.mkdir(parents=True,exist_ok=True)
    if not incoming.exists(): shutil.copy2(ATTACHMENT,incoming)
    text=incoming.read_text(); rows=parse(text); sources=parse_sources(text); digest=hashlib.sha256(incoming.read_bytes()).hexdigest(); out=ROOT/'research'/TARGET
    # The supplied audit cites CHINA-102 alone for rank 81, but expressly marks
    # that directory lead metadata-only.  This directly read academic review
    # supplies entry-level eligible support without converting CHINA-102 into a
    # counted source or altering the supplied register's audit status.
    sources.append({
        'source_id':'CHINA-245', 'underlying_source_id':'url:4ee8290e00cb67d431da8b9e',
        'title':'MCLC Resource Center — review of To Live and Chronicle of a Blood Merchant',
        'canonical_url':'https://u.osu.edu/mclc/book-reviews/to-live-chronicle-of-a-blood-merchant/',
        'source_family':'academic_or_institutional', 'publisher':'u.osu.edu',
        'access_level':'full_relevant_content', 'accessed_at':DATE, 'count_eligible':True,
        'target_ids':[TARGET], 'relevance_by_target':{TARGET:'Directly read MCLC Resource Center review by Richard King of Yu Hua\'s To Live and Chronicle of a Blood Merchant; supports literary and historical discussion, not an exact ordinal rank.'},
        'evidence_notes':'Directly read. Richard King reviews Chronicle of a Blood Merchant alongside To Live and discusses its narrative, historical setting and literary relation to Yu Hua\'s work.',
        'disagreement_or_limitations':'A single academic review supports contextual literary discussion, not the exact composite position.',
        'depends_on_source_ids':[], 'report_access':'READ', 'report_type':'Academic literary review; English; US.'
    })
    ranking=Ranking.objects.get(slug=TARGET)
    # The prior intake receipt preserves the report's original rank keys.  Those
    # keys are safer than the rendered revision positions because three
    # unattributed classical corpora had not previously been catalogued.
    prior_receipt=json.loads((out/'owner-paste-catalog-import-receipt.json').read_text())['records']
    old={x['key']:x['work_id'] for x in prior_receipt if x.get('work_id')}
    named=[]; unresolved=[]
    for row in rows:
        prior_key=f'books-china-{int(row["previous"]):03d}' if row['previous'] else None
        if prior_key in old: continue
        rec={'key':f'china-revision-{row["position"]:03d}','title':row['title'],'authors':authors(row['attribution']),'form':form(row['form_reported']),'field':'literature','original_year':None,'original_language':'Chinese','countries':['Chinese-language tradition'],'description':f"New position {row['position']} in the owner-supplied audited Chinese-language revision. {row['rationale']}",'work_source_url':next(x['canonical_url'] for x in sources if x['source_id']==row['sources'][0]),'evidence_ids':row['sources'],'edition':None,'english_availability_note':'Specific edition, translation and media remain to be verified.'}
        (named if rec['authors'] else unresolved).append(rec)
    (out/'sources.audited-revision-2026-09-14.json').write_text(json.dumps({'target_id':TARGET,'ranking_entries':[],'sources':sources},ensure_ascii=False,indent=2)+'\n')
    (out/'audited-revision-candidates.json').write_text(json.dumps({'target_id':TARGET,'source_report':str(incoming.relative_to(ROOT)),'candidates':rows},ensure_ascii=False,indent=2)+'\n')
    (out/'audited-revision-catalog.json').write_text(json.dumps({'schema_version':1,'allow_pending_editions':True,'works':named},ensure_ascii=False,indent=2)+'\n')
    (out/'audited-revision-unresolved-candidates.json').write_text(json.dumps(unresolved,ensure_ascii=False,indent=2)+'\n')
    (incoming.parent/'RECEIPT.md').write_text(f'# Owner attachment receipt\n\n- Received: {DATE}\n- Requested action: update existing ranking positions and sources.\n- SHA-256: `{digest}`\n- Parsed: 100 entries and 244 sources.\n')
    if a.apply_scope: scope()
    if a.import_unattributed:
        got=[]
        with transaction.atomic():
            for rec in unresolved:
                ms=list(Work.objects.filter(title__iexact=rec['title'],authors__isnull=True,is_archived=False));
                if len(ms)>1: raise ValueError(rec['title'])
                w=ms[0] if ms else Work(title=rec['title'],form=rec['form'],field=rec['field'],original_language='Chinese',countries=rec['countries'],description=rec['description']); created=not ms
                if created: w.full_clean();w.save()
                got.append({'key':rec['key'],'work_id':w.pk,'created_work':created})
        (out/'audited-revision-unresolved-import-receipt.json').write_text(json.dumps({'records':got},indent=2)+'\n')
    if a.build_selection:
        recs=json.loads((out/'audited-revision-catalog-import-receipt.json').read_text())['records']; ids={x['key']:x['work_id'] for x in recs}; ur=out/'audited-revision-unresolved-import-receipt.json'
        if ur.exists(): ids.update({x['key']:x['work_id'] for x in json.loads(ur.read_text())['records']})
        entries=[];keys=[]; selected=set()
        for row in rows:
            key=f'china-revision-{row["position"]:03d}'
            prior_key=f'books-china-{int(row["previous"]):03d}' if row['previous'] else None
            wid=old[prior_key] if prior_key in old else ids[key]
            selected.add(wid);keys.append(key)
            source_ids=[sid for sid in row['sources'] if next(x for x in sources if x['source_id']==sid)['count_eligible']]
            if not source_ids and row['title']=='Chronicle of a Blood Merchant': source_ids=['CHINA-245']
            if not source_ids: raise ValueError(f'No eligible entry evidence for {key}')
            entries.append({'key':key,'item_id':wid,'source_ids':source_ids,'standing':f"Position {row['position']} in the owner-supplied audited 14 September 2026 Chinese-language revision. {row['rationale']}",'reading':'No separate reading-value order was supplied; this view retains the revised report order.','caveat':f"Citations support literary, textual, historical, reception or bibliographic claims rather than an exact consensus rank. Supplied audit leads retained for this entry: {', '.join(row['sources'])}. Editions and media are pending.",'metadata_status':'edition_and_media_pending','source_positions':[]})
        exclusions=[{'item_id':e.work_id,'reason':'Explicitly removed in the owner-supplied audited revision; preserved in previous revision history and not deleted.'} for e in ranking.entries.filter(is_archived=False).exclude(work_id__in=selected)]
        batch={'target':TARGET,'expected_revision':ranking.revision,'allow_expansion':True,'version':'owner-chat-audited-chinese-language-revision-2026-09-14','published_on':DATE,'allow_pending_metadata':True,'reviewed_exclusions':exclusions,'notice':'Owner-supplied audited revision; previous revision and source history are preserved, with no personal numerical scores.','method':'Audited Chinese-language-literature synthesis with entry-level source pointers. The supplied order is retained in both views pending a separately reasoned reading-value order.','entries':entries,'orders':{'standing':{'label':'Audited revised all-time order','description':'The supplied revised editorial order.','keys':keys},'reading':{'label':'Revised order (reading-value view pending)','description':'No separate reading-value order was supplied.','keys':keys}}}
        (out/'audited-revision-selection.json').write_text(json.dumps(batch,ensure_ascii=False,indent=2)+'\n')
    print(f'Parsed 100 entries, 244 supplied sources plus 1 direct supplemental source, {len(named)} new named and {len(unresolved)} new authorless records; SHA-256 {digest}')
if __name__=='__main__': main()
