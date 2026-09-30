"""Reviewed, additive file intake. Default mode only prepares the import plan."""
from __future__ import annotations
import argparse, copy, hashlib, io, json, os, re, sys, unicodedata
from collections import defaultdict, Counter
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, unquote

ROOT=Path(__file__).resolve().parents[4]
RUN=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.config.settings')
import django
django.setup()
from django.conf import settings
from django.core.management import call_command
from django.db import connection, transaction
from backend.core.models import Ranking, RankingEntry, ResearchSource, Work, Person
from backend.core.views import ensure_revision, save_revision

RUN_ID='2026-09-27-owner-docx-updates'
REPORTS=json.loads((RUN/'normalized-reports.json').read_text())
SELECTED=[r for r in REPORTS if r['kind']!='expanded']
# Explicitly reviewed title/translation aliases in the existing catalog.
CATALOG_ALIASES={
 'proposed:shijing':6398,'proposed:yijing':6402,
 'proposed:critique-judgment':1769,'proposed:metaphysics-healing':8662,
 'proposed:mozi':901,'proposed:shobogenzo':817,'proposed:naming-necessity':3692,'proposed:word-object':4590,
 'new:blood-meridian':714,'new:golden-ass':6356,'new:tom-jones':4632,
 'new:the-street-of-crocodiles':972,'new:beggar-maid':3575,'new:invention-of-morel':1374,'new:burning-plain':3574,
}

def dump(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=str)+'\n')
def norm(t):return re.sub(r'[^a-z0-9]+','', ''.join(c for c in unicodedata.normalize('NFKD',t).casefold() if not unicodedata.combining(c)))
def urlkey(u):
    p=urlsplit(u.strip());return urlunsplit(('',p.netloc.lower().removeprefix('www.'),unquote(p.path).rstrip('/'),p.query,''))
def titlekey(t):return norm(re.sub(r'^(the|a|an)\s+','',t,flags=re.I))
def personkeys(name):
    return {norm(name),norm(re.sub(r'\s*\([^)]*\)','',name)),norm(name.split(' — ')[0]),norm(re.sub(r'^(Saint|St\.)\s+','',name,flags=re.I))}-{''}

def load_catalog():
    people=list(Person.objects.filter(is_archived=False));works=list(Work.objects.filter(is_archived=False).prefetch_related('authors'))
    pindex=defaultdict(list);windex=defaultdict(list)
    for p in people:
        for k in personkeys(p.name):pindex[k].append(p)
    for w in works:
        for k in {titlekey(w.title),titlekey(w.title.split(':')[0])}:windex[k].append(w)
    return pindex,windex

PINDEX,WINDEX=load_catalog()

def find_person(name):
    exact=list({p.pk:p for p in PINDEX.get(norm(name),[])}.values())
    if exact:return sorted(exact,key=lambda p:(not bool(p.portrait),p.pk))[0]
    candidates={p.pk:p for k in personkeys(name) for p in PINDEX.get(k,[])}
    return sorted(candidates.values(),key=lambda p:(not bool(p.portrait),p.pk))[0] if candidates and len({norm(re.sub(r'\s*\([^)]*\)','',p.name)) for p in candidates.values()})==1 else None

def find_work(title,authors):
    candidates={w.pk:w for key in {titlekey(title),titlekey(title.split(':')[0])} for w in WINDEX.get(key,[])}
    an=norm(authors or '')
    matched=[]
    for w in candidates.values():
        names=[norm(a.name) for a in w.authors.all()]
        if any(n and an and (n in an or an in n) for n in names):matched.append(w)
    exact=[w for w in matched if titlekey(w.title)==titlekey(title)]
    if exact:return sorted(exact,key=lambda w:(w.default_edition_id is None,w.pk))[0]
    if matched and len({titlekey(w.title) for w in matched})==1:return sorted(matched,key=lambda w:(w.default_edition_id is None,w.pk))[0]
    exact_unattributed=[w for w in candidates.values() if titlekey(w.title)==titlekey(title) and not w.authors.exists()]
    if len(exact_unattributed)==1 and re.search(r'(?i)anonymous|collective|tradition',authors or ''):return exact_unattributed[0]
    return None

