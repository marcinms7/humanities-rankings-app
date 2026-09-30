"""Normalize supplied Word extractions; no network access or database writes."""
import json, re, sqlite3, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
RUN = Path(__file__).resolve().parent
MANIFEST = json.loads((RUN / 'delivery-manifest.json').read_text())
DB = sqlite3.connect((ROOT/'data/db.sqlite3').as_uri()+'?mode=ro', uri=True)
DB.row_factory = sqlite3.Row
DB.execute('PRAGMA query_only=ON')
SPEC = {
 'Philosophers_All_Time_Expanded_Ranking.docx': ('expanded', (24,780), (1739,2635), 189),
 'ancient_works_all_time_ranking_update.docx': ('ancient', (12,163), (352,576), 150),
 'Top_Three_Books_by_Country_Research_Update.docx': ('country', (30,2973), (3324,4884), 624),
 'Philosophy_Books_Revised_Rankings_and_Sources.docx': ('philosophy', (33,1710), (2197,4521), 250),
 'literary-fiction-ranking.docx': ('literature', (46,1047), (2404,4685), 250),
 'Philosophers_All_Time_Research_Update_2026-09-27.docx': ('philosophers', (63,2325), (3133,5415), 297),
 'History_books_updated.docx': ('history', (46,2175), (4638,7161), 266),
 'Comics_and_graphic_narratives_revised.docx': ('comics', (50,3092), (9067,11676), 250),
}
SOURCE_ID = re.compile(r'^([A-Z][A-Z0-9_-]*\d[A-Z0-9_-]*)\s+(?:[|·]\s*)?(.+)')

def clean(text):
    return text.replace('\u200b','').replace('\ufeff','').replace('\u00ad','').strip()

def norm(text):
    text = ''.join(x for x in unicodedata.normalize('NFKD', text).casefold() if not unicodedata.combining(x))
    return re.sub(r'[^a-z0-9]+','',text)

def paragraphs(blocks,a,b):
    return [clean(x['text']) for x in blocks[a:b] if x['kind']=='p' and clean(x['text'])]

def urls(block):
    if block['kind']!='p': return []
    return list(dict.fromkeys([clean(l['url']) for l in block.get('links',[]) if l['url'].startswith(('http://','https://'))]+re.findall(r'https?://\S+',clean(block['text']))))

def extract_sources(doc,kind,qual_range):
    blocks=doc['blocks']; starts=[]
    for i,b in enumerate(blocks):
        if b['kind']!='p': continue
        match=SOURCE_ID.match(clean(b['text']))
        if match and not match.group(2).startswith('through ') and any(urls(x) for x in blocks[i+1:i+4]):
            starts.append((i,match.group(1),match.group(2)))
    records=[]
    for n,(i,sid,title) in enumerate(starts):
        end=starts[n+1][0] if n+1<len(starts) else len(blocks)
        for j in range(i+1,end):
            if blocks[j]['kind']=='p' and blocks[j].get('style') in ('Heading1','Heading2'):
                end=j;break
        lines=paragraphs(blocks,i,end); urllist=[u for b in blocks[i+1:min(end,i+4)] for u in urls(b)]
        if not urllist: continue
        url=urllist[0]; raw='\n'.join(lines); qualifying=qual_range[0]<=i<qual_range[1]
        if kind=='ancient':
            qualifying='counted=yes' in lines[0];bits=title.split(' | ')
            if bits[0].startswith('counted='):title=bits[1]
        if kind=='country': qualifying=qualifying and 'Counted new: YES' in raw
        if kind=='history': qualifying=qualifying and any(x.startswith('COUNTED |') for x in lines)
        evidence=[]
        for line in lines[1:]:
            if line.startswith(('Evidence:', 'Evidence ', 'Saved evidence:', 'This run ')):
                evidence.append(line)
            elif len(line)>120 and not line.startswith(('http','Supported','Consulted','Limits','Family:','Publisher:','Author ','Current disposition','Access and limits','Candidate mapping','Underlying','Current date','Current review','Counted','Saved limitations','Access:')):
                evidence.append(line)
        if kind=='ancient': evidence=[lines[0].split(' | candidates ',1)[-1]]
        if not evidence: evidence=[line for line in lines[1:] if not line.startswith('http')]
        supported=[]
        for line in lines:
            if re.search(r'(?i)\b(supports|supported|candidates|candidate mapping)',line):supported.append(line)
        records.append(dict(incoming_id=sid,title=title.strip(),url=url,reported_qualifying=qualifying,
                            evidence='\n'.join(evidence),supported_notes=supported,raw_record=raw,
                            original_file=doc['filename'],block=i))
    return records

