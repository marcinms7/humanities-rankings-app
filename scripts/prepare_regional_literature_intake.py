#!/usr/bin/env python3
"""Normalize three owner-supplied regional literature syntheses for review/import."""
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
from backend.core.models import Ranking, Work

CONFIG = {
    'books-arabic': {'count': 100, 'sources': 207, 'country': 'Arabic-language tradition', 'language': 'Arabic', 'path': 'research/incoming/books-arabic/2026-09-13-owner-chat-attachments/report.txt'},
    'books-russian': {'count': 100, 'sources': 220, 'country': 'Russian literary tradition', 'language': 'Russian', 'path': 'research/incoming/books-russian/2026-09-13-owner-chat-attachments/report.txt'},
    'books-caribbean': {'count': 50, 'sources': 225, 'country': 'Caribbean', 'language': '', 'path': 'research/incoming/books-caribbean/2026-09-13-owner-chat-attachments/report.txt'},
}


def family(source_type, title):
    label = f'{source_type} {title}'.casefold()
    if any(term in label for term in ('academic', 'university', 'award', 'prize', 'library', 'museum', 'institutional', 'nobel')):
        return 'academic_or_institutional'
    if any(term in label for term in ('reader', 'reddit', 'goodreads', 'douban', 'forum', 'community')):
        return 'reader_community'
    return 'editorial_or_specialist'


def form(value):
    value = value.casefold()
    if 'poem' in value or 'poetry' in value or 'verse' in value:
        return 'poem'
    if 'play' in value or 'drama' in value:
        return 'play'
    if any(term in value for term in ('collection', 'cycle', 'anthology', 'corpus', 'trilogy', 'sequence', 'stories', 'diwan', 'odes')):
        return 'collection'
    return 'book'


def author_names(raw):
    raw = raw.strip()
    if raw.casefold().startswith(('anonymous', 'multiple ', 'various ')) or ' and other ' in raw.casefold():
        return []
    raw = re.sub(r',\s*(?:adapting|based on|transcribed|edited).*$', '', raw, flags=re.I)
    return [part.strip() for part in re.split(r'\s*;\s*|\s*&\s*', raw) if part.strip()]


def refs(value):
    return re.findall(r'S\d{3}', value)


def parse_arabic(text):
    start = text.index('TOP 100 — ANNOTATED RANKING')
    section = text[start:text.index('SOURCE BIBLIOGRAPHY', start)]
    pattern = re.compile(r'(?ms)^(\d{3})\.\s+(.+?)\s+—\s+(.+?)\nGenre / form:\s*(.+?)\nEditorial rationale:\s*(.+?)\nEvidence / context:\s*\[([^]]+)\](?:\nEdition / scope note:\s*(.*?))?(?=\n\n\d{3}\. |\Z)')
    return [{'position': int(m.group(1)), 'title': m.group(2).strip(), 'creator': m.group(3).strip(), 'kind': m.group(4).strip(), 'rationale': ' '.join(m.group(5).split()), 'refs': refs(m.group(6)), 'note': ' '.join((m.group(7) or '').split())} for m in pattern.finditer(section)]


def parse_russian(text):
    section = text[text.index('TOP 100'):text.index('ALL 220 SOURCES')]
    pattern = re.compile(r'(?ms)^(\d{3})\.\s+(.+?)\s+—\s+(.+?)\s+\[([^]]+)\]\s+\|\s+Sources:\s*(.+?)\n\s*Assessment:\s*(.*?)(?=\n\n\d{3}\. |\Z)')
    return [{'position': int(m.group(1)), 'title': m.group(2).strip(), 'creator': m.group(3).strip(), 'kind': m.group(4).strip(), 'rationale': ' '.join(m.group(6).split()), 'refs': refs(m.group(5)), 'note': ''} for m in pattern.finditer(section)]


def parse_caribbean(text):
    section = text[text.index('RANKING'):text.index('CLOSE EXCLUSIONS')]
    pattern = re.compile(r'(?ms)^(\d{2})\.\s+(.+?)\s+—\s+(.+?)\s+\(([^)]*)\)\n\s*Tradition:\s*(.+?)\.\s*Form:\s*(.+?)\.\s*Original language:\s*(.+?)\.\n\s*(.+?)\n\s*Evidence:\s*\[([^]]+)\](?=\n\n\d{2}\. |\s*\Z)')
    return [{'position': int(m.group(1)), 'title': m.group(2).strip(), 'creator': m.group(3).strip(), 'kind': m.group(6).strip(), 'rationale': ' '.join(m.group(8).split()), 'refs': refs(m.group(9)), 'note': f"Original publication: {m.group(4).strip()}. Tradition: {m.group(5).strip()}. Original language: {m.group(7).strip()}."} for m in pattern.finditer(section)]


