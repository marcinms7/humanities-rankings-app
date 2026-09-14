#!/usr/bin/env python3
"""Normalize the owner's page-turner and mainstream-loved Top 150 reports."""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.config.settings')
import django
django.setup()

from django.db import transaction
from backend.core.models import Ranking, Work

DATE = '2026-09-14'
RUN = '2026-09-14-owner-chat-attachments'
REPORTS = {
    'books-addictive-all-time': {
        'attachment': Path('/Users/marcinswierczewski/.codex/attachments/688c8169-29d2-4854-875f-a28173ff1326/pasted-text.txt'),
        'kind': 'page_turners', 'prefix': 'PAGETURNERS', 'source_count': 280,
        'title': 'The Ultimate Page-Turners',
        'scope': {'forms': ['book', 'collection'], 'theme': 'compulsive_reading', 'ranking_question': 'Prose fiction and narrative nonfiction readers report being unable to put down.'},
        'description': 'A researched global ranking of prose fiction and narrative nonfiction by compulsive readability: narrative propulsion, suspense, emotional stakes and reader-reported inability to stop reading.',
    },
    'books-mainstream-loved-all-time': {
        'attachment': Path('/Users/marcinswierczewski/.codex/attachments/6c3771c6-4bc1-4910-b2df-75057c8dc1cd/pasted-text.txt'),
        'kind': 'mainstream_loved', 'prefix': 'MAINSTREAM', 'source_count': 279,
        'title': 'Most Mainstream-Loved Books Ever Written',
        'scope': {'forms': ['book', 'collection', 'poem'], 'theme': 'mainstream_love', 'ranking_question': 'Books, defined series/collections and verse works with unusually broad, enduring mainstream reader affection.', 'allow_unresolved_attribution': True},
        'description': 'A global researched ranking of books, defined series and collections by enduring mainstream reader affection, combining reader votes, circulation, rereading, cultural transmission and cross-language reception.',
    },
}

SUPPLEMENTARY_ENTRY_SOURCES = {
    'books-addictive-all-time': {
        142: ('PAGETURNERS-S281', 'Science Fiction Studies — Flowers for Algernon: When Disability Meets Animality', 'https://online.ucpress.edu/sfs/article/53/1/105/217350/Flowers-for-AlgernonWhen-Disability-Meets', 'Academic literary article directly read for the novel’s narrative, emotional and disability-literature context.'),
    },
    'books-mainstream-loved-all-time': {
        106: ('MAINSTREAM-S280', 'The Complete Review — The Rainbow Troops', 'https://www.complete-review.com/reviews/indonesia/hirataa.htm', 'Directly read review and review-summary page for the Indonesian novel’s publication, translation, reception and reader appeal.'),
        107: ('MAINSTREAM-S281', 'The Complete Review — Pather Panchali', 'https://www.complete-review.com/reviews/bengali/bandopadhyayb.htm', 'Directly read review and review-summary page for the Bengali novel’s publication, translation, critical reception and reader appeal.'),
    },
}

# Established catalog identities use normalized author names or aliases.  The
# owner report supplies fuller attribution strings (for example collaborators
# and transliteration variants); keep the existing well-identified works rather
# than making parallel catalog records solely to mirror that display wording.
SELECTION_WORK_OVERRIDES = {
    'books-mainstream-loved-all-time': {17: 298, 74: 3082, 89: 283, 92: 920, 114: 1224, 115: 6369, 140: 2231},
}


def compact(value):
    return ' '.join(value.split())


def norm(value):
    return re.sub(r'[^a-z0-9]+', '', value.casefold())


def year(value):
    match = re.search(r'(?<!\d)(\d{3,4})(?!\d)', value)
    return int(match.group(1)) if match else None


def family(label, url):
    value = f'{label} {url}'.casefold()
    if any(term in value for term in ('academic', 'research', 'university', 'library', 'institutional', 'reference', 'museum', 'archive')):
        return 'academic_or_institutional'
    if any(term in value for term in ('reddit', 'goodreads', 'storygraph', 'forum', 'reader-community', 'reader testimony', 'community')):
        return 'reader_community'
    return 'editorial_or_specialist'


