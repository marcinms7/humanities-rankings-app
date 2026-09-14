#!/usr/bin/env python3
"""Normalize and safely publish the owner's global cross-form literary ranking."""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.config.settings')

import django

django.setup()

from django.db import transaction
from backend.core.models import Ranking, Work


TARGET = 'other-works-all-time'
ATTACHMENT = Path('/Users/marcinswierczewski/.codex/attachments/050c5e1a-8257-4374-a525-4d3dbfd8af03/pasted-text.txt')
INCOMING = ROOT / 'research/incoming' / TARGET / '2026-09-14-owner-chat-attachment' / 'report.txt'
OUTPUT = ROOT / 'research' / TARGET
DATE = '2026-09-14'


def compact(value):
    return ' '.join(value.split())


def parse_entries(text):
    start = text.index('THE RANKING: 1–250')
    end = text.index('COMPLETE SOURCE BIBLIOGRAPHY', start)
    section = text[start:end]
    pattern = re.compile(
        r'(?ms)^(\d{3})\.\s+(.+?)\n'
        r'Author / attribution:\s*(.+?)\n'
        r'Date:\s*(.+?)\n'
        r'Category:\s*([A-Z])\s*\|\s*Form:\s*(.+?)\n'
        r'Literary tradition / language:\s*(.+?)\n'
        r'Why it matters:\s*(.+?)\n'
        r'Evidence:\s*(.+?)(?=\n\n\d{3}\.\s+|\Z)'
    )
    entries = []
    for match in pattern.finditer(section):
        entries.append({
            'position': int(match.group(1)), 'title': match.group(2).strip(),
            'attribution': match.group(3).strip(), 'date': match.group(4).strip(),
            'category': match.group(5), 'form_reported': match.group(6).strip(),
            'tradition_language': match.group(7).strip(), 'rationale': compact(match.group(8)),
            'source_refs': re.findall(r'S\d{3}', match.group(9)),
        })
    if [entry['position'] for entry in entries] != list(range(1, 251)):
        raise ValueError(f'Expected positions 1–250; parsed {len(entries)} entries.')
    if any(not entry['source_refs'] for entry in entries):
        raise ValueError('Every entry requires at least one report source reference.')
    return entries


def source_family(source_type, title):
    label = f'{source_type} {title}'.casefold()
    if any(term in label for term in ('scholarly', 'research article', 'university', 'library', 'museum', 'reference', 'encyclopedic', 'academic')):
        return 'academic_or_institutional'
    if any(term in label for term in ('reader', 'forum', 'reddit', 'goodreads', 'douban', 'community')):
        return 'reader_community'
    return 'editorial_or_specialist'


def access_level(value):
    value = value.casefold()
    if 'direct page' in value or 'retrieved page' in value:
        return 'full_relevant_content'
    if 'excerpt' in value or 'abstract' in value or 'indexed' in value:
        return 'relevant_excerpt'
    return 'summary_only'


