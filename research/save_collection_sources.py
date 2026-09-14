"""Add external-list provenance; curated-only import_research is inapplicable here."""
from import_collection_repairs import *
from backend.core.models import ResearchSource
from django.db import transaction
from datetime import date

audit=json.loads((RUN/'publication-audit.json').read_text())
for target in audit:
    r=Ranking.objects.get(slug=target)
    definition=json.loads((RUN/(target+'-definition.json')).read_text())
    urls=[(r.source_url,r.title+' — source contents',definition['method'])]
    if target=='great-books-western-world':
        urls.append(('https://www.bopsecrets.org/gateway/book-lists/greatbooks.htm','Great Books — complete 1990 volume table',
                     'Cross-check of all 60 volume assignments, the four deleted first-edition works, and excerpt scope including Swann in Love.'))
    if target=='mcevoy-schedule-2021':
        urls=[]
        for row in json.loads((RUN/(target+'-reviewed-rows.json')).read_text()):
            url=re.search(r'https://www.patreon.com/[^\s]+',row['note'])[0]
            urls.append((url,row['title']+' — dated public post',f"Public header dated {row['group']} confirms this work's 2021 membership. Paid body not accessed."))
    sources=[]
    with transaction.atomic():
        for i,(url,title,evidence) in enumerate(urls,1):
            record=dict(source_id=f'COLLECTION-REPAIR-{i:02}',underlying_source_id='collection-repair:'+url,
                        title=title,canonical_url=url,source_family='published_collection',target_ids=[target],
                        relevance_by_target={target:evidence},evidence_notes=evidence,accessed_at='2026-09-13',eligible=True,
                        limitations='Named-list membership evidence only; no independent quality assessment or paid lecture content review.')
            existing=r.sources.filter(url=url).first()
            if not existing:
                obj=ResearchSource(ranking=r,source_id=record['source_id'],underlying_source_id=record['underlying_source_id'],title=title,
                    url=url,family='published_collection',publisher='Benjamin McEvoy' if target.startswith('mcevoy') else 'Collection contents reference',
                    evidence=evidence,limitations=record['limitations'],consulted_on=date(2026,9,13),eligible=True,metadata=record)
                obj.full_clean();obj.save()
            sources.append(record)
        path=ROOT/'research'/target/'sources.json'
        ledger=json.loads(path.read_text()) if path.exists() else dict(target_id=target,status='named_external_list_import',sources=[])
        known={s['canonical_url'] for s in ledger['sources']}
        ledger['sources'].extend(s for s in sources if s['canonical_url'] not in known)
        ledger['saved_at']='2026-09-13'
        path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n')
    print(target,len(sources),'source records preserved/saved')
