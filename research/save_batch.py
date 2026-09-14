"""Save reviewed consultation notes, then use the existing evidence-only importer.

Research utility: no network calls, catalog writes, scoring or publication.
Usage: .venv/bin/python research/save_batch.py research/_runs/2026-09-12/batch-NN.json
"""
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
TARGETS = {
    'A': 'books-all-time', 'L': 'literature-all-time',
    'N': 'nonfiction-all-time', 'B': 'philosophy-books-all-time',
    'P': 'philosophers-all-time',
}


def save(batch_path):
    batch = json.loads(batch_path.read_text())
    consulted_on = batch.get('consulted_on', '2026-09-12')
    ledgers = {}
    registry = {}
    for target in TARGETS.values():
        path = ROOT / 'research' / target / 'sources.json'
        ledger = json.loads(path.read_text()) if path.exists() else {
            'target_id': target, 'minimum_eligible_sources': 50,
            'criteria_version': None, 'ranking_entries': [], 'sources': [],
        }
        ledgers[target] = ledger
        for source in ledger['sources']:
            registry[source['canonical_url'].rstrip('/')] = (
                source['source_id'], source['underlying_source_id'])
    touched = set()
    for item in batch['sources']:
        url = item['url']
        source_id, underlying = registry.get(url.rstrip('/'), (item['id'], item['id']))
        for alias, contribution in item['targets'].items():
            target = TARGETS[alias]
            ledger = ledgers[target]
            touched.add(target)
            if any(s['underlying_source_id'] == underlying for s in ledger['sources']):
                continue
            domain = urlparse(url).netloc.removeprefix('www.')
            source = {
                'source_id': source_id, 'underlying_source_id': underlying,
                'title': item['title'], 'author': item.get('author'),
                'publisher': item['publisher'], 'publisher_group': item.get('group', item['publisher']),
                'canonical_url': url, 'access_url': item.get('access_url', url),
                'publication_date': item.get('date'), 'accessed_at': item.get('consulted_on', consulted_on),
                'source_family': item['family'], 'domain_or_platform': domain,
                'language': item.get('language', 'en'), 'access_level': item.get('access', 'relevant_excerpt'),
                'depends_on_source_ids': item.get('dependencies_by_target', {}).get(alias, []),
                'dependency_note': item.get('dependency_note'),
                'target_ids': [target], 'relevance_by_target': {target: contribution},
                'evidence_notes': item['note'], 'location': item['location'],
                'evidence_role': item.get('role', 'candidate_evidence'),
                'candidates_or_claims_supported': item['candidates'],
                'disagreement_or_limitations': item['limits'],
                'count_eligible': True, 'exclusion_reason': None,
                'consultation_batch': str(batch_path.relative_to(ROOT)),
            }
            ledger['sources'].append(source)
    for target in sorted(touched):
        directory = ROOT / 'research' / target
        directory.mkdir(parents=True, exist_ok=True)
        ledger = ledgers[target]
        ledger.update(status='collecting_evidence_criteria_unset', saved_at=consulted_on)
        path = directory / 'sources.json'
        temp = path.with_suffix('.json.tmp')
        temp.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n')
        temp.replace(path)
        result = subprocess.run([
            str(ROOT / '.venv/bin/python'), 'manage.py', 'import_research',
            str(path.relative_to(ROOT)), '--target', target,
        ], cwd=ROOT, text=True, capture_output=True)
        print(result.stdout, end='')
        if result.returncode:
            print(result.stderr, file=sys.stderr)
            raise SystemExit(result.returncode)
        eligible = [s for s in ledger['sources'] if s['count_eligible']]
        families = dict(Counter(s['source_family'] for s in eligible))
        notes = directory / 'BATCH_LOG.md'
        with notes.open('a') as out:
            out.write(f"\n## {batch_path.stem} — {consulted_on}\n\n")
            out.write(f"Saved and imported: **{len(eligible)} eligible sources**. Families: {families}.\n\n")
            out.write(batch['summary'] + '\n\n')
            out.write('Next: ' + batch['next'] + '\n')
            out.write('\nPersonal criteria and scores remain unset. This evidence import does not change ranking entries or completed-research dates.\n')


if __name__ == '__main__':
    save(Path(sys.argv[1]).resolve())