def refs(lines,source_ids):
    text='\n'.join(lines)
    return sorted({sid for sid in source_ids if re.search(r'(?<![A-Za-z0-9_-])'+re.escape(sid)+r'(?![A-Za-z0-9_-])',text)})

def parse_rank(doc,kind,span,source_ids):
    bs=doc['blocks'];a,b=span; records=[]
    if kind=='country':
        starts=[i for i in range(a,b) if bs[i]['kind']=='p' and bs[i].get('style')=='Heading2' and re.match(r'^\d+ ',bs[i]['text'])]
        for n,i in enumerate(starts):
            end=starts[n+1] if n+1<len(starts) else b
            section,country=bs[i]['text'].split(' ',1)
            table=next(x for x in bs[i:end] if x['kind']=='table')
            lines=paragraphs(bs,i,end)
            for row in table['rows'][1:]:
                cells=[clean(c['text']) for c in row];key=cells[3];wid=int(key.split(':')[1])
                evidence_lines=[l for l in lines if l.startswith(key+' ')]
                records.append(dict(key=key,item_id=wid,title=cells[2],standing=int(cells[0]),reading=int(cells[1]),country=country,section_index=int(section),rationale='\n'.join(evidence_lines),source_ids=refs(evidence_lines,source_ids),raw_record='\n'.join(lines),group_summary=lines[1]))
        return records
    if kind=='ancient':
        ranking_id=DB.execute("select id from core_ranking where slug='books-ancient'").fetchone()[0]
        works=[dict(x) for x in DB.execute("select w.id,w.title,group_concat(p.name,'; ') authors from core_work w join core_rankingentry e on e.work_id=w.id left join core_work_authors wa on wa.work_id=w.id left join core_person p on p.id=wa.person_id where e.ranking_id=? and e.is_archived=0 group by w.id",(ranking_id,))]
        by_title={}
        for work in works:by_title.setdefault(norm(work['title']),[]).append(work)
        additions={}
        for line in paragraphs(bs,317,337):
            key,body=line.split(' | ',1);heading=body.split(' | ',1)[0];additions[norm(heading.split(' — ',1)[0])]=(key,body)
        reading={}
        for line in paragraphs(bs,165,315):
            m=re.match(r'^(\d+)\. (.+?) — (.+?) \|',line)
            if m:reading[(norm(m[2]),norm(m[3]))]=int(m[1])
        for line in paragraphs(bs,a,b):
            m=re.match(r'^(\d+)\. (.+?) — (.+?) \| (.*)',line)
            if not m: continue
            rank,title,author,body=m.groups();matches=by_title.get(norm(title),[])
            if len(matches)>1:matches=[w for w in matches if norm(author)==norm(w['authors'] or '')]
            assert len(matches)<2,('ambiguous ancient identity',title,author)
            iid=matches[0]['id'] if matches else None;addition=additions.get(norm(title));key=f'work:{iid}' if iid else addition[0] if addition else None
            assert key, ('unmatched ancient title',title)
            # The report has cross-wired annotations (e.g. Analects gets Horace's dates).
            # Keep its order, but do not import those bibliographic/rationale fragments.
            standing_note='Updated editorial position in the supplied ancient-works comparison. Candidate-level argument remains provisional; the report contains misaligned annotations, so existing catalog metadata is preserved.'
            reading_note='Supplied reading-value position; consult a suitable English edition. Misaligned report annotations were not treated as verified work metadata.'
            if addition:
                seg=addition[1].split('|');standing_note=seg[2].strip() if len(seg)>2 else standing_note;reading_note=seg[3].split('Evidence:')[0].strip() if len(seg)>3 else reading_note
            records.append(dict(key=key,item_id=iid,title=title,authors=author,standing=int(rank),reading=reading[(norm(title),norm(author))],rationale=standing_note,reading_rationale=reading_note,source_ids=refs([line],source_ids),raw_record=line,reported_addition=addition[1] if addition else None))
        return records
    starts=[]
    for i in range(a,b):
        if bs[i]['kind']!='p':continue
        line=clean(bs[i]['text'])
        if re.match(r'^\d+[. ]\s*\S',line) and not line.startswith('250 '):
            # Source headings and prose cannot satisfy the following identity line.
            following='\n'.join(paragraphs(bs,i+1,min(i+4,b)))
            if re.search(r'(?:work:|person:|proposed:|proposal:|new:|ID \d+)',following):starts.append(i)
    # Position 250 is a valid candidate too; the identity line disambiguates it.
    for i in range(a,b):
        if bs[i]['kind']=='p' and re.match(r'^250[. ]\s*\S',clean(bs[i]['text'])):
            if re.search(r'(?:work:|person:|proposed:|proposal:|new:|ID \d+)', '\n'.join(paragraphs(bs,i+1,min(i+4,b)))):starts.append(i)
    starts=sorted(set(starts))
    for n,i in enumerate(starts):
        end=starts[n+1] if n+1<len(starts) else b;lines=paragraphs(bs,i,end);head=re.match(r'^(\d+)[. ]\s*(.+)',lines[0]);rank=int(head[1]);title=head[2];raw='\n'.join(lines)
        if kind=='expanded':title=title.split('   |')[0]
        km=re.search(r'\b((?:work|person|proposed|proposal|new):[A-Za-z0-9:_-]+)', '\n'.join(lines[1:4]))
        if not km and kind=='philosophy':km=re.search(r'\bID (\d+)',lines[1])
        assert km, (kind,rank,lines[:3]);key=km[1]
        if key.isdigit():key='work:'+key
        iid=int(key.split(':')[1]) if re.match(r'^(work|person):\d+$',key) else None
        rm=re.search(r'\bReading(?: position| rank)?\s+(\d+)',raw)
        assert rm, (kind,rank,'no reading')
        author=None
        if kind in ('philosophy','literature','history'):
            title,author=title.rsplit(' — ',1)
        elif kind=='comics':author=next(l.removeprefix('Creators ') for l in lines if l.startswith('Creators '))
        if kind=='history':
            rationale=next(l.removeprefix('Standing: ') for l in lines if l.startswith('Standing: '));reading=next(l.removeprefix('Reading today: ') for l in lines if l.startswith('Reading today: '))
        elif kind=='comics':
            rationale=next(l.removeprefix('Assessment ') for l in lines if l.startswith('Assessment '));reading=next((l.removeprefix('Reading today ') for l in lines if l.startswith('Reading today ')),rationale)
        elif kind=='expanded':
            both=next(l for l in lines if l.startswith('Standing:'));rationale=both.split('Reading:')[0].removeprefix('Standing:').strip();reading=both.split('Reading:',1)[-1].strip()
        elif kind=='philosophers':
            rationale=lines[2];reading=' '.join(l for l in lines if l.startswith(('Reading value','Reading route')))
        elif kind=='literature':rationale=lines[2];reading=rationale
        else:
            rationale=next(l for l in lines[2:] if not l.startswith(('Previously','Proposed addition.','Evidence','English','Standing positions')));reading=rationale
        records.append(dict(key=key,item_id=iid,title=title,authors=author,standing=rank,reading=int(rm[1]),rationale=rationale,reading_rationale=reading,source_ids=refs(lines,source_ids),raw_record=raw))
    if kind=='philosophy':
        by_standing={r['standing']:r for r in records}
        for row in bs[1712]['rows'][1:]:
            cells=[c['text'] for c in row]
            candidate=by_standing[int(cells[2])]
            assert candidate['reading']==int(cells[0])
            candidate['reading_rationale']=cells[3]
    return records

