#!/usr/bin/env python3
"""Normalize the owner's manga Top 250 report into auditable import batches."""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.config.settings')
import django

django.setup()

from backend.core.models import Work


TARGET = 'manga-all-time'
INCOMING = ROOT / 'research/incoming/manga-all-time/2026-09-13-owner-chat-attachment/report.txt'
OUTPUT = ROOT / 'research/manga-all-time'

# The report distinguishes adaptations, continuations, and source-novel/story
# credits. Catalog authors preserve the manga creators, not prose sources or
# production collectives which the Person model cannot faithfully represent.
CREATOR_OVERRIDES = {
    'Kentaro Miura; continuation by Studio Gaga under Kouji Mori': ['Kentaro Miura', 'Kouji Mori'],
    'Takehiko Inoue; based on Eiji Yoshikawa': ['Takehiko Inoue'],
    'Asao Takamori / Ikki Kajiwara; Tetsuya Chiba': ['Asao Takamori', 'Tetsuya Chiba'],
    'Naoki Urasawa; Takashi Nagasaki; based on Osamu Tezuka': ['Naoki Urasawa', 'Takashi Nagasaki'],
    'Shinichi Sakamoto; story contributions by Yoshio Nabeta and Hiroshi Takano; inspired by Jiro Nitta': ['Shinichi Sakamoto'],
    'Takayuki Yamaguchi; based on Norio Nanjo': ['Takayuki Yamaguchi'],
    'Gamon Sakurai; initial story by Tsuina Miura': ['Gamon Sakurai', 'Tsuina Miura'],
    'Natsu Hyuga; Itsuki Nanao; Nekokurage; character concepts by Touco Shino': ['Natsu Hyuga', 'Itsuki Nanao', 'Nekokurage'],
    'Takao Saito; Saito Production': ['Takao Saito'],
}


def source_family(source_type, publisher):
    label = f'{source_type} {publisher}'.casefold()
    if any(term in label for term in ('award', 'scholarly', 'academic', 'university', 'museum', 'library', 'reference', 'encyclopedia')):
        return 'academic_or_institutional'
    if any(term in label for term in ('forum', 'reddit', 'community', 'reader', 'goodreads', 'bangumi')):
        return 'reader_community'
    return 'editorial_or_specialist'


def access_level(value):
    value = value.casefold()
    if 'full page' in value:
        return 'full_relevant_content'
    if 'excerpt' in value:
        return 'relevant_excerpt'
    return 'summary_only'


def creators(raw):
    if raw in CREATOR_OVERRIDES:
        return CREATOR_OVERRIDES[raw]
    raw = re.split(r';\s*(?:based on|story contributions|inspired by|initial story by|character concepts by|continuation by)', raw, maxsplit=1, flags=re.I)[0]
    return [part.strip() for part in raw.split(';') if part.strip()]


def parse_entries(text):
    top = text[text.index('TOP 250'):text.index('CATEGORY INDEX — RANKS PRESERVED')]
    pattern = re.compile(
        r'(?ms)^(\d{3})\.\s+(.+?)\n'
        r'Creator\(s\):\s*(.+?)\n'
        r'Audience / publication category:\s*(.+?)\n'
        r'Genres / themes:\s*(.+?)\n'
        r'Editorial rationale:\s*(.+?)\n'
        r'Evidence references:\s*(.+?)(?=\n\n(?:\d{3}\.|CATEGORY INDEX)|\Z)'
    )
    entries = []
    for match in pattern.finditer(top):
        position = int(match.group(1))
        refs = re.findall(r'S\d{3}', match.group(7))
        entries.append({
            'position': position,
            'reported_title': match.group(2).strip(),
            'reported_creators': match.group(3).strip(),
            'audience': match.group(4).strip(),
            'genres': match.group(5).strip(),
            'rationale': ' '.join(match.group(6).split()),
            'source_refs': refs,
        })
    if [entry['position'] for entry in entries] != list(range(1, 251)):
        raise ValueError(f'Expected ranked positions 1–250, found {[entry["position"] for entry in entries]}')
    if any(not entry['source_refs'] for entry in entries):
        raise ValueError('Every ranked manga entry must retain at least one supplied source reference.')
    return entries


