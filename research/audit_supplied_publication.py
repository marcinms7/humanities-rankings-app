"""Read-only publication checks and saved continuation notes."""
import os,sys,json,sqlite3,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.config.settings')
import django;django.setup()
from backend.core.models import Ranking
P=ROOT/'research/_runs/2026-09-13/supplied-corpus'
index=json.loads((P/'index.json').read_text());report={}
for target,urls in index.items():
    r=Ranking.objects.get(slug=target);active=list(r.entries.filter(is_archived=False).values_list('work_id',flat=True)); ed=r.scope['editorial']
    for lens in ('standing','reading'):
        order=ed['orders'][lens]['item_ids'];assert len(order)==len(active) and set(order)==set(active)
    assert not r.entries.filter(is_archived=False).exclude(assessments={}).exists()
    successful=failed=0
    for url in urls:
        d=json.loads((P/(hashlib.sha256(url.encode()).hexdigest()+'.json')).read_text())
        if d.get('error'):failed+=1
        else:successful+=1
    report[target]={'entries':len(active),'revision':r.revision,'target_urls':len(urls),'retrieved':successful,'failed':failed,'source_links':len({s['source_id'] for entry in ed['entries'].values() for s in entry['sources']}),'both_orders_valid':True}
    notes=ROOT/f'research/{target}/RESEARCH.md'
    with notes.open('a') as f:
        f.write(f"\n\n## Supplied-corpus publication — 13 September 2026\n\nPublished {len(active)} entries, revision {r.revision}, with both qualitative orders. All {len(urls)} supplied URLs were attempted ({successful} returned, {failed} failed); a returned page is not by itself an independently reviewed endorsement. Explicit list rows were reviewed for scope and title/author occurrences provide supplementary coverage signals. Ranking evidence links and the full method are in `research/_runs/2026-09-13/supplied-corpus/{target}-publication.json`; order TSVs and per-URL audits accompany it. All earlier entries/revisions and source records remain. No personal numerical criteria or scores were assigned.\n\nLimitations: only supported catalog matches and the reviewed explicit candidate pool were selected, not every item in every source. Other candidates remain in the extracted row files. Domain breadth reduces but does not eliminate source dependence; multilingual titles without a reliable English identity remain unresolved. Older automated consultation counts are not a measure of substantive source review. Edition/cover enrichment remains pending for newly created works.\n")
(P/'publication-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
