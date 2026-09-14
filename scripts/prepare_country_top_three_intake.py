#!/usr/bin/env python3
"""Preserve, normalize and publish the owner's Top 3 books by country report."""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.config.settings')

import django
django.setup()

from django.db import transaction
from django.utils import timezone

from backend.core.models import Person, Ranking, RankingEntry, ResearchSource, Work
from backend.core.views import ensure_revision, save_revision


TARGET = 'books-every-country'
DATE = '2026-09-14'
RUN = '2026-09-14-owner-chat-attachment'
ATTACHMENT = Path('/Users/marcinswierczewski/.codex/attachments/0eadb005-7bf7-4aaa-97aa-f7abae403e10/pasted-text.txt')
REGIONS = ['AFRICA', 'AMERICAS', 'ASIA', 'EUROPE', 'OCEANIA', 'ADDITIONAL COUNTRIES AND LITERARY REGIONS']


def compact(value):
    return ' '.join(value.split())


def norm(value):
    return re.sub(r'[^a-z0-9]+', '', value.casefold())


def country_label(value):
    label = value.title()
    for before, after in [(' And ', ' and '), (' Of ', ' of '), (' The ', ' the '), (' D’', ' d’'), (" D'", " d'")]:
        label = label.replace(before, after)
    return label.replace('Drc', 'DRC')


def title_variants(value):
    values = {norm(value)}
    if match := re.fullmatch(r'(.*?)\s*\(([^()]*)\)', value):
        values.update({norm(match.group(1)), norm(match.group(2))})
    return {item for item in values if item}


AUTHOR_OVERRIDES = {
    'Ben Bam Solomon, Elmina Quadina, Eston Thoma and other Nauruan contributors': ['Ben Bam Solomon', 'Elmina Quadina', 'Eston Thoma'],
    'Cao Xueqin; later completion traditionally associated with Gao E, with disputed editorial authorship': ['Cao Xueqin', 'Gao E'],
    'Elizabeth Diaz Rechebei and Samuel F. McPhetres': ['Elizabeth Diaz Rechebei', 'Samuel F. McPhetres'],
    'Evelyn Flores and Emelihter Kihleng, editors; multiple Indigenous authors': ['Evelyn Flores', 'Emelihter Kihleng'],
    'John Bul Dau, with Michael S. Sweeney': ['John Bul Dau', 'Michael S. Sweeney'],
    'Joseph Diescho, with Celeste Wallin': ['Joseph Diescho', 'Celeste Wallin'],
    'Mande oral tradition; Mamadou Kouyaté, as recounted by Djibril Tamsir Niane': ['Mamadou Kouyaté', 'Djibril Tamsir Niane'],
    'Marshallese storytellers; Daniel A. Kelin II, collector and editor': ['Daniel A. Kelin II'],
    'Mikaela Nyman and Rebecca Tobo Olul-Hossen, editors; multiple contributors': ['Mikaela Nyman', 'Rebecca Tobo Olul-Hossen'],
    'Neli Lifuka, as told to Klaus-Friedrich Koch': ['Neli Lifuka', 'Klaus-Friedrich Koch'],
    'Nouhou Malio, performed; Thomas A. Hale, recorded and translated': ['Nouhou Malio', 'Thomas A. Hale'],
    'Pope Francis, in conversation with Andrea Tornielli': ['Pope Francis', 'Andrea Tornielli'],
    'Reinis and Matīss Kaudzīte': ['Reinis Kaudzīte', 'Matīss Kaudzīte'],
    'Suamalie N. T. Iosefa, Doug Munro and Niko Besnier': ['Suamalie N. T. Iosefa', 'Doug Munro', 'Niko Besnier'],
}


