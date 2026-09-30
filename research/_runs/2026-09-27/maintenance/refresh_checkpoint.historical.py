"""Refresh research documents from saved ledgers and the current database; no DB writes."""
import hashlib
import json
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.config.settings')
import django
django.setup()
from backend.core.models import Ranking, Work, Person, Edition

RUN = ROOT / 'research/_runs/2026-09-13'
TARGETS = ['books-all-time', 'literature-all-time', 'nonfiction-all-time', 'philosophy-books-all-time', 'philosophers-all-time']
rows = []
all_sources = set()
for target in TARGETS:
    directory = ROOT / 'research' / target
    ledger = json.loads((directory / 'sources.json').read_text())
    sources = [s for s in ledger['sources'] if s['count_eligible']]
    ranking = Ranking.objects.get(slug=target)
    assert ranking.sources.filter(eligible=True, is_archived=False).count() == len(sources)
    assert len({s['underlying_source_id'] for s in sources}) == len(sources)
    all_sources.update(s['underlying_source_id'] for s in sources)
    release = json.loads((directory / 'initial-selection-v2.json').read_text())
    assert ranking.scope['editorial']['input_sha256'] == hashlib.sha256((directory / 'initial-selection-v2.json').read_bytes()).hexdigest()
    entries = list(ranking.entries.filter(is_archived=False))
    assert len(entries) == len(release['entries'])
    assert not ranking.criteria and all(e.assessments == {} and e.source_rank is None for e in entries)
    assert ranking.last_researched_at is None
    assert ranking.revisions.count() == 2
    assert ranking.revisions.get(number=1).snapshot['entries'] == []
    expected_ids = {e.work_id or e.person_id for e in entries}
    for lens in ['standing', 'reading']:
        order = ranking.scope['editorial']['orders'][lens]['item_ids']
        assert len(order) == len(expected_ids) and set(order) == expected_ids
    for e in entries:
        obj = e.work or e.person
        if e.work:
            assert obj.default_edition and obj.default_edition.cover and obj.default_edition.cover.storage.exists(obj.default_edition.cover.name)
            assert all(p.portrait and p.portrait.storage.exists(p.portrait.name) for p in obj.authors.all())
        else:
            assert obj.portrait and obj.portrait.storage.exists(obj.portrait.name)
    audit = dict(consulted_on='2026-09-13',eligible_sources=len(sources),families=dict(Counter(s['source_family'] for s in sources).most_common()),domains=dict(Counter(s['domain_or_platform'] for s in sources).most_common()),languages=dict(Counter(s.get('language','unknown') for s in sources).most_common()),publishers=dict(Counter(s.get('publisher_group') or s.get('publisher') or 'unknown' for s in sources).most_common()),published_entries=len(entries),revision=ranking.revision,all_entries_illustrated=True,final_scores_unset=True)
    (directory / 'evidence-audit-v2.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    previous = (directory / 'RESEARCH.md').read_text()
    archive = RUN / f'before-consolidation-{target}-RESEARCH.md'
    if not archive.exists(): archive.write_text(previous)
    next_work = previous.split('## Next useful work\n\n',1)[-1].split('## Preservation',1)[0] if '## Next useful work' in previous else 'Expand the comparison universe and strengthen thin dossiers.'
    family_table = '\n'.join(f'| {k} | {v} |' for k,v in audit['families'].items())
    notes = f'''# {ranking.title} — research state

Updated 13 September 2026, through source batch 32. **{len(sources)} distinct eligible sources are saved and imported for this target.** The hard minimum of 50 is met; worldwide research is still incomplete. The owner wants much greater depth and diversity, over 100 and toward 200 or more useful sources. No threshold proves completion.

**Now populated in the app: {len(entries)} illustrated entries, revision {ranking.revision}, with both critical standing/enduring influence and reading value today.** [Open the ranking](http://127.0.0.1:8001/#/rankings/{ranking.pk}). These are published initial selections within a limited comparison set, not completed worldwide Top lists. Intended lengths remain 100–200. Numerical criteria, weights and scores remain unset; completed-global research dates remain null.

[Published selection and explanations](INITIAL_SELECTION.md) · [Versioned input](initial-selection-v2.json) · [Import receipt](initial-selection-v2-import-receipt.json) · [Cumulative evidence](sources.json) · [Batch log](BATCH_LOG.md) · [Current diversity audit](evidence-audit-v2.json) · [Historical 25-candidate pilot](PROVISIONAL_RANKING.md)

## Scope and method

{release['notice']}

{release['method']}

## Actual source mix

| Family | Sources |
| --- | ---: |
{family_table}

Largest domains: {', '.join(f'{k}: {v}' for k,v in list(audit['domains'].items())[:10])}.

Consulted languages: {', '.join(f'{k}: {v}' for k,v in audit['languages'].items())}.

These categories describe the register, not proof of balanced coverage. Shared ownership, copied lists and repeated arguments are not independent votes. Reference material, primary texts and abstract-only access support different kinds of claims. Image and publisher bibliographic verification do not add critical-source credit.

## Next useful work

{next_work.strip()}

Continue expanding the illustrated app selection as individual dossiers become ready. Exact adjacent positions need stronger direct comparison. Do not regenerate or overwrite the historical v1 proposals. The first-publication command refuses to overwrite existing selections; prepare a reviewed revision update before adding or reordering entries.

## Preservation

Prior empty ranking revisions and v1 proposals are preserved. Catalog batches, image manifests with credits/hashes, and import receipts are in `research/catalog/`. Existing sources were imported without --update-existing. Private account and preference records were not edited by this research. A new library item appeared during the live session and is retained; the preservation audit records this separately. Source and publication dates remain distinct.
'''
    (directory / 'RESEARCH.md').write_text(notes)
    bykey = {r['key']:r for r in release['entries']}
    lines = [f'# {ranking.title} — illustrated initial selection', '', release['notice'], '', release['method'], '', f'Database revision {ranking.revision}; published {release["published_on"]}. [Open in the app](http://127.0.0.1:8001/#/rankings/{ranking.pk}).', '']
    sources_by_id = {s['source_id']:s for s in sources}
    for lens in ['standing','reading']:
        lines.extend(['## '+release['orders'][lens]['label'], ''])
        for index,key in enumerate(release['orders'][lens]['keys'],1):
            record = bykey[key]
            obj = Work.objects.get(pk=record['item_id']) if ranking.item_type=='work' else Person.objects.get(pk=record['item_id'])
            title = obj.title if ranking.item_type=='work' else obj.name
            citations = ' · '.join(f'[{sid}]({sources_by_id[sid]["canonical_url"]})' for sid in record['source_ids'])
            lines.extend([f'{index}. **{title}** — {record[lens]}', '', f'   Evidence: {citations}. Limitation: {record["caveat"]}', ''])
    (directory / 'INITIAL_SELECTION.md').write_text('\n'.join(lines))
    rows.append(dict(target=target,title=ranking.title,id=ranking.pk,sources=len(sources),entries=len(entries),revision=ranking.revision))

summary=dict(date='2026-09-13',targets=rows,target_source_records=sum(r['sources'] for r in rows),global_underlying_source_identities=len(all_sources),works=Work.objects.count(),people=Person.objects.count(),editions=Edition.objects.count(),covers=Edition.objects.exclude(cover='').count(),portraits=Person.objects.exclude(portrait='').count(),verification='Read-only ledger/database/media consistency checks. No test suites, browser automation or test accounts.')
(RUN/'publication-audit.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary,ensure_ascii=False))