def authors(value):
    value = value.strip()
    low = value.casefold()
    if any(term in low for term in ('multiple authors', 'scripture', 'traditionally revealed', 'multiple storytellers', 'anonymous', 'oral tradition')):
        return []
    value = re.sub(r'^traditionally attributed to\s+', '', value, flags=re.I)
    value = re.sub(r'\s*\([^)]*(?:illustrated|edited|translator|collected|completed|compiler)[^)]*\)', '', value, flags=re.I)
    value = re.split(r';\s*(?:illustrated|edited|initially|with |collectors|traditional|the |first )', value, maxsplit=1, flags=re.I)[0]
    value = value.strip(' ;,.')
    return [part.strip() for part in re.split(r'\s+(?:and|&)\s+|\s*;\s*', value) if part.strip()]


def form_for(title, source_form=''):
    value = f'{title} {source_form}'.casefold()
    return 'collection' if any(word in value for word in ('series', 'trilogy', 'seven-book', 'fourteen novels', 'collected', 'tales', 'scripture', 'quran', 'bible')) else 'book'


def parse_page_turners(text):
    start = text.index('RANKED TOP 150')
    end = text.index('COMPLETE SOURCE BIBLIOGRAPHY', start)
    section = text[start:end]
    pattern = re.compile(
        r'(?ms)^(\d{3})\.\s+(.+?)\s+—\s+(.+?)\n'
        r'First publication:\s*(.+?)\s*\|\s*Literary affiliation:\s*(.+?)\s*\|\s*Language:\s*(.+?)\s*\|\s*Genre:\s*(.+?)\n'
        r'Why it pulls:\s*(.+?)\nPace / fit:\s*(.+?)\nEvidence:\s*(.+?)(?=\n\n\d{3}\.\s+|\Z)'
    )
    rows=[]
    for m in pattern.finditer(section):
        rows.append({'position':int(m.group(1)), 'title':m.group(2).strip(), 'attribution':m.group(3).strip(), 'date':m.group(4).strip(), 'tradition':m.group(5).strip(), 'language':m.group(6).strip(), 'form_reported':m.group(7).strip(), 'rationale':compact(m.group(8)), 'caveat':compact(m.group(9)), 'refs':re.findall(r'S\d{3}',m.group(10))})
    if [r['position'] for r in rows] != list(range(1,151)) or any(not r['refs'] for r in rows):
        raise ValueError(f'page-turner entry parse failed: {len(rows)}')
    return rows


def parse_mainstream(text):
    start=text.index('DETAILED RANKING AND EVIDENCE')
    end=text.index('COMPLETE SOURCE REGISTER', start)
    section=text[start:end]
    pattern=re.compile(
        r'(?ms)^(\d{3})\s*\|\s*(.+?)\nAuthor:\s*(.+?)\nFirst publication / textual period:\s*(.+?)\nOriginal language / tradition:\s*(.+?)\nEvidence assessment:\s*(.+?)\nWhy this place:\s*(.+?)\nSources:\s*(.+?)(?=\n\n\d{3}\s*\|\s*|\Z)'
    )
    rows=[]
    for m in pattern.finditer(section):
        language, _, tradition=m.group(5).partition(';')
        rows.append({'position':int(m.group(1)), 'title':m.group(2).strip(), 'attribution':m.group(3).strip(), 'date':m.group(4).strip(), 'language':language.strip(), 'tradition':tradition.strip(), 'form_reported':'book or defined series/collection', 'assessment':m.group(6).strip(), 'rationale':compact(m.group(7)), 'caveat':f"Evidence assessment in the supplied report: {m.group(6).strip()}. This is an editorial synthesis of reception, not a representative global survey or a precise vote total.", 'refs':re.findall(r'S\d{3}',m.group(8))})
    if [r['position'] for r in rows] != list(range(1,151)) or any(not r['refs'] for r in rows):
        raise ValueError(f'mainstream entry parse failed: {len(rows)}')
    return rows