def field(chunk, label):
    match = re.search(rf'(?m)^{re.escape(label)}:\s*(.+?)\s*$', chunk)
    return match.group(1).strip() if match else ''


def parse_sources(text):
    section = text[text.index('COMPLETE SOURCE REGISTER — 596 DISTINCT SOURCES'):]
    headers = list(re.finditer(r'(?m)^\[S(\d{3})\]\s+(.+?)\s*$', section))
    records, seen_urls = [], set()
    for index, header in enumerate(headers):
        chunk = section[header.end():headers[index + 1].start() if index + 1 < len(headers) else len(section)]
        source_number, title = header.group(1), header.group(2).strip()
        publisher = field(chunk, 'Publisher / community')
        region_language = field(chunk, 'Region')
        source_type_access = field(chunk, 'Type')
        url = field(chunk, 'URL')
        evidence = re.search(r'(?ms)^Evidence / limitation:\s*(.*?)(?=^(?:Relevant ranks|Role):|\Z)', chunk)
        evidence = ' '.join(evidence.group(1).split()) if evidence else ''
        ranks = field(chunk, 'Relevant ranks')
        role = field(chunk, 'Role')
        if not url.startswith(('https://', 'http://')):
            raise ValueError(f'S{source_number}: missing usable URL')
        canonical = url.rstrip('/')
        if canonical in seen_urls:
            raise ValueError(f'S{source_number}: repeated source URL {canonical}')
        seen_urls.add(canonical)
        type_part, _, access_part = source_type_access.partition('| Access:')
        source_id = f'MANGA-S{source_number}'
        records.append({
            'source_id': source_id,
            'underlying_source_id': 'url:' + hashlib.sha256(canonical.encode()).hexdigest()[:24],
            'title': title,
            'canonical_url': url,
            'source_family': source_family(type_part, publisher),
            'publisher': publisher or urlparse(url).netloc,
            'access_level': access_level(access_part),
            'accessed_at': '2026-09-13',
            'count_eligible': True,
            'target_ids': [TARGET],
            'relevance_by_target': {TARGET: 'Owner-supplied international manga synthesis records this source as consulted for its Manga · All time corpus.'},
            'evidence_notes': evidence,
            'disagreement_or_limitations': 'Consultation and access level are reported by the owner-supplied source register and not independently re-read source by source during this intake. ' + (role or 'Relevant ranks identify supported discussion/context, not an exact-position vote.'),
            'depends_on_source_ids': [],
            'report_source_number': f'S{source_number}',
            'region_language': region_language,
            'report_type': type_part.strip(),
            'report_access': access_part.strip(),
            'relevant_ranks': ranks,
            'report_role': role,
        })
    numbers = {record['report_source_number'] for record in records}
    if len(records) != 596 or numbers != {f'S{number:03d}' for number in range(1, 597)}:
        raise ValueError(f'Expected S001–S596 once each, found {len(records)} records.')
    return records


def build_catalog(entries, sources):
    source_by_ref = {source['report_source_number']: source for source in sources}
    works = []
    for entry in entries:
        if any(ref not in source_by_ref for ref in entry['source_refs']):
            raise ValueError(f"{entry['position']}: unknown source reference")
        authors = creators(entry['reported_creators'])
        if not authors:
            raise ValueError(f"{entry['position']}: no resolved manga creator")
        key = f'manga-all-time-{entry["position"]:03d}'
        evidence_ids = [source_by_ref[ref]['source_id'] for ref in entry['source_refs']]
        provenance_url = source_by_ref[entry['source_refs'][0]]['canonical_url']
        # Person.source_url is a legacy 200-character field. The complete,
        # cited URL remains on the target-local ResearchSource; use the
        # publisher root only when that catalog-provenance field cannot hold it.
        if len(provenance_url) > 200:
            parsed = urlparse(provenance_url)
            provenance_url = f'{parsed.scheme}://{parsed.netloc}/'
        works.append({
            'key': key,
            'title': entry['reported_title'],
            'authors': authors,
            'form': 'book',
            'field': 'manga',
            'original_year': None,
            'original_language': 'Japanese',
            'countries': ['Japan'],
            'description': (
                f"Rank {entry['position']} in the owner-supplied international manga synthesis. "
                f"Audience/publication: {entry['audience']}. Genres/themes: {entry['genres']}. "
                f"Editorial rationale: {entry['rationale']}"
            ),
            'work_source_url': provenance_url,
            'evidence_ids': evidence_ids,
            'edition': None,
            'english_availability_note': 'The supplied report gives an English title where available; a specific English edition remains to be verified.',
        })
    return works