def source_family(s):
    text=(s['raw_record']+' '+s['url']).lower()
    if any(x in text for x in ['reddit.com','goodreads.com','reader discussion','reader_forum']):return 'reader_community'
    if any(x in text for x in ['plato.stanford','iep.utm','scholarly_reference']):return 'scholarly_reference'
    if any(x in text for x in ['scholarly','academic','journal','university']):return 'academic_or_specialist'
    if any(x in text for x in ['wikipedia.org','catalogue','metadata_only']):return 'bibliographic_or_reference'
    return 'critical_or_editorial'

def plan_sources(ranking,reports):
    existing=list(ranking.sources.all());byid={s.source_id:s for s in existing};byurl={}
    for s in existing:byurl.setdefault(urlkey(s.url),s.source_id)
    maps={};new={};updates=defaultdict(list);problems=[]
    for report in reports:
        smap={}
        for s in report['sources']:
            sid=s['incoming_id'];url=s['url'];p=urlsplit(url)
            if p.scheme not in ('http','https') or not p.netloc or len(url)>1000:
                problems.append({'source_id':sid,'file':report['filename'],'reason':'invalid or overlength source URL','url':url});continue
            uk=urlkey(url)
            known=byid.get(sid)
            canonical=sid if known and urlkey(known.url)==uk else byurl.get(uk)
            if canonical is None:
                canonical=sid
                if canonical in byid or (canonical in new and urlkey(new[canonical]['canonical_url'])!=uk):canonical=sid+'-DOCX27'
                assert len(canonical)<=80
                new[canonical]={
                    'source_id':canonical,'underlying_source_id':'url:'+hashlib.sha256(uk.encode()).hexdigest()[:40],
                    'title':s['title'][:500],'canonical_url':url,'access_url':url,
                    'source_family':source_family(s),'publisher':p.netloc.removeprefix('www.')[:240],
                    'target_ids':[ranking.slug],'relevance_by_target':{ranking.slug:'Supplied external-agent report for this target; candidate/claim mappings and full source note are retained.'},
                    'accessed_at':'2026-09-27' if s['reported_qualifying'] else None,
                    'access_level':'relevant_excerpt' if s['reported_qualifying'] else 'discovery_lead',
                    'count_eligible':bool(s['reported_qualifying']),
                    'evidence_notes':'Externally reported consultation: '+s['evidence'] if s['reported_qualifying'] else 'Retained noncounting supplied record: '+s['evidence'],
                    'disagreement_or_limitations':'Supplied external-agent evidence; no independent source-by-source web verification during this file intake. See incoming_report_records for the exact reported access, independence and evidence limitations.',
                    'depends_on_source_ids':[],'incoming_report_records':[],
                    'candidates_or_claims_supported':s['supported_notes'],
                    'owner_supplied':True,'locally_verified':False,'intake_run':RUN_ID,
                }
                byurl[uk]=canonical
            previous=smap.get(sid)
            if previous and previous!=canonical:problems.append({'source_id':sid,'file':report['filename'],'reason':'one incoming ID has differing URLs','mapped_ids':[previous,canonical]})
            smap[sid]=previous or canonical
            annotation={'filename':report['filename'],'sha256':report['sha256'],'incoming_source_id':sid,'reported_qualifying_addition':s['reported_qualifying'],'reported_source_record':s['raw_record'],'original_block':s['block']}
            if canonical in new:
                new[canonical]['incoming_report_records'].append(annotation)
                if s['reported_qualifying'] and not new[canonical]['count_eligible']:
                    new[canonical].update(count_eligible=True,accessed_at='2026-09-27',access_level='relevant_excerpt',evidence_notes='Externally reported consultation: '+s['evidence'])
            else:updates[canonical].append(annotation)
        maps[report['filename']]=smap
    return {'new_sources':list(new.values()),'existing_annotations':dict(updates),'source_id_maps':maps,'source_conflicts':problems}

def excluded_records(report,old_ids,active_ids):
    omitted=old_ids-active_ids
    # Keep the source document's decision paragraphs with each superseded row.
    doc=json.loads((ROOT/'research/incoming'/report['target']/RUN_ID/(Path(report['filename']).stem+'.json')).read_text())
    lines=[b['text'] for b in doc['blocks'] if b['kind']=='p']
    output=[]
    for iid in sorted(omitted):
        fragments=[]
        for i,line in enumerate(lines):
            if re.search(r'\bwork:'+str(iid)+r'\b',line) or re.match(r'^ID '+str(iid)+r'\s',line):fragments.append('\n'.join(lines[i:i+4]))
        output.append({'item_id':iid,'reason':'Displaced from the active comparison by the supplied revised ranking; preserved in the catalog, archived ranking entry and previous revisions.','report_decisions':fragments})
    return output