def parse_sources(text, config, target):
    marker='COMPLETE SOURCE BIBLIOGRAPHY' if config['kind']=='page_turners' else 'COMPLETE SOURCE REGISTER'
    section=text[text.index(marker):]
    headers=list(re.finditer(r'(?m)^\[S(\d{3})\]\s+(.+?)\s*$',section))
    seen=set(); records=[]
    for i, h in enumerate(headers):
        chunk=section[h.end():headers[i+1].start() if i+1<len(headers) else len(section)]
        number,title=h.group(1),h.group(2).strip()
        urlm=re.search(r'(?m)^URL:\s*(https?://\S+)',chunk) or re.search(r'(?m)^(https?://\S+)\s*$',chunk)
        if not urlm: raise ValueError(f'S{number}: missing URL')
        url=urlm.group(1).rstrip('.,;)'); canonical=url.rstrip('/')
        if canonical in seen: raise ValueError(f'S{number}: duplicate URL')
        seen.add(canonical)
        typem=re.search(r'(?m)^Type:\s*(.+?)\s*$',chunk)
        accessm=re.search(r'(?m)^Access:\s*(.+?)\s*$',chunk)
        usem=re.search(r'(?m)^(?:Use|Used for ranks):\s*(.+?)\s*$',chunk)
        typ=typem.group(1) if typem else ''
        access=accessm.group(1) if accessm else ''
        use=usem.group(1) if usem else 'Owner-supplied source-register context.'
        eligible=bool(re.search(r'\bretrieved\b|\bfull\b|\bread opening\b',access,re.I))
        sid=f"{config['prefix']}-S{number}"
        records.append({'source_id':sid,'underlying_source_id':'url:'+hashlib.sha256(canonical.encode()).hexdigest()[:24],'title':title,'canonical_url':url,'source_family':family(typ,url),'publisher':urlparse(url).netloc,'access_level':'full_relevant_content' if eligible else 'relevant_excerpt' if 'excerpt' in access.casefold() else 'summary_only','accessed_at':DATE,'count_eligible':eligible,'target_ids':[target],'relevance_by_target':{target:'Owner-supplied synthesis source for reader reception, narrative engagement, cultural transmission, comparative method, or stated limitation.'},'evidence_notes':compact(use),'disagreement_or_limitations':'Access and use are reported by the supplied bibliography. The source may support reception or context rather than an exact editorial position; indexed-only material remains uncounted.','depends_on_source_ids':[],'report_source_number':f'S{number}','report_type':typ,'report_access':access})
    expected={f'S{i:03d}' for i in range(1,config['source_count']+1)}
    actual={r['report_source_number'] for r in records}
    if actual != expected: raise ValueError(f"expected {config['source_count']} sources, got {len(records)}")
    return records


def append_supplementary_sources(sources, target):
    """Keep indexed-only report leads uncounted while supporting three entries.

    Each listed report entry otherwise had no eligible cited page. These are
    narrow, directly read, entry-level sources; they do not alter the supplied
    bibliography's reported access labels or inflate it as a claimed source.
    """
    for position, (sid, title, url, note) in SUPPLEMENTARY_ENTRY_SOURCES.get(target, {}).items():
        sources.append({'source_id':sid,'underlying_source_id':'url:'+hashlib.sha256(url.rstrip('/').encode()).hexdigest()[:24],'title':title,'canonical_url':url,'source_family':'academic_or_institutional' if 'Science Fiction Studies' in title else 'editorial_or_specialist','publisher':urlparse(url).netloc,'access_level':'full_relevant_content','accessed_at':DATE,'count_eligible':True,'target_ids':[target],'relevance_by_target':{target:f'Directly read supplementary entry-level source for rank {position}; supports literary/reception context rather than the exact composite position.'},'evidence_notes':note,'disagreement_or_limitations':'A focused supporting source for one entry; it does not establish the exact composite position. The report’s indexed-only cited leads remain retained and uncounted.','depends_on_source_ids':[],'report_source_number':None,'report_type':'Supplementary directly read source','report_access':'READ'})
    return sources


