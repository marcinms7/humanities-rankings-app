#!/usr/bin/env python3
"""Intake the owner-supplied structured Classical Education Top 250 report.

This is intentionally separate from the ordinary Top-150 importer: the report
has stable W/P/R records, a 250-work scope, and retained metadata/lead rows
that must remain visible without inflating substantive source totals.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.config.settings')
import django
django.setup()

from django.db import transaction
from backend.core.models import Person, Ranking, Work
from backend.core.views import ensure_revision

TARGET = 'classical-education-guide'
RUN = '2026-09-14-owner-chat-attachment'
ACCESS_DATE = '2026-09-14'
REPORT = Path('/Users/marcinswierczewski/.codex/attachments/2b264630-3845-4ed5-adf8-ec1450dc7e8f/pasted-text.txt')


def value(block: str, label: str) -> str:
    match = re.search(rf'(?m)^{re.escape(label)}\s*:\s*(.+)$', block)
    return match.group(1).strip() if match else ''


def first_year(text: str) -> int | None:
    bce = re.search(r'(?i)(\d{1,4})\s*(?:bce|bc)', text)
    if bce:
        return -int(bce.group(1))
    modern = re.search(r'(?<!\d)(1[0-9]{3}|20[0-9]{2})(?!\d)', text)
    return int(modern.group(1)) if modern else None


def source_family(status: str) -> str:
    code = status.strip()[:1].upper()
    return {
        'P': 'primary_text_excerpt', 'E': 'scholarly_edition_or_excerpt', 'A': 'abstract_or_summary',
        'T': 'tertiary_reference', 'C': 'commentary_or_specialist_guide', 'F': 'reader_community',
        'M': 'metadata_or_catalogue', 'D': 'duplicate_record', 'U': 'unverified_lead',
    }.get(code, 'owner_report_source')


def access_level(status: str, eligible: bool) -> str:
    if not eligible:
        return 'not_accessed' if status.strip().startswith('U') else 'summary_only'
    if status.strip().startswith('A'):
        return 'abstract_only'
    return 'relevant_excerpt'


def parse_sources(text: str) -> list[dict]:
    blocks = re.findall(r'(?ms)^BEGIN SOURCE ([PR]\d{3})\n(.*?)^END SOURCE \1\s*$', text)
    if len(blocks) != 311:
        raise ValueError(f'Expected 311 source blocks, found {len(blocks)}')
    sources = []
    for report_id, block in blocks:
        title = value(block, 'Title/description')
        url = value(block, 'Full URL')
        status = value(block, 'Access status')
        scope = value(block, 'Scope checked')
        relevance = value(block, 'Relevance')
        ranks = value(block, 'Linked merit ranks')
        eligible = bool(re.search(r'(?im)^Counted as substantive consulted evidence:\s*YES\b', block))
        if not title or not url.startswith(('https://', 'http://')) or not status:
            raise ValueError(f'{report_id}: missing required source identity fields')
        host = urlsplit(url).netloc.removeprefix('www.') or 'reported-source'
        sources.append({
            'source_id': f'CLASSICAL-{report_id}',
            'underlying_source_id': f'{TARGET}:owner-report:{report_id}',
            'title': title[:500],
            'author': None,
            'publisher': host,
            'publisher_group': host,
            'canonical_url': url,
            'access_url': url,
            'publication_date': None,
            'accessed_at': ACCESS_DATE if eligible else None,
            'source_family': source_family(status),
            'domain_or_platform': host,
            'language': value(block, 'Language/geographic context') or 'as reported',
            'access_level': access_level(status, eligible),
            'depends_on_source_ids': [],
            'dependency_note': 'Dependencies, duplicate groupings and alternate manifestations remain documented in the preserved owner report.',
            'target_ids': [TARGET],
            'relevance_by_target': {TARGET: 'Owner-supplied Classical Education Top 250 report identifies this source as relevant to this exact ranking; its reported access status and scope are retained.'},
            'evidence_notes': f'Reported consultation: {scope or relevance or "See preserved structured source record."}',
            'location': ranks or None,
            'evidence_role': 'owner_supplied_report_evidence' if eligible else 'owner_supplied_lead_or_metadata',
            'candidates_or_claims_supported': [f'W{number.zfill(3)}' for number in re.findall(r'\b(\d{1,3})\b', ranks) if number.isdigit() and 1 <= int(number) <= 250],
            'disagreement_or_limitations': f'Reported access status: {status}. This file-driven intake retains the report’s evidence classification and does not newly re-open this page.',
            'count_eligible': eligible,
            'exclusion_reason': None if eligible else 'The owner-supplied report marks this record metadata-only, duplicate, unavailable or otherwise non-substantive.',
            'consultation_batch': f'research/incoming/{TARGET}/{RUN}/report.txt',
            'owner_supplied': True,
            'report_source_id': report_id,
            'report_access_status': status,
        })
    if sum(source['count_eligible'] for source in sources) != 287:
        raise ValueError('Report source eligibility did not reproduce the stated 287 substantive records')
    return sources


def work_form(text: str) -> str:
    lower = text.casefold()
    if any(word in lower for word in ('traged', 'comedy', 'drama', 'play')):
        return 'play'
    if any(word in lower for word in ('poetry', 'epic', 'eleg', 'lyric', 'hexameter', 'epigram')):
        return 'poem'
    if any(word in lower for word in ('collection', 'corpus', 'fragments', 'testimonia', 'letters', 'dialogues')):
        return 'collection'
    if 'essay' in lower:
        return 'essay'
    return 'book'


def parse_works(text: str, source_ids: set[str]) -> list[dict]:
    blocks = re.findall(r'(?ms)^BEGIN WORK (W\d{3})\n(.*?)^END WORK \1\s*$', text)
    if len(blocks) != 250:
        raise ValueError(f'Expected 250 work blocks, found {len(blocks)}')
    works = []
    for work_id, block in blocks:
        rank = int(value(block, 'Merit rank'))
        title, author = value(block, 'Title'), value(block, 'Author/tradition')
        form_text = value(block, 'Form')
        refs = [f'CLASSICAL-{report_id}' for report_id in re.findall(r'\b([PR]\d{3})\b', value(block, 'Supporting source IDs'))]
        refs = list(dict.fromkeys(ref for ref in refs if ref in source_ids))
        if rank != int(work_id[1:]) or not title or not author or not refs:
            raise ValueError(f'{work_id}: missing rank, title, author or resolved evidence')
        works.append({
            'key': work_id, 'position': rank, 'title': title, 'attribution': author,
            'group': value(block, 'Group') or 'Classical education',
            'date': value(block, 'Composition/publication'),
            'form_reported': form_text or 'Book', 'form': work_form(form_text),
            'tradition': 'Greek and Roman tradition / classical reception',
            'language': value(block, 'Original language') or 'Unspecified in supplied report',
            'rationale': value(block, 'Educational and literary value'),
            'beginner_start': value(block, 'Beginner start'),
            'reading_language': value(block, 'Reading language'),
            'original_language_study': value(block, 'Original-language study'),
            'coverage': value(block, 'Evidence coverage'),
            'refs': refs,
            'original_year': first_year(value(block, 'Composition/publication')),
        })
    works.sort(key=lambda work: work['position'])
    if [work['position'] for work in works] != list(range(1, 251)):
        raise ValueError('Works are not a consecutive 1–250 order')
    return works


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def prepare(dry_run: bool) -> None:
    raw = REPORT.read_bytes()
    text = raw.decode('utf-8')
    digest = hashlib.sha256(raw).hexdigest()
    sources = parse_sources(text)
    works = parse_works(text, {source['source_id'] for source in sources})
    print(f'{TARGET}: {len(works)} works; {len(sources)} retained sources; {sum(s["count_eligible"] for s in sources)} substantive; sha256={digest}')
    if dry_run:
        return
    incoming = ROOT / 'research' / 'incoming' / TARGET / RUN
    incoming.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPORT, incoming / 'report.txt')
    (incoming / 'RECEIPT.md').write_text(
        f'# Owner chat attachment receipt\n\n- Received: {ACCESS_DATE}\n- Requested action: publish this ranking in the Classical education tab\n- Original attachment: `{REPORT}`\n- SHA-256: `{digest}`\n- Parsed: 250 works; 311 retained source records; 287 report-designated substantive records.\n- Caveat: report access categories are preserved; no page-by-page local rereading was performed during intake.\n'
    )
    target_dir = ROOT / 'research' / TARGET
    write_json(target_dir / 'sources.json', {'target_id': TARGET, 'minimum_eligible_sources': 50, 'criteria_version': None, 'ranking_entries': [], 'sources': sources, 'status': 'owner_report_imported_pending_publication', 'saved_at': ACCESS_DATE})
    write_json(target_dir / 'owner-chat-candidates-2026-09-14.json', works)
    (target_dir / 'RESEARCH.md').write_text(
        f'# Classical education · Guide\n\nOwner-supplied structured Top 250 report preserved at `research/incoming/{TARGET}/{RUN}/report.txt` (SHA-256 `{digest}`). Parsed 250 ranked works, 311 retained source records and 287 report-designated substantive consultations. The report’s P/R access status, scope and limitations are retained. Its source claims were not independently re-opened during this file-driven intake.\n\nThe ranking is separate from the private Paideia syllabus and study-tool progress. Personal criteria, scores and overrides remain unset.\n'
    )


def candidate_names(raw: str) -> list[str]:
    values = [raw]
    attributed = re.search(r'(?i)attributed to\s+([^;,]+)', raw)
    if attributed:
        values.append(attributed.group(1).strip())
    first = raw.split(';', 1)[0].split(',', 1)[0].strip()
    if first:
        values.append(first)
    return list(dict.fromkeys(values))


def resolve_person(raw: str, tradition: str) -> Person:
    for candidate in candidate_names(raw):
        person = Person.objects.filter(is_archived=False, name__iexact=candidate).first()
        if person:
            return person
    return Person.objects.create(name=raw, biography='', countries=[tradition], source_url='')


def resolve_work(record: dict, person: Person) -> tuple[Work, bool]:
    candidates = Work.objects.filter(is_archived=False, title__iexact=record['title'])
    work = next((candidate for candidate in candidates if candidate.authors.filter(pk=person.pk).exists()), None)
    if work:
        return work, True
    work = Work.objects.create(title=record['title'], form=record['form'], field='literature', original_year=record['original_year'],
                               original_language=record['language'], countries=[record['tradition']],
                               description=f"Rank {record['position']} in the owner-supplied Classical Education Top 250. {record['rationale']}")
    work.authors.add(person)
    return work, False


def catalog(dry_run: bool) -> None:
    records = json.loads((ROOT / 'research' / TARGET / 'owner-chat-candidates-2026-09-14.json').read_text())
    if dry_run:
        print(f'{TARGET}: would reconcile {len(records)} works')
        return
    catalog_rows, selection = [], []
    with transaction.atomic():
        for record in records:
            person = resolve_person(record['attribution'], record['tradition'])
            work, reused = resolve_work(record, person)
            catalog_rows.append({**record, 'item_id': work.pk, 'reused_existing_work': reused})
            selection.append({
                'key': record['key'], 'item_id': work.pk, 'source_ids': record['refs'],
                'standing': f"Position {record['position']} in the owner-supplied Classical Education Top 250. {record['rationale']}",
                'reading': record['beginner_start'] or record['rationale'],
                'caveat': ' '.join(part for part in [record['coverage'], record['reading_language'], record['original_language_study']] if part) or 'See the preserved report for source, translation and scope limitations.',
                'metadata_status': 'edition_and_media_pending', 'source_positions': [],
            })
        ranking = Ranking.objects.select_for_update().get(slug=TARGET)
        if ranking.revision != 1 or ranking.entries.filter(is_archived=False).exists():
            raise ValueError('The reserved Classical education target is no longer the expected empty revision-1 placeholder.')
        ensure_revision(ranking)
        ranking.target_size = 250
        ranking.description = 'A research-led Top 250 of Greek and Roman literature, history, philosophy, rhetoric, science, law and later classical reception. Separate from the private Paideia syllabus.'
        ranking.scope = {**ranking.scope, 'forms': ['book', 'collection', 'essay', 'poem', 'play'], 'report_intake': {'run': RUN, 'method': 'Owner-supplied Classical Education Top 250 structured synthesis; report order retained with source-status limits.'}}
        ranking.save(update_fields=['target_size', 'description', 'scope', 'updated_at'])
    target_dir = ROOT / 'research' / TARGET
    write_json(target_dir / 'owner-chat-catalog-2026-09-14.json', {'schema_version': 1, 'works': catalog_rows})
    write_json(target_dir / 'owner-chat-selection-2026-09-14.json', {
        'target': TARGET, 'expected_revision': 1, 'allow_expansion': True, 'version': 'owner-chat-classical-education-top-250-2026-09-14', 'published_on': ACCESS_DATE,
        'allow_pending_metadata': True, 'reviewed_exclusions': [],
        'notice': 'Owner-supplied Classical Education Top 250. The structured source ledger, access classifications, language route and starter-reading notes are retained; no personal numerical scores are set.',
        'method': 'Owner-supplied Top 250 synthesis across Greek and Roman primary works and selected later reception. The report’s merit order is retained in both views pending a separately reasoned reading-value order.',
        'entries': selection,
        'orders': {
            'standing': {'label': 'Educational and literary value', 'description': 'The supplied report’s Top 250 merit order.', 'keys': [entry['key'] for entry in selection]},
            'reading': {'label': 'Beginner route', 'description': 'The report supplies starter guidance but no separate full reading-value ordering; this view retains its merit order.', 'keys': [entry['key'] for entry in selection]},
        },
    })
    print(f'{TARGET}: reconciled {len(selection)} works and prepared revision-2 selection')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['prepare', 'catalog'])
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    (prepare if args.phase == 'prepare' else catalog)(args.dry_run)


if __name__ == '__main__':
    main()
