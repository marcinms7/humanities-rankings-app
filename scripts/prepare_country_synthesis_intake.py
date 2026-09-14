#!/usr/bin/env python3
"""Normalize owner-pasted synthesis reports into auditable intake files.

The reports remain untouched under research/incoming.  This intentionally makes
only a provisional candidate map: source registers are reported consultations,
not a claim that this script independently re-read every linked page.
"""
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse
import sys
import argparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.config.settings')
import django
django.setup()
from backend.core.models import Work
from backend.core.models import ResearchSource


REPORTS = {
    'books-japan': ('SOURCE BANK', 100, 'Japan'),
    'books-china': ('SOURCE CORPUS:', 100, 'China'),
    'books-poland': ('SOURCE SET', 100, 'Poland'),
    'books-france': ('130 SOURCES CONSULTED', 100, 'France'),
    'books-united-states': ('SOURCE INVENTORY', 100, 'United States'),
    'books-medieval': ('SOURCES USED / CONSULTED', 100, 'Global medieval world'),
    'books-turkish-tradition': ('SOURCE LIST', 100, 'Turkey'),
    'books-south-america': ('263 SOURCES / SOURCE CHANNELS', 150, 'South America'),
    'books-victorian': ('215 SOURCES USED / SOURCE POOL', 150, 'United Kingdom and Ireland'),
    'books-india': ('ALL SOURCES', 100, 'India'),
    'books-germany': ('112 SOURCES WITH DIRECT URLS', 100, 'Germany'),
    'history-books-ancient-world': ('SOURCE POOL', 100, 'Ancient world'),
    'books-africa': ('SOURCE CORPUS / AUDIT TRAIL', 150, 'Africa'),
    'books-historical-fiction': ('SOURCE INVENTORY', 100, 'Global historical fiction'),
    'history-books-ancient-rome': ('SOURCE INVENTORY', 100, 'Ancient Rome'),
    'history-books-chinese-history': ('\n120 SOURCES\n', 50, 'China'),
    'history-books-england': ('SOURCE INVENTORY', 100, 'England'),
    'books-southeast-asia': ('SOURCE CORPUS', 150, 'Southeast Asia'),
    'books-italy': ('PART I — SOURCE CORPUS', 100, 'Italy'),
    'books-ancient': ('SOURCE CORPUS (221 DISTINCT URLS)', 150, 'Ancient world'),
    'play-all-time': ('ALL 266 SOURCES USED / CONSULTED', 150, 'Global'),
    'books-epistemology': ('SOURCE INVENTORY (163 sources)', 100, 'Global'),
    'books-ethics': ('SOURCE CORPUS — 138 SOURCES WITH RAW URLS', 100, 'Global'),
    'books-political-philosophy': ('SOURCE POOL — 133 DISTINCT SOURCES', 50, 'Global'),
    'short-story-all-time': ('SOURCE CORPUS — 227 DISTINCT SOURCE PAGES', 150, 'Global'),
    'books-metaphysics': ('SOURCE POOL — 153 SOURCES WITH FULL URLs', 100, 'Global'),
    'books-philosophy-of-mind': ('RESEARCH SOURCES — 153 DISTINCT URLS', 50, 'Global'),
    'books-philosophy-of-science': ('SOURCE INVENTORY — 120 SOURCES', 50, 'Global'),
    'history-books-medieval': ('SOURCE POOL (137 SOURCES)', 50, 'Global medieval history'),
    'history-books-london': ('SOURCE INVENTORY — 266 DISTINCT PAGES / RESOURCES', 50, 'England'),
    'history-books-world': ('SOURCE CORPUS — 228 DISTINCT WEB PAGES / DOCUMENTS', 150, None),
    'history-books-social': ('SOURCE POOL — 243 ITEMS', 50, None),
    'books-philosophy-of-language': ('SOURCE POOL: 135 DISTINCT SOURCES', 20, None),
    'books-philosophy-of-mathematics': ('FULL SOURCE POOL', 20, None),
    'books-england': ('RESEARCH SOURCE INVENTORY — 247 SOURCES', 100, 'England'),
    'books-ireland': ('SOURCE INVENTORY', 50, 'Ireland'),
    'books-scotland': ('SOURCE POOL — 270 UNIQUE PAGES', 50, 'Scotland'),
    'essay-all-time': ('RESEARCH BIBLIOGRAPHY — 225 DISTINCT SOURCES', 100, None),
}