def credited_authors(value):
    if value in AUTHOR_OVERRIDES:
        return AUTHOR_OVERRIDES[value]
    low = value.casefold()
    if (low.startswith('anonymous') or low.startswith('named and unnamed')
            or low.startswith('maldivian storytellers') or low.startswith('palauan storytellers')):
        return []
    if low.startswith('traditionally attributed to '):
        return [re.split(r';', value[28:], maxsplit=1)[0].strip()]
    value = re.split(r';|,\s+(?:compiler|reteller|retelling|traditional attribution|recording|chiefly|reworking|pseudonym|from |with a debated)', value, maxsplit=1, flags=re.I)[0]
    value = re.sub(r'^Roque Dalton, from .*$', 'Roque Dalton', value)
    value = re.sub(r'\s+and other .*$', '', value, flags=re.I)
    return [part.strip() for part in re.split(r'\s+and\s+', value) if part.strip()]


def work_form(value):
    low = value.casefold()
    if 'play' in low or 'drama' in low:
        return 'play'
    if 'essay' in low:
        return 'essay'
    if 'collection' in low or 'anthology' in low or 'stories' in low or 'tales' in low:
        return 'collection'
    if any(word in low for word in ['poem', 'poetry', 'verse', 'epic']):
        return 'poem'
    return 'book'


def short_language(value):
    language = re.split(r';|,', value, maxsplit=1)[0].strip().rstrip('.')
    return language if len(language) <= 60 else ''


def source_family(title, site):
    value = f'{title} {site}'.casefold()
    if any(term in value for term in ['reddit', 'goodreads', 'forum', 'librarything', 'stackexchange']):
        return 'reader_community'
    if any(term in value for term in ['university', '.edu', 'jstor', 'project muse', 'journal', 'research', 'academy', 'museum']):
        return 'academic_or_institutional'
    if any(term in value for term in ['worldcat', 'open library', 'wikipedia', 'britannica', 'encyclopedia', 'publisher']):
        return 'bibliographic_or_reference'
    return 'editorial_or_specialist'


