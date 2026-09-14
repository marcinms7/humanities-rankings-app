"""Prepare five revision-safe publication inputs with explicit coverage limits."""
import os,sys,json,re,unicodedata
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.config.settings')
import django;django.setup()
from backend.core.models import Ranking,Work
P=ROOT/'research/_runs/2026-09-13/supplied-corpus'
targets=['books-all-time','philosophy-books-all-time','history-books-all-time','poetry-all-time','nonfiction-all-time']
additions=json.loads((P/'reviewed-additions.json').read_text())
receipt=json.loads((P/'reviewed-catalog-import-receipt.json').read_text())
ids={r['key']:r['work_id'] for r in receipt['records']}
def norm(s):return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().casefold())
def canon(s):return s.rstrip('/').replace('http://','https://')
heads={
 'history-books-all-time':['History of the Peloponnesian War','The Histories','The Decline and Fall of the Roman Empire','The Making of the Atomic Bomb','The Power Broker','The Warmth of Other Suns','The Guns of August','Battle Cry of Freedom','The Waning of the Middle Ages','The Civil War','The Rise and Fall of the Third Reich','Postwar','The Black Jacobins','Bloodlands','King Leopold','A Distant Mirror','The Dawn of Everything','1491','SPQR','The Fall of Constantinople'],
 'poetry-all-time':['The Iliad','The Odyssey','The Divine Comedy','Paradise Lost','Leaves of Grass','The Complete Poems of Emily Dickinson',"Shakespeare's Sonnets",'Les Fleurs du Mal','The Canterbury Tales','The Aeneid','Duino Elegies','Four Quartets','The Collected Poems of W.B. Yeats','The Complete Poems|John Keats','Metamorphoses','Songs of Innocence and of Experience','The Cantos','Omeros','Ariel','The Wild Iris'],
}
reading_heads={
 'history-books-all-time':['The Warmth of Other Suns','The Guns of August','The Power Broker','King Leopold','Postwar','The Making of the Atomic Bomb','SPQR','The Dawn of Everything','Hiroshima','Say Nothing','The Histories','The History of the Peloponnesian War','Bloodlands','The Rise and Fall of the Third Reich','The Time Traveller'],
 'poetry-all-time':['The Complete Poems of Emily Dickinson','Ariel','The Wild Iris','Twenty Love Poems','Leaves of Grass','The Odyssey','Poems New and Collected','Shakespeare','The Poetry of Robert Frost','Songs of Innocence','The Divine Comedy','The Iliad','Four Quartets','Duino Elegies','Omeros']
}
for target in targets:
    ranking=Ranking.objects.get(slug=target); old=ranking.scope.get('editorial',{})
    old_entries=old.get('entries',{}); oldstanding=old.get('orders',{}).get('standing',{}).get('item_ids',[])
    oldreading=old.get('orders',{}).get('reading',{}).get('item_ids',oldstanding)
    ledgerpath=ROOT/f'research/{target}/sources.json'; ledger=json.loads(ledgerpath.read_text())
    (P/f'{target}-ledger-before-publication.json').write_text(json.dumps(ledger,ensure_ascii=False,indent=2))
    sources={canon(s['canonical_url']):s for s in ledger['sources']}
    mentions={r['id']:r for r in json.loads((P/f'{target}-candidates.json').read_text())}
    selected={int(wid):{'item_id':int(wid),'prior':True} for wid in oldstanding}
    for row in additions.get(target,[]):
        if target=='philosophy-books-all-time' and row['title'] in {'Tao Te Ching','The Root Stanzas of the Middle Way: The Mulamadhyamakakarika','Discourses and Selected Writings','Discourses, Fragments, Handbook','The Essential Writings'}:
            continue  # Alternate translations/overlapping collections of existing primary works.
        wid=row['item_id'] or ids[row['key']]
        selected.setdefault(wid,{**row,'item_id':wid,'prior':False})
    works={w.pk:w for w in Work.objects.filter(pk__in=selected).prefetch_related('authors')}
    # One work identity per title/author family; preserve any existing identity.
    seen={}
    for wid in list(selected):
        work=works[wid]; key=(norm(work.title.split(':')[0]).removeprefix('the'),tuple(norm(a.name) for a in work.authors.all()))
        if key in seen and not selected[wid]['prior']: del selected[wid]
        else:seen[key]=wid
    def breadth(wid):
        urls=mentions.get(wid,{}).get('sources',[])
        domains={urlsplit(u).netloc.removeprefix('www.') for u in urls}
        return len(domains),min(len(urls),5)
    # Keep all earlier entries; additions beyond 250 remain in the catalog/pool.
    if len(selected)>250:
        new=sorted([wid for wid in selected if not selected[wid]['prior']],key=lambda wid:(-breadth(wid)[0],-breadth(wid)[1],selected[wid].get('source_rank',1000)))
        keep=set(oldstanding)|set(new[:max(0,250-len(oldstanding))]);selected={wid:r for wid,r in selected.items() if wid in keep}
    standing=sorted(selected,key=lambda wid:(-breadth(wid)[0],-breadth(wid)[1],oldstanding.index(wid) if wid in oldstanding else selected[wid].get('source_rank',1000)))
    def front(order,patterns):
        chosen=[]
        for pattern in patterns:
            title,_,author=pattern.partition('|')
            eligible=[wid for wid in order if wid not in chosen and norm(works[wid].title).removeprefix('the').startswith(norm(title).removeprefix('the')) and (not author or any(norm(author)==norm(a.name) for a in works[wid].authors.all()))]
            found=next((wid for wid in eligible if norm(works[wid].title).removeprefix('the')==norm(title).removeprefix('the')),eligible[0] if eligible else None)
            if found:chosen.append(found)
        return chosen+[wid for wid in order if wid not in chosen]
    if oldstanding:standing=[wid for wid in oldstanding[:30] if wid in selected]+[wid for wid in standing if wid not in oldstanding[:30]]
    else:standing=front(standing,heads[target])
    reading=([wid for wid in oldreading if wid in selected]+[wid for wid in standing if wid not in oldreading]) if oldreading else front(standing,reading_heads[target])
    records=[]; used={}
    for wid in standing:
        row=selected[wid]; work=works[wid]; previous=old_entries.get(str(wid),{})
        urls=mentions.get(wid,{}).get('sources',[])
        if row.get('url') and row['url'] not in urls:urls=[row['url']]+urls
        supporting=[]
        for url in urls:
            source=sources.get(canon(url))
            if not source:continue
            # Exact selected list rows establish inclusion; other appearances are
            # only cross-source discovery signals, not claimed merit votes.
            if not source.get('count_eligible') and url!=row.get('url'):continue
            supporting.append(source['source_id']);used.setdefault(source['source_id'],[]).append(work.title)
            if url==row.get('url'):
                source.update(count_eligible=True,accessed_at='2026-09-13',access_level='relevant_excerpt')
        prior_sources=[s['source_id'] for s in previous.get('sources',[]) if any(x['source_id']==s['source_id'] and x.get('count_eligible') for x in ledger['sources'])]
        supporting=list(dict.fromkeys(prior_sources+supporting))
        if not supporting:raise ValueError(f'No source evidence: {target} {work.title}')
        domains=breadth(wid)[0]
        signal=f"Located in the supplied corpus across {domains} website domains; repeated pages from one platform are capped in the coverage comparison. " if domains else ''
        standing_note=previous.get('standing') or (f"Included in the reviewed {target.replace('-all-time','').replace('-',' ')} selection for its contribution to the field. " + signal + 'The leading placements are editorial judgments; the remaining order uses breadth of source coverage as a limited reception signal.')
        reading_note=previous.get('reading') or ('The reading order foregrounds a range of engaging entry points while retaining demanding major works. '+('Moved forward as a starting point for exploring this tradition.' if reading.index(wid)<standing.index(wid) else 'Retained for sustained reading alongside the more immediate entry points.'))
        records.append({'key':str(wid),'item_id':wid,'source_ids':supporting,'standing':standing_note,'reading':reading_note,'caveat':previous.get('caveat') or 'Initial synthesis: community nominations can be uneven; source appearances do not establish agreement or objective quality. Edition/translation and image checks remain pending.','metadata_status':'edition_verification_pending','source_positions':([{'source_url':row['url'],'position':row['source_rank'],'type':'reader_list_position'}] if row.get('url') else previous.get('source_positions',[]))})
    for source in ledger['sources']:
        titles=list(dict.fromkeys(used.get(source['source_id'],[])))
        if not titles:continue
        source.setdefault('synthesis_reviews',[]).append({'run':'supplied-corpus-2026-09-13','matched_titles':titles,'limitation':'Text matches and extracted list rows; cross-page mentions are not independent endorsements.'})
        if source.get('owner_supplied'):
            source['evidence_notes']='Extracted source-list rows or title/author appearances supporting this candidate pool: '+ '; '.join(titles[:30])+'. Full readable extraction retained in supplied-corpus. Appearances indicate coverage, not an automatic positive review or merit vote.'
            source['candidates_or_claims_supported']=titles
    ledgerpath.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n')
    method='All supplied URLs were attempted and cached. Exact reader-list rows were reviewed for scope and matched to catalog identities; other title/author appearances supply limited coverage signals. The leading placements use editorial judgment; the remaining standing order prioritizes domain breadth, caps same-platform page recurrence at five as a tie-break, then retains prior position or source-list order. Existing top 30 and reading order are retained where present; new history/poetry reading heads foreground entry points. Mirrors and correlated sites remain a limitation; no claim of 959 independent votes or personal numerical scores is made.'
    batch={'target':target,'expected_revision':ranking.revision,'allow_expansion':True,'allow_pending_metadata':True,'version':'supplied-corpus-v1','published_on':'2026-09-13','notice':'Broad initial synthesis from the supplied corpus. Source coverage and editorial judgment inform the order; inaccessible pages and unresolved identities remain in the audit.','method':method,'entries':records,'orders':{'standing':{'label':'Critical standing / enduring influence','description':'Editorial leading group, followed by breadth of source coverage.','keys':[str(w) for w in standing]},'reading':{'label':'Reading value today','description':'Editorial entry points and sustained reading; not a personalized score.','keys':[str(w) for w in reading]}},'reviewed_exclusions':[]}
    (P/f'{target}-publication.json').write_text(json.dumps(batch,ensure_ascii=False,indent=2)+'\n')
    (P/f'{target}-order.tsv').write_text('standing\treading\ttitle\tauthor\tsource_links\n'+'\n'.join(f"{i+1}\t{reading.index(wid)+1}\t{works[wid].title}\t{', '.join(a.name for a in works[wid].authors.all())}\t{len(records[i]['source_ids'])}" for i,wid in enumerate(standing)))
    print(target,len(records),'entries',len(used),'new corpus sources linked')