def prepare():
    assert settings.DATABASES['default']['ENGINE']=='django.db.backends.sqlite3'
    assert Path(settings.DATABASES['default']['NAME']).resolve()==ROOT/'data/db.sqlite3'
    plans=[]
    for report in SELECTED:
        rank=Ranking.objects.get(slug=report['target'],origin='curated',owner__isnull=True,is_archived=False)
        related=[report]+([r for r in REPORTS if r['kind']=='expanded'] if report['kind']=='philosophers' else [])
        plan=plan_sources(rank,related);entries=copy.deepcopy(report['entries']);seen={};conflicts=[]
        for e in entries:
            if e['item_id'] is not None:
                model=Person if rank.item_type=='person' else Work
                obj=model.objects.get(pk=e['item_id'],is_archived=False)
            elif e['key'] in CATALOG_ALIASES:obj=Work.objects.get(pk=CATALOG_ALIASES[e['key']],is_archived=False)
            elif rank.item_type=='person':obj=find_person(e['title'])
            else:obj=find_work(e['title'],e.get('authors'))
            e['resolved_item_id']=obj.pk if obj else None
            if obj:
                e['catalog_title']=obj.name if rank.item_type=='person' else obj.title
                if obj.pk in seen and report['kind']!='country':conflicts.append({'item_id':obj.pk,'keys':[seen[obj.pk],e['key']],'titles':[x['title'] for x in entries if x['key'] in (seen[obj.pk],e['key'])]})
                seen[obj.pk]=e['key']
            smap=plan['source_id_maps'][report['filename']]
            e['canonical_source_ids']=list(dict.fromkeys(smap[x] for x in e['source_ids'] if x in smap))
            # Recover explicit source-to-candidate mappings for the ancient report,
            # whose new-candidate rows incorrectly say "gap flagged" throughout.
            if report['kind']=='ancient':
                for s in report['sources']:
                    if any(re.search(r'(?<![A-Za-z0-9:_-])'+re.escape(e['key'])+r'(?![A-Za-z0-9:_-])',t) for t in s['supported_notes']):
                        if s['incoming_id'] in smap and smap[s['incoming_id']] not in e['canonical_source_ids']:e['canonical_source_ids'].append(smap[s['incoming_id']])
        plan.update(target=rank.slug,kind=report['kind'],expected_revision=rank.revision,primary_file=report['filename'],report_hashes=[r['sha256'] for r in related],entries=entries,identity_conflicts=conflicts,
                    before={'entries':rank.entries.filter(is_archived=False).count(),'sources':rank.sources.count(),'eligible':rank.sources.filter(is_archived=False,eligible=True).count()},
                    existing_sources_absent_from_report=report['existing_source_ids_absent_from_report'])
        plans.append(plan)
        print(rank.slug,'entries',len(entries),'new_catalog',len({e['key'] for e in entries if e['resolved_item_id'] is None}),'new_sources',len(plan['new_sources']),'source_conflicts',len(plan['source_conflicts']),'identity_conflicts',len(conflicts))
    dump(RUN/'import-plan.json',plans)
    dump(RUN/'identity-review.json',[{'target':p['target'],'new_catalog':[{'key':e['key'],'title':e['title'],'authors':e.get('authors')} for e in p['entries'] if e['resolved_item_id'] is None],'conflicts':p['identity_conflicts']} for p in plans])
    return plans

def private_signature():
    result={}
    with connection.cursor() as c:
        tables=connection.introspection.table_names(c)
        for table in tables:
            columns=[x.name for x in connection.introspection.get_table_description(c,table)]
            if 'user_id' in columns or table in ('auth_user','auth_user_groups','auth_user_user_permissions','django_session'):
                c.execute('SELECT * FROM '+connection.ops.quote_name(table)+' ORDER BY 1');rows=c.fetchall()
                result[table]={'rows':len(rows),'sha256':hashlib.sha256(json.dumps(rows,default=str).encode()).hexdigest()}
    return result