def parse_report(text):
    ledger_start = text.index('COMPLETE RETAINED SOURCE LEDGER')
    ranking_text = text[:ledger_start]
    region_markers = sorted((ranking_text.index(f'\n{region}\n'), region) for region in REGIONS)
    section_headers = list(re.finditer(
        r'(?m)^([0-9]{3})\. ([^\n]+)\nEvidence confidence: (ESTABLISHED|PROVISIONAL|LIMITED)\n', ranking_text
    ))
    sections = []
    for section_offset, header in enumerate(section_headers, start=1):
        end = section_headers[section_offset].start() if section_offset < len(section_headers) else ledger_start
        body = text[header.end():end]
        markers = list(re.finditer(r'(?m)^([123])\. ', body))
        affiliation_start = body.index('Affiliation and selection note:')
        affiliation_match = re.search(
            r'(?s)Affiliation and selection note:\s*(.*?)\n\nSources for selection, alternatives and attribution:\s*(.*)\s*$', body
        )
        if len(markers) != 3 or not affiliation_match:
            raise ValueError(f'Could not parse section {header.group(1)} {header.group(2)}')
        items = []
        for item_offset, marker in enumerate(markers):
            item_end = markers[item_offset + 1].start() if item_offset + 1 < len(markers) else affiliation_start
            block = body[marker.start():item_end]
            match = re.fullmatch(
                r'(?s)([123])\. (.*?)\n\s*Author / credited contributors: (.*?)\n\s*'
                r'Original language / specified version: (.*?)\s+Form:\s*(.*?)\.\s*', block
            )
            if not match:
                raise ValueError(f'Could not parse section {header.group(1)} item {item_offset + 1}')
            local_rank, title, attribution, language, reported_form = [compact(value) for value in match.groups()]
            items.append({
                'local_rank': int(local_rank), 'title': title, 'attribution': attribution,
                'language': language.rstrip('.'), 'form_reported': reported_form,
            })
        country = country_label(header.group(2))
        region = max((name for position, name in region_markers if position < header.start()), key=lambda name: REGIONS.index(name))
        # The max-by-index expression above follows the report's ordered region
        # headings and remains stable even when a region has many sections.
        region = region.title().replace(' And ', ' and ')
        refs = re.findall(r'\[S(\d{4})\]', affiliation_match.group(2))
        if not refs:
            raise ValueError(f'No source references for {country}')
        sections.append({
            'section_index': section_offset, 'report_number': int(header.group(1)), 'country': country,
            'region': region, 'confidence': header.group(3), 'affiliation_note': compact(affiliation_match.group(1)),
            'source_ids': [f'S{value}' for value in refs], 'items': items,
        })

    ledger_text = text[ledger_start:]
    source_headers = list(re.finditer(r'(?m)^\[S(\d{4})\]\s+(.+?)\s*$', ledger_text))
    sources = []
    for offset, header in enumerate(source_headers):
        end = source_headers[offset + 1].start() if offset + 1 < len(source_headers) else len(ledger_text)
        block = ledger_text[header.end():end]
        site = re.search(r'(?m)^Site:\s*(.*?)\s*$', block)
        context = re.search(r'(?m)^Context:\s*(.*?)\s*$', block)
        consultation = re.search(r'(?m)^Consultation:\s*(.*?)\s*$', block)
        urls = re.findall(r'(?m)^(https?://\S+)\s*$', block)
        if not site or not context or not consultation or len(urls) != 1:
            raise ValueError(f'Could not parse source S{header.group(1)}')
        source_id = f'S{header.group(1)}'
        url = urls[0].rstrip('.,;)')
        checked = consultation.group(1) == 'Page extract checked'
        sources.append({
            'source_id': source_id,
            'underlying_source_id': 'url:' + hashlib.sha256(url.rstrip('/').encode()).hexdigest()[:24],
            'title': compact(header.group(2)), 'canonical_url': url,
            'source_family': source_family(header.group(2), site.group(1)),
            'publisher': site.group(1),
            'access_level': 'relevant_excerpt' if checked else 'metadata_only',
            'accessed_at': DATE,
            'count_eligible': checked,
            'target_ids': [TARGET],
            'relevance_by_target': {TARGET: f"Owner-supplied source record associated with {compact(context.group(1))} in the Top 3 books by country synthesis."},
            'evidence_notes': (f"The supplied report records a checked page extract for {compact(context.group(1))}; "
                               'it supports a narrow selection, attribution or reception claim, not every placement.' if checked else
                               f"Retained owner-supplied discovery/bibliographic record for {compact(context.group(1))}."),
            'disagreement_or_limitations': ('The page extract was checked by the report compiler; this intake did not independently reread the full source.' if checked else
                                            'The report records search-returned text or metadata. Under the project evidence rules this remains visible but uncounted until the relevant source content is directly examined.'),
            'depends_on_source_ids': [],
            'report_context': compact(context.group(1)),
            'report_consultation': consultation.group(1),
        })
    if len(sections) != 208 or sum(len(section['items']) for section in sections) != 624:
        raise ValueError('Expected 208 country sections and 624 positions.')
    if len(sources) != 1395 or [source['source_id'] for source in sources] != [f'S{i:04d}' for i in range(1, 1396)]:
        raise ValueError('Expected source IDs S0001 through S1395.')
    known_sources = {source['source_id'] for source in sources}
    if any(set(section['source_ids']) - known_sources for section in sections):
        raise ValueError('A country section refers to a missing source record.')
    return sections, sources


