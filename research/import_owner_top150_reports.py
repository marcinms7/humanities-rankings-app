#!/usr/bin/env python3
"""Normalize and publish four owner-supplied Top 150 research reports.

The reports remain the primary handoff.  This utility deliberately records the
report's stated consultation/access status instead of pretending that this
importer personally re-opened every linked source.  It is idempotent at the
target and report-hash level, preserves the original text and uses the normal
evidence importer/publishing command for database writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.config.settings')
import django
django.setup()

from django.db import transaction

from backend.core.models import Person, Ranking, Work


ROOT = PROJECT_ROOT
ATTACHMENTS = Path('/Users/marcinswierczewski/.codex/attachments')
RUN = '2026-09-14-owner-chat-attachments'
ACCESS_DATE = '2026-09-14'


@dataclass(frozen=True)
class Report:
    slug: str
    title: str
    domain: str
    filename: str
    prefix: str
    description: str
    method: str

    @property
    def source(self) -> Path:
        return ATTACHMENTS / self.filename / 'pasted-text.txt'


REPORTS = (
    Report('books-beautifully-written-all-time', 'Most beautifully written books · All time', 'literature',
           'd139fffb-c697-4ce0-9c1e-fdf1597b4105', 'BEAUTY',
           'A 150-work editorial synthesis focused on prose achievement, with source-level access limits retained from the owner-supplied report.',
           'Owner-supplied global prose-achievement synthesis. Its published order is retained as an editorial comparison, not a personal numerical score.'),
    Report('science-books-all-time', 'Science books · All time', 'nonfiction',
           '7c9bf4e7-3319-4fd8-9ad0-27d75e574bfe', 'SCIENCE',
           'A global Top 150 of science books, including historical and contemporary explanatory works; scientific and edition caveats are retained per entry.',
           'Owner-supplied evidence-informed global science-books synthesis. The report distinguishes historical importance, readability and current scientific limitations.'),
    Report('books-biography-autobiography-all-time', 'Biography & autobiography · All time', 'nonfiction',
           'beb0e319-d8fa-44d0-bbb3-952e1f07caa4', 'LIFE',
           'A 150-work global life-writing ranking spanning biography, autobiography, memoir, diaries, correspondence and collective biography.',
           'Owner-supplied global life-writing synthesis. The report retains distinctions among biography, memoir, edited diary, correspondence and collaborative testimony.'),
    Report('books-horror-all-time', 'Horror books · All time', 'literature',
           '9fe2e41e-e0b2-4fbe-8b8d-fc9993b691c3', 'HORROR',
           'A global Top 150 of horror novels, novellas and single-author collections, with genre-boundary and content caveats retained.',
           'Owner-supplied global horror synthesis. The order is editorial and evidence-informed; it is not a numerical meta-analysis or a personal score.'),
    Report('books-fantasy-all-time', 'Fantasy books · All time', 'literature',
           'f34c8c03-1530-4dad-abf0-74ae21e4fd00', 'FANTASY',
           'A global Top 150 of fantasy novels, novellas, collections and explicitly bounded sequences, with scope and translation caveats retained.',
           'Owner-supplied global fantasy synthesis. The supplied order is an editorial comparison, not a numerical meta-analysis or a personal score.'),
    Report('books-science-fiction-all-time', 'Science fiction · All time', 'literature',
           '5270371a-aed9-478d-bb16-d4eb7b6fe1ae', 'SF',
           'A global Top 150 of science-fiction novels, novellas, collections and explicitly bounded connected sequences, with genre-boundary notes retained.',
           'Owner-supplied global science-fiction synthesis. The supplied order is an argued editorial ranking, not a numerical meta-analysis or a personal score.'),
)


def norm(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', value.casefold())


def first_year(value: str) -> int | None:
    bce = re.search(r'(?i)(\d{1,4})\s*(?:bce|bc)', value)
    if bce:
        return -int(bce.group(1))
    modern = re.search(r'(?<!\d)(1[0-9]{3}|20[0-9]{2})(?!\d)', value)
    return int(modern.group(1)) if modern else None


def field(block: str, *labels: str) -> str:
    for label in labels:
        match = re.search(rf'(?im)^{re.escape(label)}\s*:\s*(.+)$', block)
        if match:
            return match.group(1).strip()
    return ''


def source_family(kind: str, title: str, url: str) -> str:
    value = f'{kind} {title} {url}'.casefold()
    if any(part in value for part in ('reddit', 'goodreads', 'storygraph', 'forum', 'douban', 'senscritique', 'reader poll', 'community')):
        return 'reader_community'
    if any(part in value for part in ('award', 'prize', 'university', 'museum', 'library', 'archive', 'society', 'institution')):
        return 'academic_or_institutional'
    if any(part in value for part in ('publisher', 'bookseller', 'catalogue', 'catalog', 'bibliographic')):
        return 'publisher_or_bibliographic'
    if any(part in value for part in ('scholarly', 'academic', 'journal', 'theor', 'history')):
        return 'scholarly_or_historical'
    if any(part in value for part in ('wikipedia', 'encyclopedia', 'bibliography')):
        return 'tertiary_reference'
    return 'editorial_or_specialist'


def source_cutoff(text: str, start: int) -> int:
    tail = text[start:]
    markers = re.search(r'(?im)^\s*(?:REGISTERED RECORDS NOT COUNTED|EXCLUDED RECORDS|EXCLUDED SOURCE|UNREAD OR INSUFFICIENTLY CONSULTED LEADS|UNREAD /|UNREAD LEADS|SELECTED UNREAD LEADS|DUPLICATES,|UNCOUTED|UNCOUNTED)', tail)
    return start + markers.start() if markers else len(text)


def parse_sources(report: Report, text: str) -> list[dict]:
    heading = re.search(r'(?im)^\s*(?:FULL(?: LINKED| CONSULTED)? SOURCE REGISTER(?:\s*—.*)?|FULL LINKED REGISTER.*|SOURCE REGISTER AND DEPENDENCY AUDIT|SOURCE DEPENDENCY AND DUPLICATION AUDIT)\s*$', text)
    if not heading:
        raise ValueError(f'{report.slug}: source-register heading not found')
    start, end = heading.end(), source_cutoff(text, heading.end())
    segment = text[start:end]
    records: list[dict] = []
    pattern = re.compile(r'(?m)^\s*(?:\[S(\d{3})\]|S(\d{3})(?:\s+\[[A-Z]\])?)\s+(.+?)\s*$')
    matches = list(pattern.finditer(segment))
    if not matches:
        raise ValueError(f'{report.slug}: no bracketed source records found')
    for index, match in enumerate(matches):
        block = segment[match.end(): matches[index + 1].start() if index + 1 < len(matches) else len(segment)]
        url_match = re.search(r'(?im)^(?:Direct URL|URL)\s*:\s*(https?://\S+)', block)
        if not url_match:
            continue
        raw_id, title = match.group(1) or match.group(2), match.group(3).lstrip('| ').strip()
        url = url_match.group(1).rstrip(').,;')
        kind = field(block, 'Type', 'Source type')
        use = field(block, 'Consulted/use', 'Read and use', 'Use', 'Read/use', 'Consulted')
        limits = field(block, 'Limit / dependency', 'Limit/dependency', 'Limit', 'Limitations', 'Dependency')
        if not use:
            use = 'The owner-supplied report records this source as consulted for its stated relevance; see the preserved report for the full note.'
        host = urlsplit(url).netloc.removeprefix('www.') or 'reported-source'
        records.append({
            'source_id': f'{report.prefix}-S{raw_id}',
            'underlying_source_id': f'{report.slug}:report-source:S{raw_id}',
            'title': title[:500],
            'author': None,
            'publisher': host,
            'publisher_group': host,
            'canonical_url': url,
            'access_url': url,
            'publication_date': None,
            'accessed_at': ACCESS_DATE,
            'source_family': source_family(kind, title, url),
            'domain_or_platform': host,
            'language': 'as reported',
            'access_level': 'relevant_excerpt',
            'depends_on_source_ids': [],
            'dependency_note': 'Dependencies and duplicate relationships are retained in the preserved owner-supplied report.',
            'target_ids': [report.slug],
            'relevance_by_target': {report.slug: 'The owner-supplied report identifies this source as evidence for this exact ranking; the report’s use and access limits are retained.'},
            'evidence_notes': f'Reported consultation: {use}',
            'location': None,
            'evidence_role': 'owner_supplied_report_evidence',
            'candidates_or_claims_supported': [],
            'disagreement_or_limitations': (limits or 'Access, dependence and scope limitations are reported in the preserved supplied report; this importer did not independently re-open the source.')[:4000],
            'count_eligible': True,
            'exclusion_reason': None,
            'consultation_batch': f'research/incoming/{report.slug}/{RUN}/report.txt',
            'owner_supplied': True,
            'report_source_id': f'S{raw_id}',
            'report_type': kind or 'Not separately classified in the report extract.',
        })
    ids = {record['source_id'] for record in records}
    if len(ids) != len(records):
        raise ValueError(f'{report.slug}: duplicate source IDs in parsed register')
    return records


def parse_entries(report: Report, text: str, known_sources: set[str]) -> list[dict]:
    ranking_start = re.search(r'(?im)^(?:(?:THE )?RANKED TOP 150|RANKING:\s*TOP 150)\s*$', text)
    if not ranking_start:
        raise ValueError(f'{report.slug}: ranking heading not found')
    end_mark = re.search(r'(?im)^\s*(?:FULL(?: LINKED| CONSULTED)? SOURCE REGISTER|FULL LINKED REGISTER|SOURCE REGISTER|SOURCE DEPENDENCY AND DUPLICATION AUDIT)\b', text[ranking_start.end():])
    if not end_mark:
        raise ValueError(f'{report.slug}: ranking end not found')
    segment = text[ranking_start.end(): ranking_start.end() + end_mark.start()]
    pattern = re.compile(r'(?m)^\s*(\d{1,3})\.\s+(.+?)\s*$')
    matches = list(pattern.finditer(segment))
    entries: list[dict] = []
    for index, match in enumerate(matches):
        position = int(match.group(1))
        if not 1 <= position <= 150:
            continue
        block = segment[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(segment)]
        heading = match.group(2).strip()
        author = field(block, 'Author')
        title = heading
        if not author and ' — ' in heading:
            author, title = (part.strip() for part in heading.split(' — ', 1))
        if not author:
            raise ValueError(f'{report.slug}: no author resolved for rank {position}: {heading}')
        refs = [f'{report.prefix}-S{number}' for number in re.findall(r'\bS(\d{3})\b', field(block, 'Supporting sources', 'Supporting source IDs', 'Sources'))]
        refs = list(dict.fromkeys(ref for ref in refs if ref in known_sources))
        if not refs:
            raise ValueError(f'{report.slug}: no counted source mapping for rank {position}: {title}')
        lang = field(block, 'Original language') or 'Unspecified in supplied report'
        published = field(block, 'Publication', 'First publication', 'First publication/composition', 'Publication / composition')
        form_text = field(block, 'Form', 'Form and scope') or 'Book'
        context = field(block, 'Tradition/context', 'Tradition / context', 'Tradition/classification', 'Tradition / principal setting', 'Tradition', 'Context')
        rationale = field(block, 'Prose qualities', 'Rationale')
        caveat = field(block, 'Translation/edition note', 'Important scientific and edition caveats', 'Boundary / edition note', 'Boundary/edition note', 'Content notes')
        if not rationale:
            raise ValueError(f'{report.slug}: no rationale at rank {position}: {title}')
        lower_form = form_text.casefold()
        form = 'play' if 'play' in lower_form or 'drama' in lower_form else 'essay' if 'essay' in lower_form else 'short_story' if 'short stor' in lower_form else 'collection' if any(token in lower_form for token in ('collection', 'diar', 'correspondence')) else 'book'
        entries.append({
            'position': position,
            'title': title,
            'attribution': author,
            'date': published,
            'form_reported': form_text,
            'form': form,
            'tradition': context or 'Unspecified in supplied report',
            'language': lang,
            'rationale': rationale,
            'context': caveat,
            'refs': refs,
            'original_year': first_year(published),
        })
    entries.sort(key=lambda entry: entry['position'])
    if [entry['position'] for entry in entries] != list(range(1, 151)):
        raise ValueError(f'{report.slug}: expected ranks 1–150, found {len(entries)} records')
    return entries


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def prepare(report: Report, dry_run: bool) -> tuple[list[dict], list[dict]]:
    raw = report.source.read_bytes()
    text = raw.decode('utf-8')
    digest = hashlib.sha256(raw).hexdigest()
    sources = parse_sources(report, text)
    entries = parse_entries(report, text, {source['source_id'] for source in sources})
    if dry_run:
        print(f'{report.slug}: {len(entries)} entries; {len(sources)} reported consulted sources; sha256={digest}')
        return sources, entries
    incoming = ROOT / 'research' / 'incoming' / report.slug / RUN
    incoming.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(report.source, incoming / 'report.txt')
    (incoming / 'RECEIPT.md').write_text(
        f'# Owner chat attachment receipt\n\n- Received: {ACCESS_DATE}\n- Requested action: import ranking entries and target-local sources into Marginalia\n- Original attachment: `{report.source}`\n- SHA-256: `{digest}`\n- Parsed: 150 ranking entries and {len(sources)} report-designated consulted source records.\n- Caveat: reported source consultation/access is preserved from the supplied report; it was not independently rechecked during this file-driven intake.\n'
    )
    ledger = {'target_id': report.slug, 'minimum_eligible_sources': 50, 'criteria_version': None, 'ranking_entries': [], 'sources': sources,
              'status': 'owner_report_imported_pending_publication', 'saved_at': ACCESS_DATE}
    target_dir = ROOT / 'research' / report.slug
    write_json(target_dir / 'sources.json', ledger)
    write_json(target_dir / 'owner-chat-candidates-2026-09-14.json', entries)
    (target_dir / 'RESEARCH.md').write_text(
        f'# {report.title}\n\nOwner-supplied UTF-8 report received on {ACCESS_DATE}; original preserved at `research/incoming/{report.slug}/{RUN}/report.txt` (SHA-256 `{digest}`).\n\nParsed **150 ranked works** and **{len(sources)} report-designated consulted source records**. The report’s own access, dependency and limitation notes are retained per source. This is file-driven intake: source pages were not independently revisited in this import. Personal criteria, scores and overrides remain unset.\n\nNext: import the ledger into the active target, reconcile the 150 catalog identities, and publish the supplied editorial order in a revisioned selection.\n'
    )
    return sources, entries


def ensure_target(report: Report, dry_run: bool) -> None:
    if dry_run:
        return
    defaults = dict(title=report.title, description=report.description, domain=report.domain, item_type='work', presentation='ranked',
                    origin='curated', owner=None, target_size=150, status='awaiting_research', criteria=[], source_url='', publisher='',
                    scope={'forms': ['book', 'collection', 'essay', 'short_story', 'play'], 'report_intake': {'run': RUN, 'method': report.method}})
    ranking, created = Ranking.objects.get_or_create(slug=report.slug, defaults=defaults)
    if not created and (ranking.origin != 'curated' or ranking.owner_id or ranking.is_archived):
        raise ValueError(f'{report.slug}: existing ranking is incompatible with a shared researched import')
    if created:
        print(f'{report.slug}: created shared target {ranking.pk}')
    else:
        print(f'{report.slug}: existing target {ranking.pk} retained')


def resolve_catalog(report: Report, entries: list[dict]) -> tuple[list[dict], list[dict]]:
    catalog, selection = [], []
    with transaction.atomic():
        for entry in entries:
            author_name = entry['attribution'].strip()
            person = Person.objects.filter(is_archived=False, name__iexact=author_name).first()
            if person is None:
                person = Person.objects.create(name=author_name, biography='', countries=[entry['tradition']], source_url='')
            candidates = Work.objects.filter(is_archived=False, title__iexact=entry['title'])
            work = next((candidate for candidate in candidates if candidate.authors.filter(pk=person.pk).exists()), None)
            reused_existing_work = work is not None
            if work is None:
                work = Work.objects.create(title=entry['title'], form=entry['form'], field='nonfiction' if report.domain == 'nonfiction' else 'literature',
                                           original_year=entry['original_year'], original_language=entry['language'], countries=[entry['tradition']],
                                           description=f"Position {entry['position']} in the owner-supplied {report.title} synthesis. {entry['rationale']}")
                work.authors.add(person)
            catalog.append({'key': f'{report.slug}-owner-{entry["position"]:03d}', 'item_id': work.pk, 'reused_existing_work': reused_existing_work, **entry})
            selection.append({
                'key': f'{report.slug}-owner-{entry["position"]:03d}', 'item_id': work.pk, 'source_ids': entry['refs'],
                'standing': f"Position {entry['position']} in the owner-supplied {report.title} synthesis. {entry['rationale']}",
                'reading': entry['rationale'],
                'caveat': entry['context'] or 'The supplied report retains source-access, translation, scope and ranking-order limitations.',
                'metadata_status': 'edition_and_media_pending', 'source_positions': []
            })
    return catalog, selection


def catalog_and_selection(report: Report, dry_run: bool) -> None:
    entries = json.loads((ROOT / 'research' / report.slug / 'owner-chat-candidates-2026-09-14.json').read_text())
    if dry_run:
        print(f'{report.slug}: would reconcile {len(entries)} catalog works')
        return
    catalog, selection = resolve_catalog(report, entries)
    target_dir = ROOT / 'research' / report.slug
    write_json(target_dir / 'owner-chat-catalog-2026-09-14.json', {'schema_version': 1, 'works': catalog})
    payload = {
        'target': report.slug, 'expected_revision': 1, 'allow_expansion': True, 'version': f'owner-chat-{report.slug}-top-150-2026-09-14', 'published_on': ACCESS_DATE,
        'allow_pending_metadata': True, 'reviewed_exclusions': [],
        'notice': f'Owner-supplied {report.title} Top 150. The detailed source register, source-access limits and report caveats are retained; no personal numerical scores are set.',
        'method': report.method,
        'entries': selection,
        'orders': {
            'standing': {'label': 'Critical standing', 'description': 'The supplied report’s editorial Top 150 order.', 'keys': [item['key'] for item in selection]},
            'reading': {'label': 'Reading value', 'description': 'The supplied report did not provide a separately ordered reading-value list, so this view retains its editorial order.', 'keys': [item['key'] for item in selection]},
        },
    }
    write_json(target_dir / 'owner-chat-selection-2026-09-14.json', payload)
    print(f'{report.slug}: reconciled {len(selection)} works and prepared revision-2 selection')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['prepare', 'catalog'])
    parser.add_argument('--target', action='append', choices=[report.slug for report in REPORTS], help='Limit processing to one or more stable target slugs.')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    reports = [report for report in REPORTS if not args.target or report.slug in args.target]
    for report in reports:
        if args.phase == 'prepare':
            prepare(report, args.dry_run)
            ensure_target(report, args.dry_run)
        else:
            catalog_and_selection(report, args.dry_run)


if __name__ == '__main__':
    main()