def build_selection(entries, sources, catalog):
    source_by_ref = {source['report_source_number']: source for source in sources}
    records_by_key = {record['key']: record for record in catalog}
    selection, keys = [], []
    for entry in entries:
        key = f'manga-all-time-{entry["position"]:03d}'
        record = records_by_key[key]
        expected = {name.casefold() for name in record['authors']}
        matches = []
        for work in Work.objects.filter(title__iexact=record['title'], is_archived=False).prefetch_related('authors'):
            if {person.name.casefold() for person in work.authors.all()} == expected:
                matches.append(work)
        if len(matches) != 1:
            raise ValueError(f'{key}: expected one catalog work, found {[work.pk for work in matches]}')
        source_ids = [source_by_ref[ref]['source_id'] for ref in entry['source_refs']]
        selection.append({
            'key': key,
            'item_id': matches[0].pk,
            'source_ids': source_ids,
            'standing': f"Position {entry['position']} in the owner-supplied international manga synthesis. {entry['rationale']}",
            'reading': 'No separate reading-value ordering was supplied; this view retains the report’s editorial order.',
            'caveat': 'Sources are linked at work level, but their consultation/access labels are externally reported in the supplied source register. Specific English editions and media remain pending.',
            'metadata_status': 'edition_and_media_pending',
            'source_positions': [],
        })
        keys.append(key)
    from backend.core.models import Ranking
    ranking = Ranking.objects.get(slug=TARGET)
    return {
        'target': TARGET,
        'expected_revision': ranking.revision,
        'version': 'owner-paste-international-manga-synthesis-2026-09-13',
        'published_on': '2026-09-13',
        'allow_pending_metadata': True,
        'reviewed_exclusions': [],
        'notice': 'Initial owner-supplied international manga synthesis. The source register preserves reported evidence and access limitations; it is not a final exhaustive ranking.',
        'method': 'Owner-supplied editorial synthesis of 596 distinct linked source pages across 12 reported source languages. The supplied order is retained; no personal numerical scores are set.',
        'entries': selection,
        'orders': {
            'standing': {'label': 'International editorial synthesis', 'description': 'The report’s supplied all-time manga order.', 'keys': keys},
            'reading': {'label': 'Reported order (reading-value view pending)', 'description': 'No separate reading-value order was supplied.', 'keys': keys},
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build-selection', action='store_true')
    args = parser.parse_args()
    text = INCOMING.read_text()
    entries, sources = parse_entries(text), parse_sources(text)
    catalog = build_catalog(entries, sources)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / 'sources.json').write_text(json.dumps({'target_id': TARGET, 'ranking_entries': [], 'sources': sources}, ensure_ascii=False, indent=2) + '\n')
    (OUTPUT / 'owner-paste-candidates.json').write_text(json.dumps({'target_id': TARGET, 'source_report': str(INCOMING.relative_to(ROOT)), 'reported_source_count': len(sources), 'candidates': entries}, ensure_ascii=False, indent=2) + '\n')
    (OUTPUT / 'owner-paste-catalog.json').write_text(json.dumps({'schema_version': 1, 'allow_pending_editions': True, 'works': catalog}, ensure_ascii=False, indent=2) + '\n')
    print(f'Normalized {len(entries)} candidates and {len(sources)} target-local source records.')
    if args.build_selection:
        (OUTPUT / 'owner-paste-selection.json').write_text(json.dumps(build_selection(entries, sources, catalog), ensure_ascii=False, indent=2) + '\n')
        print('Built a 250-entry publication batch.')


if __name__ == '__main__':
    main()