def candidates_from_sections(sections):
    candidates = {}
    for section in sections:
        for item in section['items']:
            key = f"{norm(item['title'])}:{norm(item['attribution'])}"
            candidate = candidates.setdefault(key, {
                'key': key, 'title': item['title'], 'attribution': item['attribution'],
                'authors': credited_authors(item['attribution']), 'form': work_form(item['form_reported']),
                'original_language': short_language(item['language']), 'groupings': [],
            })
            if candidate['form'] != work_form(item['form_reported']):
                raise ValueError(f"Conflicting forms for repeated work {item['title']}")
            candidate['groupings'].append({
                'country': section['country'], 'local_rank': item['local_rank'],
                'section_index': section['section_index'], 'region': section['region'],
                'confidence': section['confidence'], 'reported_title': item['title'],
                'attribution': item['attribution'], 'language': item['language'],
                'form_reported': item['form_reported'], 'affiliation_note': section['affiliation_note'],
                'source_ids': section['source_ids'],
            })
    return list(candidates.values())


def match_existing(candidate, works_by_title):
    names = {norm(name) for name in candidate['authors']}
    raw_attribution = norm(candidate['attribution'])
    possibilities = []
    for title in title_variants(candidate['title']):
        possibilities.extend(works_by_title.get(title, []))
    possibilities = list({work.pk: work for work in possibilities}.values())
    matched = []
    for work in possibilities:
        actual = {norm(person.name) for person in work.authors.all()}
        if names and actual and (actual == names or actual <= names or names <= actual or any(name in raw_attribution for name in actual)):
            matched.append(work)
        elif not names and not actual:
            matched.append(work)
    if len(matched) > 1:
        exact_authors = [work for work in matched if {
            norm(person.name) for person in work.authors.all()
        } == names]
        if len(exact_authors) == 1:
            return exact_authors[0]
        exact = [work for work in matched if norm(work.title) == norm(candidate['title'])]
        if len(exact) == 1:
            return exact[0]
        primary_title = re.sub(r'\s*\([^()]*\)\s*$', '', candidate['title'])
        primary = [work for work in matched if norm(work.title) == norm(primary_title)]
        if len(primary) == 1:
            return primary[0]
        # The existing catalogue contains a small number of punctuation-only
        # parallel identities created by earlier imports.  Preserve them, but
        # consistently reuse the identity with the strongest existing use.
        if len({norm(work.title) for work in matched}) == 1 and len({
            tuple(sorted(norm(person.name) for person in work.authors.all())) for work in matched
        }) == 1:
            return sorted(
                matched,
                key=lambda work: (-work.rankingentry_set.filter(is_archived=False).count(),
                                  -int(bool(work.default_edition_id)), work.pk),
            )[0]
        raise ValueError(f"Ambiguous catalog identity: {candidate['title']} — {candidate['attribution']}")
    return matched[0] if matched else None


def reconciliation(candidates):
    works = list(Work.objects.filter(is_archived=False).prefetch_related('authors'))
    by_title = defaultdict(list)
    for work in works:
        by_title[norm(work.title)].append(work)
    rows = []
    used = {}
    for candidate in candidates:
        work = match_existing(candidate, by_title)
        if work and work.pk in used and used[work.pk] != candidate['key']:
            raise ValueError(f"Two report candidates resolve to work {work.pk}: {work.title}")
        if work:
            used[work.pk] = candidate['key']
        rows.append({
            'key': candidate['key'], 'title': candidate['title'], 'attribution': candidate['attribution'],
            'authors': candidate['authors'], 'countries': [group['country'] for group in candidate['groupings']],
            'existing_work_id': work.pk if work else None,
            'existing_title': work.title if work else None,
            'existing_authors': [person.name for person in work.authors.all()] if work else [],
        })
    return rows