def create_catalog(e,kind,ranking):
    if ranking.item_type=='person':
        p=find_person(e['title'])
        if p:return p
        p=Person(name=e['title'].split(' — ')[0],biography='');p.full_clean();p.save()
        for k in personkeys(p.name):PINDEX[k].append(p)
        return p
    w=find_work(e['title'],e.get('authors'))
    if w:return w
    authors=e.get('authors') or '';form='book'
    if kind=='ancient':
        description=e.get('reported_addition') or ''
        if any(x in description.lower() for x in ['anthology','corpus','collection','collected']):form='collection'
        elif 'poem' in description.lower():form='poem'
    # Preserve the app's declared scope. Specific work-unit labels stay in the report.
    if form not in ranking.scope.get('forms',[form]):form='book'
    field='philosophy' if kind=='philosophy' else 'nonfiction' if kind=='history' else 'literature'
    w=Work(title=e['title'],form=form,field=field,description='',reading_load='philosophy' if field=='philosophy' else 'classic_literature');w.full_clean();w.save()
    if authors and not re.search(r'(?i)anonymous|collective|tradition|composite|disputed|attribution',authors):
        for name in [a.strip() for a in authors.split(';') if a.strip()]:
            name=re.sub(r'\s*\(editor\).*$','',name).strip()
            p=find_person(name)
            if p is None:
                p=Person(name=name);p.full_clean();p.save()
                for k in personkeys(name):PINDEX[k].append(p)
            w.authors.add(p)
    for k in {titlekey(w.title),titlekey(w.title.split(':')[0])}:WINDEX[k].append(w)
    return w

def canonical_ledger(rank):
    sources=[]
    for s in rank.sources.all().order_by('id'):
        m=copy.deepcopy(s.metadata) if isinstance(s.metadata,dict) else {}
        m.update(source_id=s.source_id,underlying_source_id=s.underlying_source_id,title=s.title,canonical_url=s.url,source_family=s.family,publisher=s.publisher,
                 evidence_notes=s.evidence,disagreement_or_limitations=s.limitations,accessed_at=s.consulted_on.isoformat() if s.consulted_on else None,count_eligible=s.eligible,
                 target_ids=[rank.slug],relevance_by_target={rank.slug:m.get('relevance_by_target',{}).get(rank.slug) or 'Retained target-specific evidence; see the source note and incoming report provenance.'})
        sources.append(m)
    return {'target_id':rank.slug,'run_id':RUN_ID,'ranking_entries':[],'sources':sources}