def parse_sources(text):
    section = text[text.index('COMPLETE SOURCE BIBLIOGRAPHY'):]
    headers = list(re.finditer(r'(?m)^\[S(\d{3})\]\s+(.+?)\s*$', section))
    records, urls = [], set()
    for index, header in enumerate(headers):
        chunk = section[header.end():headers[index + 1].start() if index + 1 < len(headers) else len(section)]
        number, title = header.group(1), header.group(2).strip()
        url_match = re.search(r'(?m)^https?://\S+\s*$', chunk)
        if not url_match:
            raise ValueError(f'S{number}: no direct URL.')
        url = url_match.group(0).strip()
        canonical = url.rstrip('/')
        if canonical in urls:
            raise ValueError(f'S{number}: duplicate primary URL in a claimed distinct-source register.')
        urls.add(canonical)
        details = re.search(r'(?m)^Host:\s*(.+?)\s*\|\s*Type:\s*(.+?)\s*\|\s*Language:\s*(.+?)\s*$', chunk)
        used = re.search(r'(?m)^Used for:\s*(.+?)\s*\|\s*Access:\s*(.+?)\s*$', chunk)
        host, source_type, language = details.groups() if details else (urlparse(url).netloc, '', '')
        use, access = used.groups() if used else ('Owner-supplied source-register context.', '')
        source_id = f'LITWORKS-S{number}'
        records.append({
            'source_id': source_id,
            'underlying_source_id': 'url:' + hashlib.sha256(canonical.encode()).hexdigest()[:24],
            'title': title, 'canonical_url': url, 'source_family': source_family(source_type, title),
            'publisher': host, 'access_level': access_level(access), 'accessed_at': DATE,
            'count_eligible': True, 'target_ids': [TARGET],
            'relevance_by_target': {TARGET: 'Owner-supplied global cross-form literary-importance synthesis reports this target-local source as consulted for comparative methodology, interpretation, reception, literary history, or bibliographic context.'},
            'evidence_notes': compact(use),
            'disagreement_or_limitations': 'Consultation and access are reported by the owner-supplied bibliography and were not independently reread source by source during intake. A source may support context, history or reception rather than the exact editorial position.',
            'depends_on_source_ids': [], 'report_source_number': f'S{number}',
            'report_host': host, 'report_type': source_type, 'report_language': language, 'report_access': access,
        })
    expected = {f'S{number:03d}' for number in range(1, 612)}
    if len(records) != 611 or {record['report_source_number'] for record in records} != expected:
        raise ValueError(f'Expected S001–S611 exactly once; parsed {len(records)}.')
    return records


def parse_year(value):
    match = re.search(r'(?<!\d)(\d{3,4})(?!\d)', value)
    if not match:
        return None
    year = int(match.group(1))
    return -year if 'BCE' in value[:match.end() + 12] else year


def author_names(attribution):
    lower = attribution.casefold()
    if lower.startswith(('multiple ', 'anonymous', 'traditionally understood', 'og huz', 'oghuz ', 'multiple buddhist')):
        return []
    if 'anonymous' in lower or ('multiple' in lower and 'authors' in lower):
        return []
    raw = re.sub(r'\s*\([^)]*(?:traditional|disputed|attribution)[^)]*\)', '', attribution, flags=re.I)
    raw = re.split(r';\s*(?:multiple|completion|layered|associated|traditional|anonymous|oral|later|and commentators)', raw, maxsplit=1, flags=re.I)[0]
    raw = re.sub(r'^Traditionally attributed to\s+', '', raw, flags=re.I)
    raw = raw.strip(' ;,.')
    if not raw or raw.casefold().startswith(('the ', 'multiple', 'anonymous')):
        return []
    return [name.strip() for name in re.split(r'\s+(?:and|&)\s+|\s*;\s*', raw) if name.strip()]


def tradition_and_language(value):
    tradition, separator, language = value.partition(';')
    return tradition.strip(), language.strip() if separator else ''


def work_form(category, reported):
    if category == 'P':
        return 'poem' if 'anthology' not in reported.casefold() and 'poems' not in reported.casefold() else 'collection'
    if category == 'D':
        return 'play'
    if category == 'S':
        return 'short_story' if 'collection' not in reported.casefold() and 'tales' not in reported.casefold() else 'collection'
    if category in {'M', 'L'} or any(word in reported.casefold() for word in ('anthology', 'collection', 'corpus', 'tales', 'fragments')):
        return 'collection'
    if category == 'E' and any(word in reported.casefold() for word in ('essay', 'criticism', 'prose', 'dialogue', 'sayings')):
        return 'essay'
    return 'book'


def existing_authors_for_unique_title(title):
    matches = list(Work.objects.filter(title__iexact=title, is_archived=False).prefetch_related('authors'))
    if len(matches) == 1 and matches[0].authors.exists():
        return [person.name for person in matches[0].authors.all()]
    return None