def line_field(chunk, label):
    match = re.search(rf'(?m)^{re.escape(label)}:\s*(.+?)\s*$', chunk)
    return match.group(1).strip() if match else ''


def parse_sources(target, text):
    if target == 'books-arabic':
        section = text[text.index('SOURCE BIBLIOGRAPHY') :]
        headers = list(re.finditer(r'(?m)^\[S(\d{3})\]\s+(.+?)\s*$', section))
        def extract(number, title, chunk):
            publisher = line_field(chunk, 'Publisher / community')
            type_access = line_field(chunk, 'Type')
            source_type, _, access = type_access.partition('| Access:')
            url = line_field(chunk, 'URL')
            evidence = re.search(r'(?ms)^Evidence / limitation:\s*(.*?)(?=^(?:Relevant ranks|Role):|\Z)', chunk)
            return publisher, source_type.strip(), access.strip(), url, ' '.join(evidence.group(1).split()) if evidence else '', line_field(chunk, 'Role')
    elif target == 'books-russian':
        section = text[text.index('ALL 220 SOURCES') :]
        headers = list(re.finditer(r'(?m)^S(\d{3})\.\s+(.+?)\s*$', section))
        def extract(number, title, chunk):
            details = line_field(chunk, 'Language')
            bits = [bit.strip() for bit in details.split('|')]
            source_type = next((bit.removeprefix('Type:').strip() for bit in bits if bit.startswith('Type:')), '')
            access = next((bit.removeprefix('Access:').strip() for bit in bits if bit.startswith('Access:')), '')
            url_match = re.search(r'(?m)^https?://\S+\s*$', chunk)
            evidence = re.search(r'(?ms)^Use / limitation:\s*(.*?)(?=\n\n|\Z)', chunk)
            return '', source_type, access, url_match.group(0).strip() if url_match else '', ' '.join(evidence.group(1).split()) if evidence else '', ''
    else:
        section = text[text.index('FULL SOURCE BIBLIOGRAPHY') :]
        headers = list(re.finditer(r'(?m)^S(\d{3})\s+\[([^]]+)\]\s+(.+?)\s*$', section))
        def extract(number, title, chunk):
            access = headers  # placeholder replaced below
            url_match = re.search(r'(?m)^https?://\S+\s*$', chunk)
            source_type = line_field(chunk, 'Type')
            evidence = re.search(r'(?ms)^Use / limitation:\s*(.*?)(?=\n\n|\Z)', chunk)
            return '', source_type, '', url_match.group(0).strip() if url_match else '', ' '.join(evidence.group(1).split()) if evidence else '', ''
    records, urls = [], set()
    for index, header in enumerate(headers):
        chunk = section[header.end():headers[index + 1].start() if index + 1 < len(headers) else len(section)]
        number = header.group(1)
        title = header.group(3).strip() if target == 'books-caribbean' else header.group(2).strip()
        publisher, source_type, access, url, evidence, role = extract(number, title, chunk)
        if target == 'books-caribbean':
            access = header.group(2).split('/')[-1]
        if not url.startswith(('http://', 'https://')):
            raise ValueError(f'{target} S{number}: missing URL')
        canonical = url.rstrip('/')
        if canonical in urls:
            raise ValueError(f'{target} S{number}: duplicate URL')
        urls.add(canonical)
        level = 'full_relevant_content' if access in {'P', 'O', 'Full page', 'Full page text'} else 'relevant_excerpt' if access in {'E', 'S', 'Excerpt'} else 'summary_only'
        source_id = f'{target.replace("books-", "").upper()}-S{number}'
        records.append({'source_id': source_id, 'underlying_source_id': 'url:' + hashlib.sha256(canonical.encode()).hexdigest()[:24], 'title': title, 'canonical_url': url, 'source_family': family(source_type, title), 'publisher': publisher or urlparse(url).netloc, 'access_level': level, 'accessed_at': '2026-09-13', 'count_eligible': True, 'target_ids': [target], 'relevance_by_target': {target: 'Owner-supplied regional literature synthesis reports this source as consulted for this target-specific corpus.'}, 'evidence_notes': evidence or 'Reported source-register context; local source-by-source verification remains pending.', 'disagreement_or_limitations': 'Access and consultation are reported by the owner-supplied bibliography, not independently re-read source by source during intake. ' + role, 'depends_on_source_ids': [], 'report_source_number': f'S{number}', 'report_type': source_type, 'report_access': access})
    expected = CONFIG[target]['sources']
    if len(records) != expected or {record['report_source_number'] for record in records} != {f'S{i:03d}' for i in range(1, expected + 1)}:
        raise ValueError(f'{target}: expected S001–S{expected:03d}, parsed {len(records)}')
    return records