def apply(plans):
    if any(p['identity_conflicts'] or p['source_conflicts'] for p in plans):raise RuntimeError('Review identity/source conflicts before applying')
    signature=private_signature();dump(RUN/'private-preservation-before.json',signature)
    receipts=[]
    for plan in plans:
        slug=plan['target'];report=next(r for r in SELECTED if r['target']==slug)
        out=ROOT/'research'/slug;out.mkdir(exist_ok=True)
        source_path=out/'sources.json'
        if source_path.exists() and not (out/f'sources.before-{RUN_ID}.json').exists():(out/f'sources.before-{RUN_ID}.json').write_bytes(source_path.read_bytes())
        additions=RUN/f'{slug}-source-additions.json';dump(additions,{'target_id':slug,'run_id':RUN_ID,'ranking_entries':[],'sources':plan['new_sources']})
        with transaction.atomic():
            rank=Ranking.objects.select_for_update().get(slug=slug)
            prior_run=rank.scope.get('editorial',{}).get('intake_run')
            if prior_run==RUN_ID:
                print(slug,'already applied');continue
            assert rank.revision==plan['expected_revision']
            original_sources={s.pk:(s.source_id,s.url,s.eligible,s.is_archived) for s in rank.sources.all()}
            ensure_revision(rank)
            output=io.StringIO();call_command('import_research',str(additions),target=slug,stdout=output)
            for sid,annotations in plan['existing_annotations'].items():
                src=rank.sources.get(source_id=sid);metadata=copy.deepcopy(src.metadata)
                metadata.setdefault('incoming_report_updates',[]).append({'run_id':RUN_ID,'records':annotations,'locally_verified':False})
                src.metadata=metadata;src.save(update_fields=['metadata','updated_at'])
            source_objects={s.source_id:s for s in rank.sources.all()}
            old_entries={getattr(e,rank.item_type+'_id'):e for e in rank.entries.filter(is_archived=False)}
            old_scope=copy.deepcopy(rank.scope);old_ed=old_scope.get('editorial',{});old_map=old_ed.get('entries',{})
            if plan['kind'] in ('literature','history'):
                rank.scope={**rank.scope,'forms':list(dict.fromkeys([*rank.scope.get('forms',[]),'collection']))}
                old_scope={**old_scope,'forms':rank.scope['forms']}
            if plan['kind']=='literature':
                catalog_repairs=[]
                for wid,form in {3552:'collection',3556:'collection',3574:'collection',3575:'collection',6633:'book',6635:'book'}.items():
                    work=Work.objects.get(pk=wid)
                    if work.form!=form:
                        catalog_repairs.append({'work_id':wid,'title':work.title,'previous_form':work.form,'corrected_form':form,'reason':'Supplied literary-fiction report identifies complete story collections or complete novels, not individual stories.'})
                        work.form=form;work.save(update_fields=['form','updated_at'])
                dump(RUN/'literature-catalog-form-repairs.json',catalog_repairs)
            explanations={};ids={};country_groups=defaultdict(list);created=0;reused=0
            for e in plan['entries']:
                if e['key'] in ids:objid=ids[e['key']]
                else:
                    if e['resolved_item_id'] is not None:objid=e['resolved_item_id'];reused+=1
                    else:
                        obj=create_catalog(e,plan['kind'],rank);objid=obj.pk;created+=1
                    ids[e['key']]=objid
                refs=[source_objects[sid] for sid in e['canonical_source_ids']]
                explanation={'standing':e['rationale'],'reading':e.get('reading_rationale',e['rationale']),
                    'caveat':'External-agent research supplied by the owner; source access claims are reported, not independently rechecked during intake. Unresolved limits and identity/edition details are preserved in the report record.',
                    'sources':[{'source_id':s.source_id,'title':s.title,'url':s.url,'eligible':s.eligible} for s in refs],
                    'metadata_status':'existing_metadata_preserved_new_metadata_pending','source_positions':old_map.get(str(objid),{}).get('source_positions',[]),
                    'reported_title':e['title'],'reported_attribution':e.get('authors'),'report_candidate_id':e['key'],'report_record':e['raw_record'],'report_file':plan['primary_file']}
                if plan['kind']=='country':
                    old=old_entries.get(objid);existing=next((g for g in old.groupings if g.get('section_index')==e['section_index']),{}) if old else {}
                    grouping={**existing,'country':e['country'],'section_index':e['section_index'],'local_rank':e['standing'],'reading_rank':e['reading'],
                              'historical_source_ids':existing.get('source_ids',[]),'candidate_source_ids':e['canonical_source_ids'],
                              'source_ids':list(dict.fromkeys([*existing.get('source_ids',[]),*e['canonical_source_ids']])),
                              'standing_note':e['rationale'],'report_section_notes':e['raw_record'],'report_file':plan['primary_file']}
                    confidence=re.search(r'Confidence: ([A-Z]+)',e['group_summary'])
                    if confidence:grouping['confidence']=confidence[1]
                    country_groups[objid].append(grouping)
                    if str(objid) in explanations:
                        seen={s['source_id'] for s in explanations[str(objid)]['sources']};explanations[str(objid)]['sources'] += [s for s in explanation['sources'] if s['source_id'] not in seen]
                    else:explanations[str(objid)]=explanation
                else:explanations[str(objid)]=explanation
            assert len(set(ids.values()))==len(ids),'Candidate identity collapse; resolve explicitly'
            if plan['kind']=='country':
                standing=list(dict.fromkeys(ids[e['key']] for e in sorted(plan['entries'],key=lambda e:(e['section_index'],e['standing']))))
                reading=list(dict.fromkeys(ids[e['key']] for e in sorted(plan['entries'],key=lambda e:(e['section_index'],e['reading']))))
            else:
                standing=[ids[e['key']] for e in sorted(plan['entries'],key=lambda e:e['standing'])];reading=[ids[e['key']] for e in sorted(plan['entries'],key=lambda e:e['reading'])]
            exclusions=excluded_records(report,set(old_entries),set(standing))
            for iid in set(old_entries)-set(standing):
                old_entries[iid].is_archived=True;old_entries[iid].save(update_fields=['is_archived'])
            for position,iid in enumerate(standing,1):
                entry=rank.entries.filter(**{rank.item_type+'_id':iid}).first() or RankingEntry(ranking=rank,**{rank.item_type+'_id':iid},source_rank=None,assessments={})
                entry.position=position;entry.is_archived=False;entry.rationale=explanations[str(iid)]['standing']
                if plan['kind']=='country':entry.groupings=country_groups[iid]
                entry.full_clean();entry.save()
            new_ed={'version':RUN_ID,'intake_run':RUN_ID,'published_on':'2026-09-27','report_hashes':plan['report_hashes'],
                    'notice':'Updated from owner-supplied external research; all previous sources and ranking revisions retained. Personal numerical scores remain unset.',
                    'method':'The supplied report provides qualitative standing and reading orders. Its source registers were structurally reconciled to existing identities and imported additively; no new source-by-source web review was performed.',
                    'entries':explanations,'orders':{'standing':{'label':'Country sections' if plan['kind']=='country' else 'Critical standing / enduring influence','description':'Updated supplied editorial order; see candidate evidence and limitations.','item_ids':standing},
                    'reading':{'label':'Country reading routes' if plan['kind']=='country' else 'Reading value today','description':'The supplied separate reading-value order. Country placements retain local reading_rank values.','item_ids':reading}},'reviewed_exclusions':exclusions}
            if plan['kind']=='philosophers':new_ed['alternate_report_preserved']='Philosophers_All_Time_Expanded_Ranking.docx: 189-person alternative; its sources are merged, its full proposal retained in research files. The 297-person report supplies the displayed orders.'
            if plan['kind']=='ancient':new_ed['intake_limitations']='Report contains cross-wired work annotations; existing bibliographic metadata was preserved, positional orders reconciled by title and author, and candidate/source mappings recovered from the source register where explicit.'
            rank.scope={**old_scope,'editorial':new_ed};rank.status='initial_selection'
            if plan['kind']=='country':
                confidence_by_section={g['section_index']:g.get('confidence','PROVISIONAL') for groups in country_groups.values() for g in groups}
                rank.scope.update(position_count=len(plan['entries']),distinct_work_count=len(standing),country_section_count=208,source_record_count=rank.sources.count(),checked_source_count=rank.sources.filter(eligible=True,is_archived=False).count(),confidence_counts=dict(Counter(confidence_by_section.values())))
            rank.full_clean();save_revision(rank,f'Owner DOCX update: {len(standing)} entries; additive source import; prior evidence and private data preserved.')
            for s in rank.sources.filter(pk__in=original_sources):assert original_sources[s.pk]==(s.source_id,s.url,s.eligible,s.is_archived),'Existing source changed or removed'
            assert rank.sources.filter(pk__in=original_sources).count()==len(original_sources)
            receipt={'target':slug,'revision':rank.revision,'before':plan['before'],'after':{'entries':rank.entries.filter(is_archived=False).count(),'sources':rank.sources.count(),'eligible':rank.sources.filter(eligible=True,is_archived=False).count()},
                     'new_source_records':len(plan['new_sources']),'new_eligible_source_records':sum(s['count_eligible'] for s in plan['new_sources']),
                     'existing_source_records_preserved':len(original_sources),'archived_ranking_entries':len(exclusions),'newly_resolved_catalog_candidates':created,
                     'catalog_id_map':ids,'source_id_maps':plan['source_id_maps'],'source_import_output':output.getvalue(),'primary_file':plan['primary_file']}
        dump(RUN/f'{slug}-import-receipt.json',receipt);dump(source_path,canonical_ledger(rank));dump(out/f'{RUN_ID}-candidate-map.json',{'target':slug,'catalog_id_map':ids,'primary_file':plan['primary_file'],'entries':plan['entries']})
        receipts.append(receipt);dump(RUN/'import-receipts.json',receipts)
        print(slug,receipt['before'],'->',receipt['after'],'revision',rank.revision,flush=True)
    after=private_signature();assert signature==after,'Private records changed during intake'
    dump(RUN/'private-preservation-after.json',after)
    with connection.cursor() as c:
        c.execute('PRAGMA foreign_key_check');assert not c.fetchall(),'Foreign-key errors'
        c.execute("SELECT name FROM sqlite_master WHERE type='trigger'");triggers=[r[0] for r in c.fetchall()]
    dump(RUN/'preservation-check.json',{'private_records_unchanged':True,'foreign_key_check':'passed','retained_database_triggers':triggers,'no_existing_sources_removed_or_reclassified':True})
    print('Preservation checks passed; no private records changed and all existing source records retained.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    plans=json.loads((RUN/'import-plan.json').read_text()) if args.apply else prepare()
    if args.apply:apply(plans)