def build_catalog(entries, sources):
    source_by_ref = {source['report_source_number']: source for source in sources}
    catalog, unresolved = [], []
    for entry in entries:
        if any(ref not in source_by_ref for ref in entry['source_refs']):
            raise ValueError(f"Rank {entry['position']}: unknown source reference.")
        authors = existing_authors_for_unique_title(entry['title']) or author_names(entry['attribution'])
        tradition, language = tradition_and_language(entry['tradition_language'])
        base = {
            'key': f'litworks-{entry["position"]:03d}', 'title': entry['title'], 'authors': authors,
            'form': work_form(entry['category'], entry['form_reported']), 'field': 'literature',
            'original_year': parse_year(entry['date']), 'original_language': language,
            'countries': [tradition] if tradition else [],
            'description': f"Rank {entry['position']} in the owner-supplied global cross-form literary-importance synthesis. Attribution: {entry['attribution']}. Date: {entry['date']}. Category/form: {entry['category']} / {entry['form_reported']}. {entry['rationale']}",
            'work_source_url': source_by_ref[entry['source_refs'][0]]['canonical_url'],
            'evidence_ids': [source_by_ref[ref]['source_id'] for ref in entry['source_refs']],
            'edition': None, 'english_availability_note': 'Specific edition, translation and media remain to be verified.',
        }
        if authors:
            catalog.append(base)
        else:
            unresolved.append({**base, 'attribution': entry['attribution'], 'reason': 'Collective, anonymous or non-authorial attribution retained without creating a fictitious Person record.'})
    return catalog, unresolved


def import_unattributed(unresolved):
    receipt_path = OUTPUT / 'owner-paste-unattributed-catalog-import-receipt.json'
    results = []
    with transaction.atomic():
        for record in unresolved:
            matches = list(Work.objects.filter(title__iexact=record['title'], is_archived=False, authors__isnull=True))
            if len(matches) > 1:
                raise ValueError(f"Ambiguous authorless work: {record['title']}")
            work = matches[0] if matches else Work(
                title=record['title'], form=record['form'], field=record['field'], original_year=record['original_year'],
                original_language=record['original_language'], countries=record['countries'], description=record['description'],
            )
            created = not bool(matches)
            if created:
                work.full_clean()
                work.save()
            results.append({'key': record['key'], 'work_id': work.pk, 'created_work': created, 'attribution': record['attribution']})
    receipt_path.write_text(json.dumps({'records': results}, ensure_ascii=False, indent=2) + '\n')
    return results


def build_selection(entries, sources, catalog, unresolved):
    source_by_ref = {source['report_source_number']: source for source in sources}
    catalog_by_key = {record['key']: record for record in catalog}
    unresolved_by_key = {record['key']: record for record in unresolved}
    selection, keys = [], []
    for entry in entries:
        key = f'litworks-{entry["position"]:03d}'
        record = catalog_by_key.get(key) or unresolved_by_key[key]
        if record['authors']:
            expected = {name.casefold() for name in record['authors']}
            matches = [work for work in Work.objects.filter(title__iexact=record['title'], is_archived=False).prefetch_related('authors') if {person.name.casefold() for person in work.authors.all()} == expected]
        else:
            matches = list(Work.objects.filter(title__iexact=record['title'], is_archived=False, authors__isnull=True))
        if len(matches) != 1:
            raise ValueError(f'{key}: expected one catalog work, found {[work.pk for work in matches]}.')
        source_ids = [source_by_ref[ref]['source_id'] for ref in entry['source_refs']]
        selection.append({
            'key': key, 'item_id': matches[0].pk, 'source_ids': source_ids,
            'standing': f"Position {entry['position']} in the owner-supplied global cross-form literary-importance synthesis. {entry['rationale']}",
            'reading': 'No separate reading-value order was supplied; this view retains the report’s historical-literary-importance order.',
            'caveat': 'The bibliography supports literary history, criticism, reception or bibliographic context, not an exact consensus rank. Reported source access is retained; exact editions, media and some collective attributions remain pending.',
            'metadata_status': 'edition_and_media_pending', 'source_positions': [],
        })
        keys.append(key)
    ranking = Ranking.objects.get(slug=TARGET)
    return {
        'target': TARGET, 'expected_revision': ranking.revision,
        'version': 'owner-paste-global-cross-form-literary-importance-2026-09-14', 'published_on': DATE,
        'allow_pending_metadata': True, 'reviewed_exclusions': [],
        'notice': 'Initial owner-supplied global cross-form literary-importance synthesis. The bibliography preserves reported access and source-role limits; no personal numerical scores are set.',
        'method': 'Owner-supplied editorial synthesis of 611 distinct linked source records across literary forms and traditions. The report’s historical-literary-importance order is retained; the reading-value view intentionally mirrors it pending a separately reasoned order.',
        'entries': selection,
        'orders': {
            'standing': {'label': 'Historical literary importance', 'description': 'The report’s supplied global cross-form order.', 'keys': keys},
            'reading': {'label': 'Reported order (reading-value view pending)', 'description': 'No separate reading-value ordering was supplied.', 'keys': keys},
        },
    }