def write_artifacts(incoming, text, sections, sources, candidates, rows):
    output = ROOT / 'research' / TARGET
    output.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(incoming.read_bytes()).hexdigest()
    ledger = {'target_id': TARGET, 'ranking_entries': [], 'sources': sources}
    (output / 'sources.owner-chat-2026-09-14.json').write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n')
    (output / 'owner-chat-candidates-2026-09-14.json').write_text(json.dumps({
        'target_id': TARGET, 'source_report': str(incoming.relative_to(ROOT)), 'sections': sections,
    }, ensure_ascii=False, indent=2) + '\n')
    (output / 'owner-chat-reconciliation-2026-09-14.json').write_text(json.dumps({
        'target_id': TARGET, 'input_sha256': digest, 'position_count': 624,
        'distinct_candidate_count': len(candidates), 'records': rows,
    }, ensure_ascii=False, indent=2) + '\n')
    (incoming.parent / 'RECEIPT.md').write_text(
        '# Owner attachment receipt\n\n'
        f'- Received: {DATE}\n- Requested action: populate and format the Top 3 books by country ranking.\n'
        f'- SHA-256: `{digest}`\n- Parsed: 208 country/literary-region sections, 624 positions, '
        f'{len(candidates)} distinct works and 1,395 linked source records.\n'
    )
    return digest


def get_or_create_person(name, source_url):
    matches = Person.objects.filter(name__iexact=name)
    if matches.filter(is_archived=True).exists() or matches.count() > 1:
        raise ValueError(f'Ambiguous or archived person: {name}')
    if matches.exists():
        return matches.get(), False
    # The complete long URL remains in ResearchSource; Person.source_url is an
    # optional legacy 200-character field and must not receive a truncated URL.
    person = Person(name=name, source_url=source_url if len(source_url) <= 200 else '')
    person.full_clean()
    person.save()
    return person, True