def normalize(target, build_selection):
    text = (ROOT / CONFIG[target]['path']).read_text()
    entries = {'books-arabic': parse_arabic, 'books-russian': parse_russian, 'books-caribbean': parse_caribbean}[target](text)
    if [entry['position'] for entry in entries] != list(range(1, CONFIG[target]['count'] + 1)):
        raise ValueError(f'{target}: incomplete ranking parse')
    sources = parse_sources(target, text)
    by_ref = {source['report_source_number']: source for source in sources}
    catalog, unresolved = [], []
    for entry in entries:
        people = author_names(entry['creator'])
        if not people:
            unresolved.append({**entry, 'reason': 'Collective or anonymous attribution retained without inventing a person.'})
            continue
        if any(ref not in by_ref for ref in entry['refs']):
            raise ValueError(f'{target} rank {entry["position"]}: unknown cited source')
        key = f'{target}-{entry["position"]:03d}'
        evidence_ids = [by_ref[ref]['source_id'] for ref in entry['refs']]
        catalog.append({'key': key, 'title': entry['title'], 'authors': people, 'form': form(entry['kind']), 'field': 'literature', 'original_year': None, 'original_language': CONFIG[target]['language'], 'countries': [CONFIG[target]['country']], 'description': f"Rank {entry['position']} in the owner-supplied regional synthesis. Form: {entry['kind']}. {entry['rationale']} {entry['note']}".strip(), 'work_source_url': by_ref[entry['refs'][0]]['canonical_url'], 'evidence_ids': evidence_ids, 'edition': None, 'english_availability_note': 'Specific English edition/translation remains to be verified.'})
    out = ROOT / 'research' / target
    out.mkdir(parents=True, exist_ok=True)
    (out / 'sources.json').write_text(json.dumps({'target_id': target, 'ranking_entries': [], 'sources': sources}, ensure_ascii=False, indent=2) + '\n')
    (out / 'owner-paste-candidates.json').write_text(json.dumps({'target_id': target, 'candidates': entries}, ensure_ascii=False, indent=2) + '\n')
    (out / 'owner-paste-unresolved-candidates.json').write_text(json.dumps(unresolved, ensure_ascii=False, indent=2) + '\n')
    (out / 'owner-paste-catalog.json').write_text(json.dumps({'schema_version': 1, 'allow_pending_editions': True, 'works': catalog}, ensure_ascii=False, indent=2) + '\n')
    print(f'{target}: {len(entries)} candidates, {len(sources)} sources, {len(catalog)} catalog records, {len(unresolved)} unresolved.')
    if build_selection:
        records = {record['key']: record for record in catalog}
        planned, keys = [], []
        for entry in entries:
            key = f'{target}-{entry["position"]:03d}'
            if key not in records:
                continue
            record = records[key]
            matches = [work for work in Work.objects.filter(title__iexact=record['title'], is_archived=False).prefetch_related('authors') if {p.name.casefold() for p in work.authors.all()} == {name.casefold() for name in record['authors']}]
            if len(matches) != 1:
                raise ValueError(f'{key}: expected one catalog work, found {[work.pk for work in matches]}')
            planned.append({'key': key, 'item_id': matches[0].pk, 'source_ids': record['evidence_ids'], 'standing': f"Position {entry['position']} in the owner-supplied regional synthesis. {entry['rationale']}", 'reading': 'No separate reading-value ordering was supplied; this view retains the report order.', 'caveat': 'Sources are linked at work level but reflect externally reported consultation/access; English editions and media remain pending.', 'metadata_status': 'edition_and_media_pending', 'source_positions': []})
            keys.append(key)
        ranking = Ranking.objects.get(slug=target)
        selection = {'target': target, 'expected_revision': ranking.revision, 'version': 'owner-paste-regional-synthesis-2026-09-13', 'published_on': '2026-09-13', 'allow_pending_metadata': True, 'reviewed_exclusions': [], 'notice': 'Initial owner-supplied regional research synthesis; source-level access and corpus limitations are retained.', 'method': 'Owner-supplied cross-source editorial synthesis. The supplied order is retained and personal numerical scores are unset.', 'entries': planned, 'orders': {'standing': {'label': 'Reported regional synthesis', 'description': 'The source report’s supplied order.', 'keys': keys}, 'reading': {'label': 'Reported order (reading-value view pending)', 'description': 'No separate reading-value order was supplied.', 'keys': keys}}}
        (out / 'owner-paste-selection.json').write_text(json.dumps(selection, ensure_ascii=False, indent=2) + '\n')
        print(f'{target}: publication batch {len(planned)} entries.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', action='append', choices=sorted(CONFIG))
    parser.add_argument('--build-selection', action='store_true')
    args = parser.parse_args()
    for target in args.target or CONFIG:
        normalize(target, args.build_selection)