def ensure_target_scope():
    ranking = Ranking.objects.get(slug=TARGET, origin='curated', owner__isnull=True, is_archived=False)
    if ranking.entries.filter(is_archived=False).exists() or ranking.sources.filter(is_archived=False).exists():
        raise ValueError('Target is no longer empty; scope changes need explicit reconciliation.')
    ranking.scope = {
        **ranking.scope,
        'forms': ['book', 'collection', 'essay', 'short_story', 'poem', 'play'],
        'ranking_purpose': 'historical_literary_importance',
        'cross_form': True,
        'allow_unresolved_attribution': True,
    }
    ranking.description = 'A global, cross-form ranking of literary works by historical literary importance: influence on later writing, literary forms, interpretive traditions and cultural imagination.'
    ranking.full_clean()
    ranking.save(update_fields=['scope', 'description', 'updated_at'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply-target-scope', action='store_true')
    parser.add_argument('--import-unattributed', action='store_true')
    parser.add_argument('--build-selection', action='store_true')
    args = parser.parse_args()
    if not ATTACHMENT.exists():
        raise FileNotFoundError(f'Attachment unavailable: {ATTACHMENT}')
    if args.apply_target_scope:
        ensure_target_scope()
    INCOMING.parent.mkdir(parents=True, exist_ok=True)
    if not INCOMING.exists():
        shutil.copy2(ATTACHMENT, INCOMING)
    text = INCOMING.read_text()
    digest = hashlib.sha256(INCOMING.read_bytes()).hexdigest()
    entries, sources = parse_entries(text), parse_sources(text)
    catalog, unresolved = build_catalog(entries, sources)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    ledger = json.dumps({'target_id': TARGET, 'ranking_entries': [], 'sources': sources}, ensure_ascii=False, indent=2) + '\n'
    (OUTPUT / 'sources.json').write_text(ledger)
    (OUTPUT / 'owner-paste-candidates.json').write_text(json.dumps({'target_id': TARGET, 'source_report': str(INCOMING.relative_to(ROOT)), 'reported_source_count': len(sources), 'candidates': entries}, ensure_ascii=False, indent=2) + '\n')
    (OUTPUT / 'owner-paste-catalog.json').write_text(json.dumps({'schema_version': 1, 'allow_pending_editions': True, 'works': catalog}, ensure_ascii=False, indent=2) + '\n')
    (OUTPUT / 'owner-paste-unresolved-candidates.json').write_text(json.dumps(unresolved, ensure_ascii=False, indent=2) + '\n')
    (INCOMING.parent / 'RECEIPT.md').write_text(f'# Owner attachment receipt\n\n- Received: {DATE}\n- Requested action: import supplied cross-form ranking and sources into the app.\n- SHA-256: `{digest}`\n- Parsed: 250 ranking entries and 611 source records.\n- {len(unresolved)} collective/anonymous attributions retained without invented people.\n')
    if args.import_unattributed:
        import_unattributed(unresolved)
    if args.build_selection:
        (OUTPUT / 'owner-paste-selection.json').write_text(json.dumps(build_selection(entries, sources, catalog, unresolved), ensure_ascii=False, indent=2) + '\n')
    print(f'Parsed {len(entries)} entries, {len(sources)} sources, {len(catalog)} named catalog records and {len(unresolved)} unresolved attributions; SHA-256 {digest}.')


if __name__ == '__main__':
    main()