def apply_publication(sections, sources, candidates, rows, digest):
    output = ROOT / 'research' / TARGET
    source_urls = {source['source_id']: source['canonical_url'] for source in sources}
    row_by_key = {row['key']: row for row in rows}
    ranking = Ranking.objects.select_for_update().get(slug=TARGET, origin='curated', owner__isnull=True, is_archived=False)
    if ranking.scope.get('editorial', {}).get('input_sha256') == digest:
        print('This exact report is already published; no changes.')
        return
    if ranking.entries.filter(is_archived=False).exists() or ranking.revisions.exists():
        raise ValueError('The country target is no longer empty; use a separately reviewed revision workflow.')
    if ResearchSource.objects.filter(ranking=ranking, is_archived=False).count() != 1395:
        raise ValueError('Import the complete target-local source ledger before publication.')

    created_works = created_people = 0
    resolved = {}
    for candidate in candidates:
        match = row_by_key[candidate['key']]
        work = Work.objects.filter(pk=match['existing_work_id'], is_archived=False).first() if match['existing_work_id'] else None
        if work is None:
            first_source = candidate['groupings'][0]['source_ids'][0]
            people = []
            for name in candidate['authors']:
                person, created = get_or_create_person(name, source_urls[first_source])
                created_people += int(created)
                people.append(person)
            countries = list(dict.fromkeys(group['country'] for group in candidate['groupings']))
            work = Work(
                title=candidate['title'], form=candidate['form'], field='literature',
                original_language=candidate['original_language'], countries=countries,
                description=(f"Selected in the owner-supplied Top 3 books by country report for {', '.join(countries)}. "
                             f"Reported credit: {candidate['attribution']}. Specific English edition and media remain to be verified."),
            )
            work.full_clean()
            work.save()
            work.authors.set(people)
            created_works += 1
        resolved[candidate['key']] = work

    ensure_revision(ranking)
    item_ids = []
    entry_ids = {}
    for position, candidate in enumerate(candidates, start=1):
        work = resolved[candidate['key']]
        entry = RankingEntry(
            ranking=ranking, work=work, position=position, source_rank=None, assessments={},
            rationale=(f"Selected in {len(candidate['groupings'])} country/literary-region section"
                       f"{'s' if len(candidate['groupings']) != 1 else ''}; local ranks and section-specific notes are preserved below."),
            groupings=candidate['groupings'],
        )
        entry.full_clean()
        entry.save()
        item_ids.append(work.pk)
        entry_ids[candidate['key']] = entry.pk

    confidence = Counter(section['confidence'] for section in sections)
    ranking.title = 'Top 3 books by country'
    ranking.description = ('Three editorial selections for every UN member state and observer state, plus thirteen additional '
                           'countries and literary regions. Browse in report order or filter by country; numbering restarts at 1–3 in every section.')
    ranking.presentation = 'unranked'
    ranking.target_size = 624
    ranking.status = 'initial_selection'
    ranking.last_researched_at = timezone.make_aware(datetime(2026, 9, 14, 12, 0))
    ranking.scope = {
        'forms': ['book', 'collection', 'essay', 'short_story', 'poem', 'play'],
        'group_by': 'country', 'items_per_country': 3, 'display_format': 'country_grouped',
        'coverage_status': 'initial_selection', 'english_edition_required': False,
        'country_section_count': 208, 'position_count': 624, 'distinct_work_count': len(candidates),
        'source_record_count': 1395, 'checked_source_count': sum(source['count_eligible'] for source in sources),
        'confidence_counts': dict(confidence),
        'editorial': {
            'version': 'owner-chat-top-3-books-by-country-2026-09-14', 'published_on': DATE,
            'notice': ('Owner-supplied 208-section editorial selection. It contains 624 local positions and '
                       f'{len(candidates)} distinct catalog works; repeated works are retained in every applicable section.'),
            'method': ('The supplied country-by-country order is preserved without inventing a global rank. Source access labels '
                       'remain honest: 12 page extracts count as checked evidence, while 1,383 search-returned/metadata records remain visible unverified leads.'),
            'input_sha256': digest, 'entries': {}, 'reviewed_exclusions': [],
            'orders': {
                'standing': {'label': 'Country sections', 'description': 'Report section order with local ranks 1–3.', 'item_ids': item_ids},
                'reading': {'label': 'Country sections', 'description': 'No separate reading-value order was supplied.', 'item_ids': item_ids},
            },
        },
    }
    ranking.full_clean()
    save_revision(ranking, f'Initial country-grouped selection: 208 sections, 624 positions and {len(candidates)} distinct works. Personal scores unset.')
    receipt = {
        'input_sha256': digest, 'ranking_id': ranking.pk, 'revision': ranking.revision,
        'country_sections': 208, 'positions': 624, 'distinct_works': len(candidates),
        'source_records': 1395, 'eligible_sources': sum(source['count_eligible'] for source in sources),
        'created_works': created_works, 'created_people': created_people, 'entry_ids': entry_ids,
    }
    (output / 'owner-chat-publication-2026-09-14.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: value for key, value in receipt.items() if key != 'entry_ids'}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    incoming = ROOT / 'research' / 'incoming' / TARGET / RUN / 'report.txt'
    incoming.parent.mkdir(parents=True, exist_ok=True)
    if not incoming.exists():
        shutil.copy2(ATTACHMENT, incoming)
    text = incoming.read_text()
    sections, sources = parse_report(text)
    candidates = candidates_from_sections(sections)
    rows = reconciliation(candidates)
    digest = write_artifacts(incoming, text, sections, sources, candidates, rows)
    print(json.dumps({
        'sha256': digest, 'sections': len(sections), 'positions': sum(len(section['items']) for section in sections),
        'distinct_works': len(candidates), 'existing_matches': sum(row['existing_work_id'] is not None for row in rows),
        'new_works': sum(row['existing_work_id'] is None for row in rows),
        'authorless_new_works': sum(not candidate['authors'] and row_by['existing_work_id'] is None for candidate, row_by in zip(candidates, rows)),
        'sources': len(sources), 'eligible_sources': sum(source['count_eligible'] for source in sources),
    }, ensure_ascii=False))
    if args.apply:
        with transaction.atomic():
            apply_publication(sections, sources, candidates, rows, digest)


if __name__ == '__main__':
    main()
