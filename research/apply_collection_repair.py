"""Apply a saved reviewed collection batch, retaining previous entries/revisions."""
import sys, json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from research.import_collection_repairs import RUN, ROOT, Work, Ranking, norm
from django.core.management import call_command
from django.db import transaction
from backend.core.views import ensure_revision

def apply(target):
    definition=json.loads((RUN/(target+'-definition.json')).read_text())
    batch=json.loads((RUN/(target+'-catalog.json')).read_text())
    rows=json.loads((RUN/(target+'-mapped.json')).read_text())
    with transaction.atomic():
        named=[r for r in batch['works'] if r['authors']]
        resolved={}
        if named:
            p=RUN/(target+'-named-catalog.json'); p.write_text(json.dumps({**batch,'works':named},ensure_ascii=False,indent=2)+'\n')
            call_command('import_catalog_research',str(p))
            receipt=json.loads(p.with_name(p.stem+'-import-receipt.json').read_text())
            resolved.update({r['key']:r['work_id'] for r in receipt['records']})
        for record in batch['works']:
            if record['authors']: continue
            existing=Work.objects.filter(title=record['title'],authors__isnull=True,is_archived=False).first()
            if not existing:
                existing=Work(**{k:record[k] for k in ['title','form','field','original_year','original_language','countries','description']})
                existing.full_clean();existing.save()
            resolved[record['key']]=existing.pk
        r,created=Ranking.objects.get_or_create(slug=target,defaults=dict(title=definition.get('title',target),origin='external',
                presentation=definition.get('presentation','unranked'),domain='literature',source_url=definition['url']))
        ensure_revision(r)
        r.source_url=definition['url']
        if definition.get('description'): r.description=definition['description']
        if definition.get('title'): r.title=definition['title']
        entries={}
        for row in rows:
            wid=row['work_id'] or resolved[row['key']]
            if wid in entries: entries[wid]['note']+=' '+row['note']
            else: entries[wid]=dict(work_id=wid,note=row['note'])
        r.target_size=len(entries); r.save()
        payload=dict(target=target,presentation=r.presentation,expected_revision=r.revision,source_checked_on='2026-09-13',
            status=definition.get('status','imported'),method_note=definition['method'],unresolved_count=definition.get('unresolved_count',0),
            allow_reviewed_replacement=True,entries=list(entries.values()))
        p=ROOT/'research'/target/'reviewed-contents-20260913.json';p.parent.mkdir(parents=True,exist_ok=True)
        if p.exists(): raise RuntimeError('Do not overwrite a published input; use a new dated filename.')
        p.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
        call_command('import_external_list',str(p))
        (RUN/(target+'-catalog-resolution.json')).write_text(json.dumps(resolved,indent=2)+'\n')

if __name__=='__main__':
    for target in sys.argv[1:]: apply(target)
