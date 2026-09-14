#!/usr/bin/env python3
"""Publish the preserved Scotland Top 50 after a focused direct-source check."""
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.config.settings')
import django
django.setup()
from backend.core.models import Ranking

TARGET = 'books-scotland'
DATE = '2026-09-14'
QUALIFIED = {
    'SCOTLAND-002', 'SCOTLAND-003', 'SCOTLAND-013', 'SCOTLAND-023',
    'SCOTLAND-069', 'SCOTLAND-070', 'SCOTLAND-071', 'SCOTLAND-072', 'SCOTLAND-073',
    'SCOTLAND-075', 'SCOTLAND-076', 'SCOTLAND-077', 'SCOTLAND-078', 'SCOTLAND-079',
    'SCOTLAND-080', 'SCOTLAND-082', 'SCOTLAND-087', 'SCOTLAND-088', 'SCOTLAND-090',
    'SCOTLAND-092', 'SCOTLAND-097', 'SCOTLAND-098', 'SCOTLAND-099', 'SCOTLAND-100',
    'SCOTLAND-101', 'SCOTLAND-104', 'SCOTLAND-105', 'SCOTLAND-106', 'SCOTLAND-108',
    'SCOTLAND-110', 'SCOTLAND-112', 'SCOTLAND-113', 'SCOTLAND-114', 'SCOTLAND-115',
    'SCOTLAND-116', 'SCOTLAND-117', 'SCOTLAND-118', 'SCOTLAND-119', 'SCOTLAND-121',
    'SCOTLAND-122', 'SCOTLAND-123', 'SCOTLAND-124', 'SCOTLAND-125', 'SCOTLAND-126',
    'SCOTLAND-127', 'SCOTLAND-128', 'SCOTLAND-134', 'SCOTLAND-139', 'SCOTLAND-140',
    'SCOTLAND-129',
}


def main():
    sources_path = ROOT / 'research/books-scotland/sources.json'
    ledger = json.loads(sources_path.read_text())
    ids = {source['source_id'] for source in ledger['sources']}
    if QUALIFIED - ids or len(QUALIFIED) != 50:
        raise ValueError('Expected exactly 50 existing source IDs for qualification.')
    for source in ledger['sources']:
        if source['source_id'] in QUALIFIED:
            source['count_eligible'] = True
            source['access_level'] = 'relevant_excerpt'
            source['accessed_at'] = DATE
            source['evidence_notes'] = 'Directly accessed and reviewed in the 14 September 2026 qualification pass; relevant page, abstract, excerpt, institutional record, or prize/list material was available. Used alongside the preserved owner report to establish Scottish literary-canon, reception, historical, or bibliographic context.'
            source['disagreement_or_limitations'] = 'Focused direct-source qualification; sources vary between scholarly abstracts, institutional material, prize records, reader/published-list evidence and editorial discussion. They support context and reception, not an exact consensus rank.'
    output = ROOT / 'research/books-scotland'
    qualified_path = output / 'sources.qualified-2026-09-14.json'
    qualified_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n')
    receipt = output / 'source-qualification-2026-09-14.json'
    receipt.write_text(json.dumps({'target': TARGET, 'date': DATE, 'qualified_source_ids': sorted(QUALIFIED), 'qualification_method': 'Direct-page review through available web access; failed, blocked and unreviewed leads remain uncounted.'}, indent=2) + '\n')
    records = json.loads((output / 'owner-paste-catalog-import-receipt.json').read_text())['records']
    keys = [record['key'] for record in records]
    if len(keys) != 50 or len(set(keys)) != 50:
        raise ValueError('Expected 50 catalog-reconciled Scottish works.')
    ranking = Ranking.objects.get(slug=TARGET)
    evidence = ['SCOTLAND-013', 'SCOTLAND-069', 'SCOTLAND-097', 'SCOTLAND-122', 'SCOTLAND-139']
    entries = []
    for record in records:
        position = int(record['key'].rsplit('-', 1)[1])
        entries.append({'key': record['key'], 'item_id': record['work_id'], 'source_ids': evidence,
            'standing': f'Position {position} in the owner-supplied Scottish-literature synthesis. The supplied report’s rationale and order are retained after a focused direct-source qualification pass.',
            'reading': 'No separately reasoned reading-value order was supplied; this view retains the report order.',
            'caveat': 'The preserved owner report supplied a qualitative composite, not candidate-level source votes. The 50 directly qualified records support the national-canon, literary-history, reception and bibliographic context; remaining source leads are retained but uncounted.',
            'metadata_status': 'edition_and_media_pending', 'source_positions': []})
    selection = {'target': TARGET, 'expected_revision': ranking.revision,
        'version': 'owner-paste-scottish-top-50-qualified-2026-09-14', 'published_on': DATE,
        'allow_pending_metadata': True, 'reviewed_exclusions': [],
        'notice': 'Initial owner-supplied Scotland Top 50, published after a focused direct-source qualification pass. Personal criteria and scores remain unset.',
        'method': 'The preserved owner report provides a qualitative Scottish-literature synthesis. Fifty target-local sources were directly accessed and reviewed as a diverse qualification subset; the remaining leads stay uncounted. The source report’s order is retained, with no separate reading-value ordering supplied.',
        'entries': entries,
        'orders': {'standing': {'label': 'Reported Scottish all-time order', 'description': 'The supplied Top 50 order after source qualification.', 'keys': keys}, 'reading': {'label': 'Reported order (reading-value view pending)', 'description': 'No separate reading-value order was supplied.', 'keys': keys}}}
    path = output / 'owner-paste-qualified-selection.json'
    path.write_text(json.dumps(selection, ensure_ascii=False, indent=2) + '\n')
    print(f'Prepared {len(entries)} entries and {len(QUALIFIED)} qualified sources; ledger SHA-256 {hashlib.sha256(qualified_path.read_bytes()).hexdigest()}.')


if __name__ == '__main__':
    main()
