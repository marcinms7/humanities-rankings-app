"""Ingest the owner's additional poetry DOCX using the reviewed additive intake."""
import argparse, importlib.util, json, re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
RUN=Path(__file__).resolve().parent
RUN_ID='2026-09-27-owner-docx-poetry'
ORIGINAL=ROOT/'research/incoming/poetry-all-time'/RUN_ID/'Poetry_All_Time_Updated_Ranking.json'
PREVIOUS=ROOT/'research/_runs/2026-09-27/owner-docx-updates'

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def normalized():
    p=module('word_parser',PREVIOUS/'prepare.py')
    doc=json.loads(ORIGINAL.read_text());bs=doc['blocks'];sources=p.extract_sources(doc,'poetry',(2813,3473));source_ids={s['incoming_id'] for s in sources}
    assert len(source_ids)==326 and sum(s['reported_qualifying'] for s in sources)==110
    starts=[i for i in range(41,1585) if bs[i]['kind']=='p' and re.match(r'^\d+\s+\S',bs[i]['text']) and i+1<len(bs) and re.search(r'(work:|new:)',bs[i+1].get('text',''))]
    entries=[]
    for n,i in enumerate(starts):
        end=starts[n+1] if n+1<len(starts) else 1585
        lines=p.paragraphs(bs,i,end);head=re.match(r'^(\d+)\s+(.+)',lines[0]);parts=[x.strip() for x in lines[1].split('|')]
        authors,key,form,positions=parts
        match=re.search(r'S (\d+)\s+R (\d+)',positions);assert int(head[1])==int(match[1])
        entries.append({'key':key,'item_id':int(key.split(':')[1]) if key.startswith('work:') else None,'title':head[2], 'authors':authors,
                        'standing':int(match[1]),'reading':int(match[2]),'reported_form_code':form.removeprefix('Form '),
                        'rationale':next(l.removeprefix('Standing ') for l in lines if l.startswith('Standing ')),
                        'reading_rationale':next(l.removeprefix('Reading ') for l in lines if l.startswith('Reading ')),
                        'source_ids':p.refs(lines,source_ids),'raw_record':'\n'.join(lines)})
    assert len(entries)==186 and len({e['key'] for e in entries})==186
    for lens in ('standing','reading'):assert sorted(e[lens] for e in entries)==list(range(1,187))
    for row in bs[1587]['rows'][1:]:
        cells=[c['text'] for c in row];candidate=next(e for e in entries if e['key']==cells[3]);assert candidate['standing']==int(cells[1]) and candidate['reading']==int(cells[0])
    current={r[0] for r in p.DB.execute("select source_id from core_researchsource s join core_ranking r on r.id=s.ranking_id where r.slug='poetry-all-time'")}
    assert not current-source_ids,('missing historical sources',current-source_ids)
    report={'kind':'poetry','target':'poetry-all-time','filename':doc['filename'],'sha256':doc['sha256'],'entries':entries,'sources':sources,'existing_source_ids_absent_from_report':[]}
    (RUN/'normalized-poetry.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    report=json.loads((RUN/'normalized-poetry.json').read_text()) if args.apply else normalized()
    m=module('reviewed_intake',PREVIOUS/'apply_updates.py');m.RUN=RUN;m.RUN_ID=RUN_ID;m.REPORTS=[report];m.SELECTED=[report]
    m.CATALOG_ALIASES['new:shijing']=6398
    old_create=m.create_catalog
    def poetry_catalog(e,kind,ranking):
        obj=old_create(e,kind,ranking)
        # A new candidate's precise work unit is stated in the incoming report.
        # Existing catalog records are kept unchanged by this intake.
        form='poem' if e['reported_form_code'] in ('I','L') else 'collection' if e['reported_form_code'] in ('C','S','A') else 'book'
        if obj.form!=form:
            obj.form=form;obj.full_clean();obj.save(update_fields=['form','updated_at'])
        return obj
    m.create_catalog=poetry_catalog
    if args.apply:
        plans=json.loads((RUN/'import-plan.json').read_text());m.apply(plans)
    else:
        plans=m.prepare()
        for e in plans[0]['entries']:
            if e['resolved_item_id'] is None:print('NEW CATALOG',e['key'],e['title'],'—',e['authors'])

if __name__=='__main__':main()
