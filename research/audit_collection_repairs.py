"""Read-only publication checks and durable provenance/continuation notes."""
from import_collection_repairs import *
import hashlib, shutil, sqlite3
from collections import Counter
from django.db import connection

targets=['mcevoy-reading-list','mcevoy-favourites','great-books-western-world','mcevoy-lectures']+[f'mcevoy-schedule-{y}' for y in range(2021,2027)]
audit={}
for target in targets:
    r=Ranking.objects.get(slug=target)
    entries=list(r.entries.filter(is_archived=False).select_related('work').order_by('position','id'))
    payload=json.loads((ROOT/'research'/target/'reviewed-contents-20260913.json').read_text())
    assert [e.work_id for e in entries]==[e['work_id'] for e in payload['entries']]
    assert [e.position for e in entries]==list(range(1,len(entries)+1))
    assert all(e.source_rank is None for e in entries)
    assert r.target_size==len(entries) and r.origin=='external' and not r.owner_id
    audit[target]=dict(id=r.pk,revision=r.revision,entries=len(entries),archived_entries=r.entries.filter(is_archived=True).count(),
        revision_snapshots=r.revisions.count(),status=r.status,source_url=r.source_url)
    note=f'''# {r.title}

Verified and imported 13 September 2026: **{len(entries)} active entries**, revision **{r.revision}**.

{r.description}

Source: {r.source_url}

Method: {payload['method_note']}

Saved input: `reviewed-contents-20260913.json`; matching import receipt alongside it. Source snapshots, reviewed rows, catalog mapping and audit are in `research/_runs/2026-09-13/collection-repair/`. Original records/revisions are preserved; incorrect prior memberships are archived, not deleted. Private tables were not written. Covers and verified reading editions for newly added records remain a separate enrichment task. No browser automation or test suite was run.
'''
    (ROOT/'research'/target/'RESEARCH.md').write_text(note)
gb=Ranking.objects.get(slug='great-books-western-world')
assert not gb.entries.filter(is_archived=False,work__authors__name='Sun Tzu').exists()
assert not gb.entries.filter(is_archived=False,work__title='In Search of Lost Time').exists()
gbrows=json.loads((RUN/'greatbooks-1990-reviewed-rows.json').read_text())
assert set(int(r['group'].rsplit(' ',1)[-1]) for r in gbrows)==set(range(1,61))
assert len(gbrows)==386
reading=Ranking.objects.get(slug='mcevoy-reading-list')
assert reading.entries.filter(is_archived=False,work__title='Meditations',work__authors__name='Marcus Aurelius').exists()
for title in ['The Old Testament','The New Testament']:
    assert reading.entries.filter(is_archived=False,work__title=title,work__authors__isnull=True).exists()

manifest=[]
for filename in ['mcevoy.html','gbww.html','gbww1990.html','mcevoy-sitemap.html']:
    src=Path('/tmp')/filename;dest=RUN/filename
    if not dest.exists():shutil.copyfile(src,dest)
    manifest.append(dict(file=filename,sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),bytes=dest.stat().st_size))
save('source-snapshot-manifest.json',manifest)
save('publication-audit.json',audit)
with connection.cursor() as c:
    c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND sql LIKE '%DELETE%'")
    guards=c.fetchone()[0]
    assert guards>=8
print(json.dumps(dict(rankings=audit,delete_guards=guards),indent=2))
