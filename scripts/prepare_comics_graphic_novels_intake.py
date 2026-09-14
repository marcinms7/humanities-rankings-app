#!/usr/bin/env python3
"""Normalize the owner-supplied worldwide comics Top 250 for reviewed import.

This is deliberately file-driven: it preserves the supplied report first, then
emits an evidence ledger, candidate map, catalog batch and publication batch.
It never modifies an existing ranking, source or catalog record.
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.config.settings')
import django

django.setup()

from backend.core.models import Ranking, Work


TARGET = 'comics-graphic-novels-all-time'
ATTACHMENT = Path('/Users/marcinswierczewski/.codex/attachments/d2e79c58-834d-4d95-abc3-74733f435a29/pasted-text.txt')
INCOMING = ROOT / 'research/incoming' / TARGET / '2026-09-14-owner-chat-attachment' / 'report.txt'
OUTPUT = ROOT / 'research' / TARGET
DATE = '2026-09-14'


def target_values():
    return {
        'slug': TARGET,
        'title': 'Comics and graphic novels · All time',
        'description': (
            'A worldwide owner-supplied critical synthesis of comics, graphic novels, '
            'manga, manhwa, manhua, comic strips and wordless novels. Manga demographics '
            'are preserved as publication-context metadata, not a second merit ranking.'
        ),
        'domain': 'literature',
        'item_type': 'work',
        'presentation': 'ranked',
        'origin': 'curated',
        'is_public': True,
        'target_size': 250,
        'status': 'awaiting_research',
        'scope': {
            'forms': ['book', 'collection'],
            'media': ['comics', 'graphic_novels', 'manga', 'manhwa', 'manhua', 'comic_strips', 'wordless_novels'],
            'entry_unit': 'book, bounded story, coherent series, creator run, or classic strip corpus as stated per entry',
            'manga_category_index_preserved': True,
            'manga_categories_are': 'publication demographics/context, not genres, quality levels, or age ratings',
        },
    }


def ensure_target():
    existing = Ranking.objects.filter(slug=TARGET).first()
    if existing:
        if existing.origin != 'curated' or existing.owner_id or existing.is_archived:
            raise ValueError(f'{TARGET} exists but is not an active shared curated target.')
        return existing, False
    ranking = Ranking(**target_values())
    ranking.full_clean()
    ranking.save()
    return ranking, True


def compact(value):
    return ' '.join(value.split())


def parse_year(value):
    years = re.findall(r'(?<!\d)(\d{4})(?!\d)', value)
    return int(years[0]) if years else None


def split_creators(raw):
    """Keep named creators while excluding prose-source/production catch-alls."""
    raw = re.sub(r';\s*(?:based on|adapted from|with colours? by|continuation by).*$', '', raw, flags=re.I)
    raw = raw.replace(' and others', '')
    names = []
    for group in raw.split(';'):
        group = group.strip()
        if not group:
            continue
        # Comma-separated names appear only as a compact collaborator group in
        # this report; retain each named individual rather than a fake collective.
        parts = re.split(r',\s*|\s+and\s+', group)
        for part in parts:
            part = part.strip(' .')
            if part and not part.casefold().startswith(('various ', 'studio ', 'collective ')):
                names.append(part)
    return list(dict.fromkeys(names))


def family(source, title):
    label = f'{source} {title}'.casefold()
    if any(term in label for term in ('university', 'academic', 'scholarly', 'library', 'museum', 'award', 'prize', 'book / scholarly', 'encyclopedia')):
        return 'academic_or_institutional'
    if any(term in label for term in ('reddit', 'forum', 'community', 'goodreads', 'douban', 'reader', 'bedetheque')):
        return 'reader_community'
    return 'editorial_or_specialist'


def access_level(access):
    return {'P': 'full_relevant_content', 'E': 'relevant_excerpt', 'B': 'summary_only'}.get(access, 'summary_only')


def parse_entries(text):
    start = text.index('THE RANKING — 1 TO 250')
    end = text.index('MANGA CATEGORY INDEX', start)
    section = text[start:end]
    pattern = re.compile(
        r'(?ms)^(\d{3})\.\s+(.+?)\n'
        r'Creators:\s*(.+?)\n'
        r'Year/edition:\s*(.+?)\s*\|\s*Tradition:\s*(.+?)\s*\|\s*Form:\s*(.+?)\n'
        r'Genres/themes:\s*(.+?)\n'
        r'(?:Manga / Asian-comics publication context:\s*(.+?)\n)?'
        r'Scope:\s*(.+?)\n'
        r'Why here:\s*(.+?)\n'
        r'References:\s*(.+?)(?=\n\n\d{3}\.\s+|\Z)'
    )
    entries = []
    for match in pattern.finditer(section):
        refs = re.findall(r'S\d{3}', match.group(11))
        entries.append({
            'position': int(match.group(1)),
            'title': match.group(2).strip(),
            'creators_reported': match.group(3).strip(),
            'year_edition': match.group(4).strip(),
            'tradition': match.group(5).strip(),
            'form_reported': match.group(6).strip(),
            'genres': match.group(7).strip(),
            'manga_context': (match.group(8) or '').strip(),
            'scope': compact(match.group(9)),
            'rationale': compact(match.group(10)),
            'source_refs': refs,
        })
    if [entry['position'] for entry in entries] != list(range(1, 251)):
        raise ValueError(f'Expected ranks 1–250, parsed {len(entries)} entries.')
    if any(not entry['source_refs'] for entry in entries):
        raise ValueError('Every ranked entry must retain at least one source reference.')
    return entries


def field(chunk, label):
    match = re.search(rf'(?m)^{re.escape(label)}:\s*(.+?)\s*$', chunk)
    return match.group(1).strip() if match else ''


def parse_sources(text):
    section = text[text.index('FULL SOURCE BIBLIOGRAPHY'):]
    headers = list(re.finditer(r'(?m)^\[S(\d{3})\]\s+(.+?)\s*$', section))
    records, urls = [], set()
    for index, header in enumerate(headers):
        chunk = section[header.end():headers[index + 1].start() if index + 1 < len(headers) else len(section)]
        number, title = header.group(1), header.group(2).strip()
        url = field(chunk, 'URL')
        if not url.startswith(('https://', 'http://')):
            raise ValueError(f'S{number}: missing direct HTTP(S) URL.')
        canonical = url.rstrip('/')
        if canonical in urls:
            raise ValueError(f'S{number}: duplicate primary URL; reconcile before import.')
        urls.add(canonical)
        # The supplied bibliography uses one compact line, e.g.
        # "Source: example.org | Language: English | Access: P".
        source_line = field(chunk, 'Source')
        source = source_line.split('|', 1)[0].strip() or urlparse(url).netloc
        language_match = re.search(r'(?:^|\|)\s*Language:\s*([^|]+)', source_line)
        access_match = re.search(r'(?:^|\|)\s*Access:\s*([PEB])\b', source_line)
        language = language_match.group(1).strip() if language_match else field(chunk, 'Language')
        access = access_match.group(1) if access_match else field(chunk, 'Access')
        use = compact(field(chunk, 'Use'))
        continuation = field(chunk, 'Continuation URL (same reference)')
        source_id = f'COMICS-S{number}'
        records.append({
            'source_id': source_id,
            'underlying_source_id': 'url:' + hashlib.sha256(canonical.encode()).hexdigest()[:24],
            'title': title,
            'canonical_url': url,
            'source_family': family(source, title),
            'publisher': source,
            'access_level': access_level(access),
            'accessed_at': DATE,
            'count_eligible': True,
            'target_ids': [TARGET],
            'relevance_by_target': {TARGET: 'Owner-supplied worldwide comics and graphic-novels synthesis records this target-local source as consulted for comparison, criticism, reception, history, or bibliographic context.'},
            'evidence_notes': use or 'Owner-supplied source-register context for the worldwide comics and graphic-novels synthesis.',
            'disagreement_or_limitations': (
                'Access and consultation are reported by the owner-supplied bibliography and were not independently reread source by source during intake. '
                'The source may support context, history or reception rather than an exact final position.'
            ),
            'depends_on_source_ids': [],
            'report_source_number': f'S{number}',
            'language': language,
            'report_access': access,
            'report_use': use,
            'continuation_url_same_reference': continuation,
        })
    expected = {f'S{number:03d}' for number in range(1, 828)}
    if len(records) != 827 or {record['report_source_number'] for record in records} != expected:
        raise ValueError(f'Expected S001–S827 exactly once, parsed {len(records)} sources.')
    return records


def existing_authors_for_unique_title(title):
    matches = list(Work.objects.filter(title__iexact=title, is_archived=False).prefetch_related('authors'))
    if len(matches) == 1 and matches[0].authors.exists():
        return [person.name for person in matches[0].authors.all()]
    return None


def countries(tradition):
    return [part.strip() for part in re.split(r'[/;,]', tradition) if part.strip()]


def build_catalog(entries, sources):
    source_by_ref = {source['report_source_number']: source for source in sources}
    records = []
    for entry in entries:
        if any(ref not in source_by_ref for ref in entry['source_refs']):
            raise ValueError(f"Rank {entry['position']}: unknown source reference.")
        authors = existing_authors_for_unique_title(entry['title']) or split_creators(entry['creators_reported'])
        if not authors:
            raise ValueError(f"Rank {entry['position']}: no resolved named creator for {entry['title']}.")
        evidence_ids = [source_by_ref[ref]['source_id'] for ref in entry['source_refs']]
        provenance = source_by_ref[entry['source_refs'][0]]['canonical_url']
        records.append({
            'key': f'comics-graphic-novels-{entry["position"]:03d}',
            'title': entry['title'],
            'authors': authors,
            'form': 'collection' if any(term in entry['form_reported'].casefold() for term in ('cycle', 'collection', 'corpus', 'strip')) else 'book',
            # Preserve existing manga identities on reconciliation. New non-manga
            # comics use the current app's general-literature catalog field.
            'field': 'manga' if entry['manga_context'] else 'literature',
            'original_year': parse_year(entry['year_edition']),
            'original_language': '',
            'countries': countries(entry['tradition']),
            'description': (
                f"Rank {entry['position']} in the owner-supplied worldwide comics synthesis. "
                f"Tradition: {entry['tradition']}. Form: {entry['form_reported']}. "
                f"Genres/themes: {entry['genres']}. "
                f"Manga/Asian-comics publication context: {entry['manga_context'] or 'not specified'}. "
                f"Scope: {entry['scope']}. Editorial rationale: {entry['rationale']}"
            ),
            'work_source_url': provenance if len(provenance) <= 200 else f'{urlparse(provenance).scheme}://{urlparse(provenance).netloc}/',
            'evidence_ids': evidence_ids,
            'edition': None,
            'english_availability_note': 'The supplied report uses the displayed title; a specific English edition and media remain to be verified.',
        })
    return records


def build_selection(entries, sources, catalog):
    source_by_ref = {source['report_source_number']: source for source in sources}
    by_key = {record['key']: record for record in catalog}
    selection, keys = [], []
    for entry in entries:
        key = f'comics-graphic-novels-{entry["position"]:03d}'
        record = by_key[key]
        expected = {name.casefold() for name in record['authors']}
        matches = [work for work in Work.objects.filter(title__iexact=record['title'], is_archived=False).prefetch_related('authors') if {person.name.casefold() for person in work.authors.all()} == expected]
        if len(matches) != 1:
            raise ValueError(f'{key}: expected exactly one reconciled catalog work, found {[work.pk for work in matches]}.')
        source_ids = [source_by_ref[ref]['source_id'] for ref in entry['source_refs']]
        selection.append({
            'key': key,
            'item_id': matches[0].pk,
            'source_ids': source_ids,
            'standing': f"Position {entry['position']} in the owner-supplied worldwide editorial synthesis. {entry['rationale']}",
            'reading': 'No separate reading-value ordering was supplied; this view deliberately retains the report’s worldwide editorial order.',
            'caveat': 'References support criticism, reception, history or bibliographic context; they do not independently prove the exact rank. Reported consultation/access levels are retained, while exact editions and media remain pending.',
            'metadata_status': 'edition_and_media_pending',
            'source_positions': [],
        })
        keys.append(key)
    ranking = Ranking.objects.get(slug=TARGET)
    return {
        'target': TARGET,
        'expected_revision': ranking.revision,
        'version': 'owner-paste-worldwide-comics-graphic-novels-synthesis-2026-09-14',
        'published_on': DATE,
        'allow_pending_metadata': True,
        'reviewed_exclusions': [],
        'notice': 'Initial owner-supplied worldwide comics and graphic-novels synthesis. Its 827-reference bibliography preserves reported access and source-role limits; no personal numerical scores are set.',
        'method': 'Owner-supplied editorial synthesis across comics, graphic novels, manga, manhwa, manhua, comic strips and wordless novels. The report’s 250-position order and its manga publication-context distinctions are retained; the existing Manga · All time ranking remains separate.',
        'entries': selection,
        'orders': {
            'standing': {'label': 'Worldwide critical standing', 'description': 'The report’s supplied editorial order.', 'keys': keys},
            'reading': {'label': 'Reported order (reading-value view pending)', 'description': 'No separate reading-value order was supplied.', 'keys': keys},
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ensure-target', action='store_true')
    parser.add_argument('--build-selection', action='store_true')
    args = parser.parse_args()
    if not ATTACHMENT.exists():
        raise FileNotFoundError(f'Attachment unavailable: {ATTACHMENT}')
    ranking, created = ensure_target() if args.ensure_target else (Ranking.objects.get(slug=TARGET), False)
    INCOMING.parent.mkdir(parents=True, exist_ok=True)
    if not INCOMING.exists():
        shutil.copy2(ATTACHMENT, INCOMING)
    text = INCOMING.read_text()
    digest = hashlib.sha256(INCOMING.read_bytes()).hexdigest()
    entries, sources = parse_entries(text), parse_sources(text)
    catalog = build_catalog(entries, sources)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    ledger_path = OUTPUT / 'sources.json'
    new_ledger = json.dumps({'target_id': TARGET, 'ranking_entries': [], 'sources': sources}, ensure_ascii=False, indent=2) + '\n'
    if ledger_path.exists() and ledger_path.read_text() != new_ledger:
        snapshot = OUTPUT / 'sources-before-source-line-metadata-correction.json'
        if not snapshot.exists():
            snapshot.write_text(ledger_path.read_text())
    ledger_path.write_text(new_ledger)
    (OUTPUT / 'owner-paste-candidates.json').write_text(json.dumps({'target_id': TARGET, 'source_report': str(INCOMING.relative_to(ROOT)), 'reported_source_count': len(sources), 'candidates': entries}, ensure_ascii=False, indent=2) + '\n')
    (OUTPUT / 'owner-paste-catalog.json').write_text(json.dumps({'schema_version': 1, 'allow_pending_editions': True, 'works': catalog}, ensure_ascii=False, indent=2) + '\n')
    (INCOMING.parent / 'RECEIPT.md').write_text(
        f'# Owner attachment receipt\n\n- Received: {DATE}\n- Requested action: import the supplied ranking and sources into the app.\n- SHA-256: `{digest}`\n- Parsed: 250 ranked entries and 827 numbered source records.\n- Source consultation/access claims are externally reported by the supplied bibliography.\n'
    )
    if args.build_selection:
        (OUTPUT / 'owner-paste-selection.json').write_text(json.dumps(build_selection(entries, sources, catalog), ensure_ascii=False, indent=2) + '\n')
    print(f'Target {ranking.slug} ({"created" if created else "existing"}); parsed {len(entries)} entries and {len(sources)} sources; SHA-256 {digest}.')


if __name__ == '__main__':
    main()