def existing_authors(title, attribution):
    works=list(Work.objects.filter(title__iexact=title,is_archived=False).prefetch_related('authors'))
    supplied={norm(name) for name in authors(attribution)}
    actual={norm(person.name) for person in works[0].authors.all()} if len(works)==1 else set()
    if supplied and supplied == actual: return [p.name for p in works[0].authors.all()]
    return None


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--target',choices=REPORTS,required=True)
    parser.add_argument('--apply-scope',action='store_true')
    parser.add_argument('--import-unattributed',action='store_true')
    parser.add_argument('--build-selection',action='store_true')
    args=parser.parse_args(); target=args.target; config=REPORTS[target]
    incoming=ROOT/'research'/'incoming'/target/RUN/'report.txt'; incoming.parent.mkdir(parents=True,exist_ok=True)
    if not incoming.exists(): shutil.copy2(config['attachment'],incoming)
    text=incoming.read_text(); rows=(parse_page_turners(text) if config['kind']=='page_turners' else parse_mainstream(text)); sources=append_supplementary_sources(parse_sources(text,config,target),target)
    digest=hashlib.sha256(incoming.read_bytes()).hexdigest(); out=ROOT/'research'/target; out.mkdir(parents=True,exist_ok=True)
    ranking=Ranking.objects.get(slug=target,origin='curated',owner__isnull=True,is_archived=False)
    if args.apply_scope:
        if ranking.entries.filter(is_archived=False).exists(): raise ValueError('Target is already published; scope update requires reconciliation.')
        ranking.scope=config['scope']; ranking.description=config['description']; ranking.full_clean(); ranking.save(update_fields=['scope','description','updated_at'])
    byref={r['report_source_number']:r for r in sources}
    named=[]; unresolved=[]
    for row in rows:
        names=existing_authors(row['title'], row['attribution']) or authors(row['attribution'])
        record={'key':f"{target}-owner-{row['position']:03d}",'title':row['title'],'authors':names,'form':form_for(row['title'],row['form_reported']),'field':'literature','original_year':year(row['date']),'original_language':row['language'],'countries':[row['tradition']] if row['tradition'] else [],'description':f"Position {row['position']} in {config['title']}, owner-supplied 14 September 2026 synthesis. Attribution: {row['attribution']}. First publication/textual period: {row['date']}. {row['rationale']}",'work_source_url':byref[row['refs'][0]]['canonical_url'],'evidence_ids':[byref[x]['source_id'] for x in row['refs']],'edition':None,'english_availability_note':'Specific edition, translation and media remain to be verified.'}
        (named if names else unresolved).append(record)
    (out/'sources.owner-chat-2026-09-14.json').write_text(json.dumps({'target_id':target,'ranking_entries':[],'sources':sources},ensure_ascii=False,indent=2)+'\n')
    (out/'owner-chat-candidates-2026-09-14.json').write_text(json.dumps({'target_id':target,'source_report':str(incoming.relative_to(ROOT)),'candidates':rows},ensure_ascii=False,indent=2)+'\n')
    (out/'owner-chat-catalog-2026-09-14.json').write_text(json.dumps({'schema_version':1,'allow_pending_editions':True,'works':named},ensure_ascii=False,indent=2)+'\n')
    (out/'owner-chat-unresolved-2026-09-14.json').write_text(json.dumps(unresolved,ensure_ascii=False,indent=2)+'\n')
    (incoming.parent/'RECEIPT.md').write_text(f'# Owner attachment receipt\n\n- Received: {DATE}\n- Requested action: populate the existing ranking template with positions and sources.\n- SHA-256: `{digest}`\n- Parsed: 150 ranking entries and {len(sources)} source records.\n')
    if args.import_unattributed:
        result=[]
        with transaction.atomic():
            for record in unresolved:
                matches=list(Work.objects.filter(title__iexact=record['title'],authors__isnull=True,is_archived=False))
                if len(matches)>1: raise ValueError(f"Ambiguous authorless work: {record['title']}")
                work=matches[0] if matches else Work(title=record['title'],form=record['form'],field=record['field'],original_year=record['original_year'],original_language=record['original_language'],countries=record['countries'],description=record['description'])
                created=not matches
                if created: work.full_clean(); work.save()
                result.append({'key':record['key'],'work_id':work.pk,'created_work':created})
        (out/'owner-chat-unresolved-2026-09-14-import-receipt.json').write_text(json.dumps({'records':result},ensure_ascii=False,indent=2)+'\n')
    if args.build_selection:
        receipts=sorted(out.glob('owner-chat-catalog-2026-09-14*-import-receipt.json'), key=lambda p: (p.name != 'owner-chat-catalog-2026-09-14-import-receipt.json', p.name))
        if not receipts: raise FileNotFoundError('Catalog import receipt not found.')
        ids={}
        for receipt in receipts:
            ids.update({r['key']:r['work_id'] for r in json.loads(receipt.read_text())['records']})
        unresolved_receipt=out/'owner-chat-unresolved-2026-09-14-import-receipt.json'
        if unresolved_receipt.exists(): ids.update({r['key']:r['work_id'] for r in json.loads(unresolved_receipt.read_text())['records']})
        keys=[]; entries=[]
        for row in rows:
            key=f"{target}-owner-{row['position']:03d}"; source_ids=[byref[x]['source_id'] for x in row['refs'] if byref[x]['count_eligible']]
            if not source_ids and row['position'] in SUPPLEMENTARY_ENTRY_SOURCES.get(target, {}): source_ids=[SUPPLEMENTARY_ENTRY_SOURCES[target][row['position']][0]]
            if not source_ids: raise ValueError(f'No eligible source cited by rank {row["position"]}: {row["title"]}')
            work_id=SELECTION_WORK_OVERRIDES.get(target, {}).get(row['position'], ids[key])
            entries.append({'key':key,'item_id':work_id,'source_ids':source_ids,'standing':f"Position {row['position']} in the owner-supplied 14 September 2026 {config['title']} synthesis. {row['rationale']}",'reading':f"The supplied order reflects {('compulsive readability' if config['kind']=='page_turners' else 'enduring mainstream reader affection')}. {row['rationale']}",'caveat':row['caveat']+f" Supplied source references retained for this entry: {', '.join(row['refs'])}.",'metadata_status':'edition_and_media_pending','source_positions':[]}); keys.append(key)
        selected={entry['item_id'] for entry in entries}
        exclusions=[{'item_id':entry.work_id,'reason':'Superseded in this correction by the established catalog identity for the same owner-supplied work; the earlier revision remains preserved.'} for entry in ranking.entries.filter(is_archived=False).exclude(work_id__in=selected)]
        selection={'target':target,'expected_revision':ranking.revision,'allow_expansion':True,'version':f'owner-chat-{config["kind"]}-top-150-2026-09-14','published_on':DATE,'allow_pending_metadata':True,'reviewed_exclusions':exclusions,'notice':f"Owner-supplied {config['title']} Top 150. Source access and limits are retained; no personal numerical scores are set.",'method':f"Owner-supplied editorial synthesis of {len(sources)} target-local linked sources. The supplied order is retained in both views pending a separately reasoned alternative order.",'entries':entries,'orders':{'standing':{'label':('Compulsive readability' if config['kind']=='page_turners' else 'Enduring mainstream reader affection'),'description':'The supplied editorial Top 150 order.','keys':keys},'reading':{'label':'Supplied order (alternative view pending)','description':'No separately reasoned alternative order was supplied.','keys':keys}}}
        (out/'owner-chat-selection-2026-09-14.json').write_text(json.dumps(selection,ensure_ascii=False,indent=2)+'\n')
    print(f"{target}: parsed 150 entries, {len(sources)} sources ({sum(x['count_eligible'] for x in sources)} eligible), {len(named)} named and {len(unresolved)} authorless catalog records; SHA-256 {digest}")


if __name__ == '__main__':
    main()
