#!/usr/bin/env python3
"""Normalize the owner's audited Japan/Poland revised Top 100 reports safely."""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.config.settings')
import django
django.setup()
from django.db import transaction
from backend.core.models import Ranking, Work

DATE = '2026-09-14'
RUN = '2026-09-14-owner-chat-audited-revision'
REPORTS = {
    'books-japan': Path('/Users/marcinswierczewski/.codex/attachments/1668ddaf-ef3e-4ef0-9645-2aec0c61078a/pasted-text.txt'),
    'books-poland': Path('/Users/marcinswierczewski/.codex/attachments/f8f3da95-9fb7-4494-aa77-c2d27e3ccef3/pasted-text.txt'),
}
RANKING_WORK_CACHE = {}


def compact(value):
    return ' '.join(value.split())


def norm(value):
    value = unicodedata.normalize('NFKD', value)
    value = ''.join(c for c in value if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', '', value.casefold())


def source_family(source_type, url):
    label = f'{source_type} {url}'.casefold()
    if any(word in label for word in ('university', 'library', 'museum', 'academic', 'scholar', 'institute', 'reference', 'digital text')) or '.edu' in urlparse(url).netloc:
        return 'academic_or_institutional'
    if any(word in label for word in ('goodreads', 'reddit', 'forum', 'reader', 'lubimyczytac', 'douban')):
        return 'reader_community'
    return 'editorial_or_specialist'


def access_level(value):
    value = value.casefold()
    if value in {'c', 'text'}:
        return 'full_relevant_content'
    if value in {'b', 'abstract'}:
        return 'relevant_excerpt'
    return 'summary_only'


def eligible(target, access):
    access = access.strip().casefold()
    return access in ({'c', 'b'} if target == 'books-japan' else {'text', 'abstract'})


def parse_sources(target, text):
    prefix = 'JAPAN' if target == 'books-japan' else 'POLAND'
    headers = list(re.finditer(rf'(?m)^({prefix}-\d{{3}})\s+—\s+(.+?)\s*$', text))
    expected = {f'{prefix}-{number:03d}' for number in range(1, (260 if prefix == 'JAPAN' else 242))}
    result, urls = [], set()
    for i, header in enumerate(headers):
        chunk = text[header.end(): headers[i + 1].start() if i + 1 < len(headers) else len(text)]
        source_id, title = header.group(1), header.group(2).strip()
        url_match = re.search(r'(?m)^URL:\s*(https?://\S+)', chunk) or re.search(r'(?m)^(https?://\S+)', chunk)
        if not url_match:
            raise ValueError(f'{source_id}: missing direct URL')
        url = url_match.group(1).rstrip('.,;)')
        canonical = url.rstrip('/')
        if canonical in urls:
            raise ValueError(f'{source_id}: duplicate primary URL')
        urls.add(canonical)
        source_type = (re.search(r'(?m)^Type:\s*(.+)$', chunk) or [None, ''])[1].strip()
        language = (re.search(r'(?m)^Language\s*/\s*region:\s*(.+)$', chunk) or [None, ''])[1].strip()
        access_match = re.search(r'Access:\s*([A-Z]+)', chunk)
        access = access_match.group(1).strip().split()[0].rstrip('.;,') if access_match else 'M'
        use_match = re.search(r'(?ms)^Use:\s*(.+?)(?=\n\s*\n|\Z)', chunk)
        use = compact(use_match.group(1)) if use_match else 'Owner-supplied revised-report source-register context.'
        is_eligible = eligible(target, access)
        result.append({
            'source_id': source_id,
            'underlying_source_id': 'url:' + hashlib.sha256(canonical.encode()).hexdigest()[:24],
            'title': title, 'canonical_url': url, 'source_family': source_family(source_type, url),
            'publisher': urlparse(url).netloc, 'access_level': access_level(access), 'accessed_at': DATE,
            'count_eligible': is_eligible, 'target_ids': [target],
            'relevance_by_target': {target: 'The owner-supplied audited revision reports this target-local record as consulted or audited for context, criticism, reception, bibliography, or a documented access limitation.'},
            'evidence_notes': use,
            'disagreement_or_limitations': 'Access and use are reported by the owner-supplied revision. Records marked metadata, failed, wrong-target, or equivalent remain retained but uncounted; this intake did not independently reread every source.',
            'depends_on_source_ids': [],
            'report_type': source_type, 'report_language_region': language, 'report_access': access,
        })
    if {record['source_id'] for record in result} != expected:
        raise ValueError(f'{target}: expected exact source range, found {len(result)} records')
    return result


def form_kind(value):
    value = value.casefold()
    if any(word in value for word in ('play', 'drama', 'tragedy', 'comedy')):
        return 'play'
    if any(word in value for word in ('essay', 'criticism', 'chronicle', 'philosoph')):
        return 'essay'
    if any(word in value for word in ('story collection', 'linked stories', 'stories', 'anthology', 'poetry', 'poem', 'verse', 'diary', 'memoir', 'reportage')):
        return 'collection'
    return 'book'


def parse_japan_entries(text):
    starts = [m.start() for m in re.finditer(re.escape('2. REVISED TOP 100'), text)]
    if not starts:
        raise ValueError('books-japan: revised-ranking heading missing')
    start = starts[-1]
    section = text[start:text.index('3. CHANGE LOG', start)]
    pattern = re.compile(r'(?ms)^(\d{1,3})\.\s+([^\n]+)\n\s+Author / attribution:\s*([^\n]+)\n\s+Original title:\s*([^\n]+)\n\s+Date:\s*([^\n]+)\n\s+Language / region:\s*([^\n]+)\n\s+Form:\s*([^\n]+)\n\s+Rationale:\s*(.+?)\n\s+Evidence:\s*(.+?)(?=\n\n\d{1,3}\.\s+|\Z)')
    rows = []
    for m in pattern.finditer(section):
        rows.append({'position': int(m.group(1)), 'title': m.group(2).strip(), 'attribution': m.group(3).strip(), 'original_title': m.group(4).strip(), 'date': m.group(5).strip(), 'language_region': m.group(6).strip(), 'form_reported': m.group(7).strip(), 'rationale': compact(m.group(8)), 'source_refs': re.findall(r'JAPAN-\d{3}', m.group(9))})
    return validate_entries('books-japan', rows)


def parse_poland_entries(text):
    start = text.index('2–3. REVISED TOP 100')
    section = text[start:text.index('4. COMPLETE SOURCE REGISTER', start)]
    headers = list(re.finditer(r'(?m)^(\d{3})\.\s+([^\n]+?)\s+—\s+([^\n]+)$', section))
    rows = []
    for index, header in enumerate(headers):
        chunk = section[header.end():headers[index + 1].start() if index + 1 < len(headers) else len(section)]
        date = re.search(r'(?m)^Date:\s*(.+)$', chunk)
        language_form = re.search(r'(?m)^Language / region:\s*(.+?)\s+Form:\s*(.+)$', chunk)
        rationale = re.search(r'(?ms)^Rationale:\s*(.+?)\n\nPrevious:', chunk)
        previous = re.search(r'(?m)^Previous:\s*(.+?)\.\s+Sources:', chunk)
        if not all((date, language_form, rationale, previous)):
            raise ValueError(f'books-poland: malformed entry {header.group(1)}')
        rows.append({'position': int(header.group(1)), 'attribution': header.group(2).strip(), 'title': header.group(3).strip(), 'date': date.group(1).strip(), 'language_region': language_form.group(1).strip(), 'form_reported': language_form.group(2).strip(), 'rationale': compact(rationale.group(1)), 'previous': previous.group(1).strip(), 'source_refs': re.findall(r'POLAND-\d{3}', chunk)})
    return validate_entries('books-poland', rows)


def validate_entries(target, rows):
    if [row['position'] for row in rows] != list(range(1, 101)):
        raise ValueError(f'{target}: expected 100 sequential entries, parsed {len(rows)}')
    if any(not row['source_refs'] for row in rows):
        raise ValueError(f'{target}: every entry needs report source references')
    return rows


def authors(attribution):
    lower = attribution.casefold()
    if any(x in lower for x in ('anonymous', 'many poets', 'multiple', 'collective', 'oral performers', 'compilation uncertain')):
        return []
    if ' in recorded conversations with ' in lower:
        attribution = re.split(r',\s*in recorded conversations with', attribution, flags=re.I)[0]
    attribution = re.sub(r'\s*\([^)]*(?:traditional|attribution|compiler|editor)[^)]*\)', '', attribution, flags=re.I)
    attribution = re.split(r';\s*(?:traditional|with|editor|compiler|multiple)', attribution, maxsplit=1, flags=re.I)[0]
    return [x.strip() for x in re.split(r'\s+(?:and|&)\s+|\s*;\s*', attribution) if x.strip()]


def title_options(title):
    clean = re.sub(r';\s*(?:Polish title|commonly|later|first edition).*$', '', title, flags=re.I).strip()
    options = [title, clean]
    options.extend(re.findall(r'\(([^)]+)\)', title))
    options.extend(x.strip() for x in re.split(r'\s*(?::|;|/)\s*', clean))
    return {norm(x) for x in options if x.strip()}


def existing_authors(title, target):
    if target not in RANKING_WORK_CACHE:
        ranking = Ranking.objects.get(slug=target)
        RANKING_WORK_CACHE[target] = list(Work.objects.filter(rankingentry__ranking=ranking, rankingentry__is_archived=False, is_archived=False).distinct().prefetch_related('authors'))
    matches = RANKING_WORK_CACHE[target]
    options = title_options(title)
    matches = [w for w in matches if norm(w.title) in options]
    if len(matches) == 1 and matches[0].authors.exists():
        return list(matches[0].authors.values_list('name', flat=True))
    return None


def build_catalog(target, entries, sources):
    source_ids = {record['source_id'] for record in sources}
    named, unresolved = [], []
    country = 'Japan' if target == 'books-japan' else 'Poland'
    for row in entries:
        if set(row['source_refs']) - source_ids:
            raise ValueError(f'{target} #{row["position"]}: unknown source reference')
        row_authors = existing_authors(row['title'], target) or authors(row['attribution'])
        base = {
            'key': f'{target}-revision-{row["position"]:03d}', 'title': row['title'], 'authors': row_authors,
            'form': form_kind(row['form_reported']), 'field': 'literature', 'original_year': None,
            'original_language': row['language_region'].split(';', 1)[0].strip(), 'countries': [country],
            'description': f"Position {row['position']} in the owner-supplied audited revision. Attribution: {row['attribution']}. Date: {row['date']}. Form: {row['form_reported']}. {row['rationale']}",
            'work_source_url': next(record['canonical_url'] for record in sources if record['source_id'] == row['source_refs'][0]),
            'evidence_ids': row['source_refs'], 'edition': None, 'english_availability_note': 'Specific edition, translation and media remain to be verified.',
        }
        (named if row_authors else unresolved).append({**base, **({'attribution': row['attribution']} if not row_authors else {})})
    return named, unresolved


def import_unattributed(target, unresolved):
    output = ROOT / 'research' / target
    receipt = []
    with transaction.atomic():
        for record in unresolved:
            matches = list(Work.objects.filter(title__iexact=record['title'], authors__isnull=True, is_archived=False))
            if len(matches) > 1:
                raise ValueError(f'{target}: ambiguous authorless work {record["title"]}')
            work = matches[0] if matches else Work(title=record['title'], form=record['form'], field=record['field'], original_language=record['original_language'], countries=record['countries'], description=record['description'])
            created = not matches
            if created:
                work.full_clean(); work.save()
            receipt.append({'key': record['key'], 'work_id': work.pk, 'created_work': created, 'attribution': record['attribution']})
    (output / 'audited-revision-unresolved-import-receipt.json').write_text(json.dumps({'records': receipt}, ensure_ascii=False, indent=2) + '\n')


def build_selection(target, entries, sources, named, unresolved):
    source_ids = {record['source_id'] for record in sources}
    by_key = {x['key']: x for x in named + unresolved}
    selection, keys, removed = [], [], []
    ranking = Ranking.objects.get(slug=target)
    baseline_work_by_position = {}
    if target == 'books-poland':
        baseline = ranking.revisions.filter(number=2).first()
        if baseline:
            baseline_work_by_position = {record['position']: record['work_id'] for record in baseline.snapshot.get('entries', []) if record.get('work_id')}
    output = ROOT / 'research' / target
    catalog_receipt = json.loads((output / 'audited-revision-catalog-import-receipt.json').read_text())['records']
    id_by_key = {record['key']: record['work_id'] for record in catalog_receipt}
    unresolved_receipt = output / 'audited-revision-unresolved-import-receipt.json'
    if unresolved_receipt.exists():
        id_by_key.update({record['key']: record['work_id'] for record in json.loads(unresolved_receipt.read_text())['records']})
    current_ids = set(ranking.entries.filter(is_archived=False).values_list('work_id', flat=True))
    selected_ids = set()
    for row in entries:
        key = f'{target}-revision-{row["position"]:03d}'; record = by_key[key]
        previous_position = re.search(r'#(\d+)', row.get('previous', ''))
        if previous_position and int(previous_position.group(1)) in baseline_work_by_position:
            work = Work.objects.get(pk=baseline_work_by_position[int(previous_position.group(1))], is_archived=False)
        elif key not in id_by_key:
            raise ValueError(f'{target}: catalog receipt has no work for {key}')
        else:
            work = Work.objects.get(pk=id_by_key[key], is_archived=False)
        selected_ids.add(work.pk); keys.append(key)
        usable = [sid for sid in row['source_refs'] if sid in source_ids]
        selection.append({'key': key, 'item_id': work.pk, 'source_ids': usable, 'standing': f"Position {row['position']} in the owner-supplied audited 14 September 2026 revision. {row['rationale']}", 'reading': 'No separate reading-value order was supplied; this view retains the revised report order.', 'caveat': 'The supplied citations support context, criticism, reception, bibliography or audited access limits, not an exact consensus rank. Reported consultation/access remains externally reported; editions and media are pending.', 'metadata_status': 'edition_and_media_pending', 'source_positions': []})
    for entry in ranking.entries.filter(is_archived=False).exclude(work_id__in=selected_ids):
        removed.append({'item_id': entry.work_id, 'reason': 'Superseded by the established prior-revision catalog identity during audited catalog reconciliation; the superseded shared record and prior revision remain preserved and are not deleted.'})
    return {'target': target, 'expected_revision': ranking.revision, 'allow_expansion': True, 'version': f'owner-chat-audited-country-revision-{DATE}', 'published_on': DATE, 'allow_pending_metadata': True, 'reviewed_exclusions': removed, 'notice': 'Owner-supplied audited revision. Previous revision and source history are preserved; no personal numerical scores are set.', 'method': 'Audited owner-supplied all-time country synthesis. The report maps evidence to entries and records access limitations; its editorial order is retained in both views pending a separately reasoned reading-value order.', 'entries': selection, 'orders': {'standing': {'label': 'Audited revised all-time order', 'description': 'The supplied 14 September 2026 revised editorial order.', 'keys': keys}, 'reading': {'label': 'Revised order (reading-value view pending)', 'description': 'No separate reading-value order was supplied.', 'keys': keys}}}


def apply_scope(target):
    ranking = Ranking.objects.get(slug=target, origin='curated', owner__isnull=True, is_archived=False)
    ranking.scope = {**ranking.scope, 'forms': ['book', 'collection', 'essay', 'play'], 'allow_unresolved_attribution': True, 'revised_scope_date': DATE}
    ranking.full_clean()
    ranking.save(update_fields=['scope', 'updated_at'])


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--target', action='append', choices=REPORTS); parser.add_argument('--apply-scope', action='store_true'); parser.add_argument('--import-unattributed', action='store_true'); parser.add_argument('--build-selection', action='store_true'); args = parser.parse_args()
    for target in args.target or REPORTS:
        attachment = REPORTS[target]
        if args.apply_scope: apply_scope(target)
        incoming = ROOT / 'research' / 'incoming' / target / RUN / 'report.txt'; incoming.parent.mkdir(parents=True, exist_ok=True)
        if not incoming.exists(): shutil.copy2(attachment, incoming)
        text = incoming.read_text(); digest = hashlib.sha256(incoming.read_bytes()).hexdigest()
        sources = parse_sources(target, text); entries = parse_japan_entries(text) if target == 'books-japan' else parse_poland_entries(text); named, unresolved = build_catalog(target, entries, sources)
        output = ROOT / 'research' / target; output.mkdir(parents=True, exist_ok=True)
        (output / 'sources.audited-revision-2026-09-14.json').write_text(json.dumps({'target_id': target, 'ranking_entries': [], 'sources': sources}, ensure_ascii=False, indent=2) + '\n')
        (output / 'audited-revision-candidates.json').write_text(json.dumps({'target_id': target, 'source_report': str(incoming.relative_to(ROOT)), 'candidates': entries}, ensure_ascii=False, indent=2) + '\n')
        (output / 'audited-revision-catalog.json').write_text(json.dumps({'schema_version': 1, 'allow_pending_editions': True, 'works': named}, ensure_ascii=False, indent=2) + '\n')
        (output / 'audited-revision-unresolved-candidates.json').write_text(json.dumps(unresolved, ensure_ascii=False, indent=2) + '\n')
        (incoming.parent / 'RECEIPT.md').write_text(f'# Owner attachment receipt\n\n- Received: {DATE}\n- Requested action: update the existing country ranking positions and sources.\n- SHA-256: `{digest}`\n- Parsed: 100 entries, {len(sources)} registered sources; {len(unresolved)} authorless collective/anonymous records.\n')
        if args.import_unattributed: import_unattributed(target, unresolved)
        if args.build_selection: (output / 'audited-revision-selection.json').write_text(json.dumps(build_selection(target, entries, sources, named, unresolved), ensure_ascii=False, indent=2) + '\n')
        print(f'{target}: 100 entries, {len(sources)} sources, {len(named)} named records, {len(unresolved)} authorless; SHA-256 {digest}')


if __name__ == '__main__': main()