def main():
    reports=[]
    for delivery in MANIFEST:
        path=ROOT/delivery['directory']/(Path(delivery['filename']).stem+'.json');doc=json.loads(path.read_text());kind,span,qual_range,expected=SPEC[delivery['filename']]
        sources=extract_sources(doc,kind,qual_range);ids={s['incoming_id'] for s in sources}
        entries=parse_rank(doc,kind,span,ids)
        assert len(entries)==expected,(kind,len(entries),expected)
        if kind!='country':
            assert sorted(e['standing'] for e in entries)==list(range(1,expected+1)),(kind,'standing permutation')
            assert sorted(e['reading'] for e in entries)==list(range(1,expected+1)),(kind,'reading permutation')
            assert len({e['key'] for e in entries})==expected,(kind,'duplicate candidate keys')
        rank_id=DB.execute('select id from core_ranking where slug=?',(delivery['target'],)).fetchone()[0]
        existing={r['source_id'] for r in DB.execute('select source_id from core_researchsource where ranking_id=?',(rank_id,))}
        missing=sorted(existing-ids)
        report=dict(kind=kind,target=delivery['target'],filename=delivery['filename'],sha256=delivery['sha256'],entries=entries,sources=sources,existing_source_ids_absent_from_report=missing)
        (RUN/f'normalized-{kind}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        reports.append(report)
        print(kind,'entries',len(entries),'source_records',len(sources),'unique_source_ids',len(ids),'reported_new_qualifying',sum(s['reported_qualifying'] for s in sources),'old_sources_absent',len(missing))
    (RUN/'normalized-reports.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