# These are pre-existing duplicate catalog identities.  Do not merge or delete
# either record during an intake; use the typography-preserving record where a
# supplied title is otherwise unambiguous.
PREFERRED_EXISTING_WORK_IDS = {
    ('books-england', 16): 582,
    ('essay-all-time', 3): 582,
}


def norm(value):
    value = unicodedata.normalize('NFKD', value)
    value = ''.join(c for c in value if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', '', value.casefold())


def title_options(title):
    options = [title]
    options += re.findall(r'\(([^)]+)\)', title)
    options += re.findall(r'\[([^]]+)\]', title)
    options += [part.strip() for part in title.split('/')]
    cleaned = re.sub(r'\s*[\[(].*?[\])]', '', title).strip()
    options.append(cleaned)
    if norm(cleaned) == 'mencius':
        options.append('Mengzi')
    return [item for item in options if item]


def family(title, url):
    label = f'{title} {url}'.casefold()
    host = urlparse(url).netloc.casefold()
    if any(value in host for value in ('goodreads.', 'reddit.', 'librarything.', 'senscritique.', 'lubimyczytac.', 'douban.')):
        return 'reader_community'
    if any(value in label for value in ('university', 'university', 'cambridge', 'oxford', 'jstor', 'syllabus', 'curriculum', 'library')) or '.edu' in host:
        return 'academic_or_institutional'
    return 'editorial_or_specialist'


def source_records(target, text, marker):
    section = text[text.index(marker):]
    lines = section.splitlines()
    records, seen = [], set()
    for index, line in enumerate(lines):
        match = re.search(r'https?://\S+', line)
        if not match:
            continue
        url = match.group(0).rstrip('.,;)')
        if url in {'http://', 'https://'}:
            continue
        canonical = url.rstrip('/')
        if canonical in seen:
            continue
        seen.add(canonical)
        title = ''
        for previous in reversed(lines[max(0, index - 6):index]):
            numbered = re.match(r'\s*(?:(?:S)?\d{1,3})[.)]\s*(.+?)\s*$', previous)
            if numbered:
                title = numbered.group(1)
                break
        if not title:
            title = urlparse(url).netloc
        source_id = f"{target.replace('books-', '').upper()}-{len(records) + 1:03d}"
        parsed = urlparse(canonical)
        is_discovery_query = (
            'scholar.google.com/scholar' in canonical
            or 'search.worldcat.org/search' in canonical
            or 'jstor.org/action/doBasicSearch' in canonical
            or '/search' in parsed.path
            or 'subject_search' in canonical
        )
        # The language report explicitly calls this a prospective cross-check
        # register ("would use"), rather than reporting consultations.  Keep
        # the URLs, but do not turn that wording into claimed evidence.
        reported_consultation = target not in {'books-philosophy-of-language', 'books-scotland'}
        count_eligible = reported_consultation and not is_discovery_query
        records.append({
            'source_id': source_id,
            'underlying_source_id': 'url:' + hashlib.sha256(canonical.encode()).hexdigest()[:24],
            'title': title,
            'canonical_url': url,
            'source_family': family(title, url),
            'publisher': urlparse(url).netloc,
            'access_level': 'summary_only',
            'accessed_at': '2026-09-13',
            'count_eligible': count_eligible,
            'target_ids': [target],
            'relevance_by_target': {target: (
                'Owner-supplied synthesis reports this source as consulted for this target-specific corpus.'
                if reported_consultation else
                'Owner-supplied report lists this as a prospective cross-check source; consultation is not claimed.'
            )},
            'evidence_notes': (
                'Reported consultation in the owner-supplied synthesis; the detailed source register is retained with the original. Local source-by-source verification remains pending.'
                if reported_consultation and not is_discovery_query else
                'Retained as a reported discovery/search lead, not counted as independent consulted evidence.'
                if is_discovery_query else
                'Retained as a prospective source from the owner-supplied report; local consultation/verification remains pending.'
            ),
            'disagreement_or_limitations': (
                'Search/discovery page, not an independent endorsement or consulted substantive source.'
                if is_discovery_query else
                'The report says these are sources it would use to cross-check the ranking; it does not claim they were consulted.'
                if not reported_consultation else
                'External reported consultation, not independently re-read during intake; per-candidate citations were not supplied.'
            ),
            'depends_on_source_ids': [],
        })
    return records


def ranking_records(target, text, source_marker, expected_count):
    if target == 'books-italy':
        section = text[text.index('PART II — COMPOSITE TOP 100'):]
    elif target == 'history-books-social':
        section = text[text.index('TOP 50 SOCIAL HISTORY BOOKS'):]
    elif target == 'books-ireland':
        section = text[text.index('TOP 50 — SYNTHESIZED RANKING'):]
    else:
        section = text[:text.index(source_marker)]
    rows = []
    for line in section.splitlines():
        if target in {'history-books-chinese-history', 'history-books-london', 'history-books-social', 'books-italy', 'books-metaphysics', 'books-philosophy-of-mind', 'books-philosophy-of-science', 'books-epistemology', 'books-ethics', 'books-political-philosophy', 'books-philosophy-of-language', 'books-philosophy-of-mathematics', 'essay-all-time', 'history-books-medieval'}:
            match = re.match(r'\s*(\d{1,3})\.\s+(.+?)\s+—\s+(.+?)\s*$', line)
            if match:
                position, author, title = int(match.group(1)), match.group(2), match.group(3)
                if 1 <= position <= expected_count:
                    row = {'position': position, 'reported_title': title, 'reported_author': author, 'raw_line': line.strip()}
                    if target in {'history-books-social', 'books-philosophy-of-language', 'books-philosophy-of-mathematics', 'essay-all-time'}:
                        row['reported_title'] = re.sub(r'\s*\([^)]*(?:\d{3,4}|BCE|lectures?|eds?\.)[^)]*\)\s*$', '', title).strip()
                        row['reported_title'] = re.sub(r'\s*,\s*especially\s+.*$', '', row['reported_title'], flags=re.I)
                    if target == 'books-philosophy-of-language':
                        row['reported_title'] = re.sub(r'\s*/\s*“[^”]+”\s*$', '', row['reported_title'])
                        row['reported_form'] = 'Essay' if position in {2, 4, 10, 11, 14, 15, 19} else 'Book'
                    if target == 'books-philosophy-of-mathematics':
                        row['reported_form'] = 'Essay' if position in {6, 7, 9, 10, 16} else 'Book'
                    if target == 'essay-all-time':
                        row['reported_form'] = 'Essay'
                    if target == 'books-philosophy-of-mind':
                        form = re.search(r'\[([^]]+)\]\s*$', title)
                        row['reported_form'] = form.group(1) if form else 'Book'
                        row['reported_title'] = re.sub(r'\s*\((?:c\.\s*)?\d[\d /–-]*(?:BCE)?\)\s*\[[^]]+\]\s*$', '', title).strip()
                    if target == 'books-philosophy-of-science':
                        row['reported_title'] = re.sub(r'\s+\([^)]*(?:\d|century)[^)]*\)\s*$', '', title).strip()
                        row['reported_form'] = 'Essay' if position in {16, 41, 49, 50} else 'Book'
                    if target in {'books-epistemology', 'books-political-philosophy'}:
                        row['reported_title'] = re.sub(r'\s+\([^)]*(?:\d|century|written)[^)]*\)\s*$', '', title).strip()
                    if target == 'books-epistemology':
                        row['reported_form'] = 'Essay' if position in {6, 11, 12, 14, 24, 31, 32, 60, 66, 74, 75, 76, 77, 78, 81, 82, 83, 84, 85, 86, 91, 92} else 'Book'
                    if target == 'books-ethics':
                        row['reported_form'] = 'Essay' if position in {19, 58, 59, 60, 78, 79, 88} else 'Book'
                    if target == 'books-political-philosophy':
                        row['reported_form'] = 'Essay' if position in {9, 21} else 'Book'
                    rows.append(row)
                continue
        match = re.match(r'\s*(\d{1,3})\.\s+(.+?)\s+—\s+(.+?)\s*$', line)
        if not match:
            continue
        position, title, remainder = int(match.group(1)), match.group(2), match.group(3)
        if not 1 <= position <= expected_count:
            continue
        # France includes year and form after the author; other reports do not.
        author = remainder.split(' — ', 1)[0].strip()
        author = re.sub(r'\s*\[[^]]+\]', '', author).strip()
        if author.casefold() in {'various poets', 'various', 'anonymous anthology', 'composite'}:
            author = ''
        rows.append({'position': position, 'reported_title': title, 'reported_author': author, 'raw_line': line.strip()})
    unique = {row['position']: row for row in rows}
    if set(unique) != set(range(1, expected_count + 1)):
        raise ValueError(f'{target}: expected positions 1–{expected_count}, got {sorted(unique)}')
    return [unique[position] for position in range(1, expected_count + 1)]


def main(targets=None):
    for target, (source_marker, expected_count, _country) in REPORTS.items():
        if targets and target not in targets:
            continue
        incoming = ROOT / 'research' / 'incoming' / target / '2026-09-13-owner-chat-attachments' / 'report.txt'
        if not incoming.exists():
            incoming = ROOT / 'research' / 'incoming' / target / '2026-09-13-owner-reupload-2' / 'report.txt'
        if not incoming.exists():
            incoming = ROOT / 'research' / 'incoming' / target / '2026-09-13-owner-reupload' / 'report.txt'
        if not incoming.exists():
            incoming = ROOT / 'research' / 'incoming' / target / '2026-09-13-owner-paste' / 'report.txt'
        text = incoming.read_text()
        output = ROOT / 'research' / target
        output.mkdir(parents=True, exist_ok=True)
        sources = source_records(target, text, source_marker)
        candidates = ranking_records(target, text, source_marker, expected_count)
        (output / 'sources.json').write_text(json.dumps({
            'target_id': target, 'ranking_entries': [], 'sources': sources,
        }, ensure_ascii=False, indent=2) + '\n')
        (output / 'owner-paste-candidates.json').write_text(json.dumps({
            'target_id': target, 'source_report': str(incoming.relative_to(ROOT)),
            'reported_source_count': len(sources), 'candidates': candidates,
        }, ensure_ascii=False, indent=2) + '\n')
        print(f'{target}: {len(candidates)} candidates, {len(sources)} unique URLs')


def clean_authors(value):
    if value.strip().casefold().startswith(('traditional', 'anonymous', 'collective')):
        return []
    value = re.sub(r'\s+et al\.?(?=\s|$)', '', value, flags=re.I)
    value = re.sub(r'\s*\([^)]*\)', '', value)
    value = re.split(r'\s*(?:/|,\s*(?:traditional|compiler|editor)|\s+and\s+(?:disciples|school|others))', value, maxsplit=1, flags=re.I)[0]
    return [part.strip() for part in re.split(r'\s*(?:,\s*|\s*&\s*|\s+and\s+)\s*', value) if part.strip()]


def display_title(value):
    english = re.findall(r'\(([^)]+)\)', value)
    if english and any('a' <= char.casefold() <= 'z' for char in english[0]):
        return english[0].strip()
    return re.sub(r'\s*\[[^]]+\]', '', value).split(' / ')[0].strip()


def catalog_form(target, candidate):
    if target == 'play-all-time':
        return 'play'
    if target == 'short-story-all-time':
        return 'short_story'
    if target == 'essay-all-time':
        return 'essay'
    if target == 'books-ancient':
        descriptors = re.findall(r'\[([^]]+)\]', candidate.get('raw_line', ''))
        descriptor = descriptors[-1].casefold() if descriptors else ''
        if 'anthology' in descriptor:
            return 'collection'
        if any(term in descriptor for term in ('tragedy', 'comedy', 'drama')):
            return 'play'
        if any(term in descriptor for term in ('poetry', 'poem', 'epic', 'hymn', 'elegiac', 'pastoral')) and 'scripture' not in descriptor:
            return 'poem'
    if target in {'books-philosophy-of-mind', 'books-philosophy-of-science', 'books-epistemology', 'books-ethics', 'books-political-philosophy', 'books-philosophy-of-language', 'books-philosophy-of-mathematics'} and re.search(r'(article|essay|chapter)', candidate.get('reported_form', ''), re.I):
        return 'essay'
    return 'book'


def catalog_field(target):
    if target.startswith('history-books-'):
        return 'nonfiction'
    if target in {'books-metaphysics', 'books-philosophy-of-mind', 'books-philosophy-of-science', 'books-epistemology', 'books-ethics', 'books-political-philosophy', 'books-philosophy-of-language', 'books-philosophy-of-mathematics'}:
        return 'philosophy'
    return 'literature'


def build_catalog_and_selection(targets=None):
    works = list(Work.objects.filter(is_archived=False).prefetch_related('authors'))
    for target, _markers in REPORTS.items():
        if targets and target not in targets:
            continue
        output = ROOT / 'research' / target
        sources = json.loads((output / 'sources.json').read_text())['sources']
        candidates = json.loads((output / 'owner-paste-candidates.json').read_text())['candidates']
        if not sources:
            print(f'{target}: no URL-backed sources; candidate map retained but no catalog/publication batch generated')
            continue
        representative_ids = [source['source_id'] for source in sources[:5]]
        records, selection, unresolved = [], [], []
        country = REPORTS[target][2]
        for candidate in candidates:
            authors = clean_authors(candidate['reported_author'])
            if not authors:
                unresolved.append({**candidate, 'reason': 'The report supplies a collective or indeterminate attribution; current ranking entries require a resolved person.'})
                continue
            author_keys = {norm(author) for author in authors}
            matches = []
            for work in works:
                names = {norm(person.name) for person in work.authors.all()}
                if author_keys == names and any(norm(option) == norm(work.title) for option in title_options(candidate['reported_title'])):
                    matches.append(work)
            if len(matches) > 1:
                preferred_id = PREFERRED_EXISTING_WORK_IDS.get((target, candidate['position']))
                if preferred_id:
                    matches = [work for work in matches if work.pk == preferred_id]
                preferred_form = [work for work in matches if work.form == catalog_form(target, candidate)]
                if len(preferred_form) == 1:
                    matches = preferred_form
                if (target, candidate['position']) in {('books-political-philosophy', 46), ('books-ethics', 23)}:
                    preferred = [work for work in matches if work.field == 'philosophy' and work.rankingentry_set.exists()]
                    if len(preferred) == 1:
                        matches = preferred
                if len(matches) == 1:
                    work = matches[0]
                    title, authors = work.title, list(work.authors.values_list('name', flat=True))
                    key = f"{target}-{candidate['position']:03d}"
                    records.append({
                        'key': key, 'title': title, 'authors': authors,
                        'form': catalog_form(target, candidate),
                        'field': catalog_field(target),
                        'original_year': None, 'original_language': '', 'countries': [country] if country else [],
                        'description': f"Included at position {candidate['position']} in the owner-supplied research synthesis. Original report title: {candidate['reported_title']}.",
                        'work_source_url': sources[0]['canonical_url'], 'evidence_ids': representative_ids,
                        'edition': None, 'english_availability_note': 'The owner-supplied report uses an English title or translation title; a specific English edition remains to be verified.',
                    })
                    selection.append({'key': key, 'position': candidate['position'], 'reported_title': candidate['reported_title']})
                    continue
                unresolved.append({**candidate, 'reason': f'Ambiguous existing catalog matches: {[work.pk for work in matches]}.'})
                continue
            if matches:
                work = matches[0]
                title, authors = work.title, list(work.authors.values_list('name', flat=True))
            else:
                title = display_title(candidate['reported_title'])
            key = f"{target}-{candidate['position']:03d}"
            records.append({
                'key': key, 'title': title, 'authors': authors,
                'form': catalog_form(target, candidate),
                'field': catalog_field(target),
                'original_year': None, 'original_language': '', 'countries': [country] if country else [],
                'description': f"Included at position {candidate['position']} in the owner-supplied research synthesis. Original report title: {candidate['reported_title']}.",
                'work_source_url': sources[0]['canonical_url'], 'evidence_ids': representative_ids,
                'edition': None, 'english_availability_note': 'The owner-supplied report uses an English title or translation title; a specific English edition remains to be verified.',
            })
            selection.append({'key': key, 'position': candidate['position'], 'reported_title': candidate['reported_title']})
        catalog = {'schema_version': 1, 'allow_pending_editions': True, 'works': records}
        (output / 'owner-paste-catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n')
        (output / 'owner-paste-unresolved-candidates.json').write_text(json.dumps(unresolved, ensure_ascii=False, indent=2) + '\n')
        (output / 'owner-paste-selection-plan.json').write_text(json.dumps({'target_id': target, 'representative_source_ids': representative_ids, 'entries': selection}, ensure_ascii=False, indent=2) + '\n')
        print(f'{target}: catalog {len(records)}, unresolved {len(unresolved)}')


def build_publication_batches(targets=None):
    from backend.core.models import Ranking
    for target in REPORTS:
        if targets and target not in targets:
            continue
        output = ROOT / 'research' / target
        if sum(source['count_eligible'] for source in json.loads((output / 'sources.json').read_text())['sources']) < 50:
            continue
        catalog = json.loads((output / 'owner-paste-catalog.json').read_text())['works']
        plan = json.loads((output / 'owner-paste-selection-plan.json').read_text())
        by_key = {record['key']: record for record in catalog}
        entries, keys = [], []
        for planned in plan['entries']:
            record = by_key[planned['key']]
            matches = []
            expected_names = {norm(name) for name in record['authors']}
            for work in Work.objects.filter(title__iexact=record['title']).prefetch_related('authors'):
                if {norm(person.name) for person in work.authors.all()} == expected_names:
                    matches.append(work)
            if len(matches) != 1:
                raise ValueError(f"{planned['key']}: expected exactly one catalog identity, found {[work.pk for work in matches]}")
            keys.append(planned['key'])
            entries.append({
                'key': planned['key'], 'item_id': matches[0].pk,
                'source_ids': plan['representative_source_ids'],
                'standing': f"Position {planned['position']} in the owner-supplied cross-source research synthesis.",
                'reading': 'No separate reading-value ordering was supplied; this initial view retains the reported synthesis order.',
                'caveat': 'The supplied source register is corpus-level rather than a per-work citation map; specific English edition and media verification remain pending.',
                'metadata_status': 'edition_and_media_pending',
                'source_positions': [],
            })
        ranking = Ranking.objects.get(slug=target)
        batch = {
            'target': target, 'expected_revision': ranking.revision, 'version': 'owner-paste-research-synthesis-2026-09-13',
            'published_on': '2026-09-13', 'allow_pending_metadata': True, 'reviewed_exclusions': [],
            'notice': 'Initial owner-supplied research synthesis. Source records preserve externally reported consultation and verification limitations; this is not a final exhaustive ranking.',
            'method': 'Reported cross-source synthesis from the owner-supplied report. The supplied order is retained as a provisional editorial order; no personal numerical scores are set.',
            'entries': entries,
            'orders': {
                'standing': {'label': 'Reported cross-source synthesis', 'description': 'The source report’s supplied all-time ordering.', 'keys': keys},
                'reading': {'label': 'Reported order (reading-value view pending)', 'description': 'No separate reading-value order was supplied, so this view currently retains the report order.', 'keys': keys},
            },
        }
        (output / 'owner-paste-selection.json').write_text(json.dumps(batch, ensure_ascii=False, indent=2) + '\n')
        print(f'{target}: publication batch {len(entries)} entries')


def reconcile_victorian_source_ids():
    target = 'books-victorian'
    path = ROOT / 'research' / target / 'sources.json'
    if not path.exists():
        return
    ledger = json.loads(path.read_text())
    existing = {source.underlying_source_id: source.source_id for source in ResearchSource.objects.filter(ranking__slug=target)}
    used = set(existing.values())
    next_number = 1
    for source in ledger['sources']:
        matched = existing.get(source['underlying_source_id'])
        if matched:
            source['source_id'] = matched
            continue
        if source['source_id'] in used:
            while f'VICTORIAN-R{next_number:03d}' in used:
                next_number += 1
            source['source_id'] = f'VICTORIAN-R{next_number:03d}'
            used.add(source['source_id'])
    path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', action='append', choices=sorted(REPORTS))
    args = parser.parse_args()
    main(args.target)
    reconcile_victorian_source_ids()
    build_catalog_and_selection(args.target)
    build_publication_batches(args.target)
