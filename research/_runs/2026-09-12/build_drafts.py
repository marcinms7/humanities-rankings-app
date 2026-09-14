"""Render a dated research proposal; never write the application database."""
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUN = Path(__file__).resolve().parent
inputs = json.loads((RUN / 'draft-candidate-input.json').read_text())
specs = json.loads((RUN / 'draft-order-input.json').read_text())
works = {r[0]: r for r in inputs['works']}
people = {r[0]: r for r in inputs['people']}
index = ['# Provisional ranking comparisons — 12 September 2026', '',
         'The owner requested both critical standing/enduring influence and reading value today. These are **five 25-candidate pilot comparisons**, each with two explicit editorial orderings. They are not completed worldwide Top 25s or the intended 100–200-entry rankings. No final criteria, weights or scores have been assigned.', '',
         'Read [the method and its limits](DRAFT_METHOD.md). The underlying research evidence is imported into the application database; these proposal files are not published app entries. Most specific English editions remain unverified, so the book lists are conditional research drafts rather than ready-to-use edition recommendations.', '',
         '| Target | Consulted sources | Draft candidates | Both orderings and evidence |',
         '| --- | ---: | ---: | --- |']

for slug, spec in specs.items():
    folder = ROOT / 'research' / slug
    ledger = json.loads((folder / 'sources.json').read_text())
    sources = {s['source_id']: s for s in ledger['sources']}
    eligible = [s for s in sources.values() if s['count_eligible']]
    standing, reading = spec['standing'].split(), spec['reading'].split()
    assert len(standing) == len(reading) == 25
    assert len(set(standing)) == 25 and set(standing) == set(reading)
    positions = {k: i + 1 for i, k in enumerate(reading)}
    candidates = []
    for i, key in enumerate(standing, 1):
        person = slug == 'philosophers-all-time'
        row = (people if person else works)[key]
        if person:
            _, title, ids, historical, today, caution = row
            creator = None
        else:
            _, title, creator, ids, historical, today, caution = row
        ids = ids.split()
        if slug == 'nonfiction-all-time' and key == 'republic':
            # Only these separately recorded sources support this target;
            # do not silently borrow the Plato reference from another ledger.
            ids = ['S19', 'R028']
        for sid in ids:
            assert sid in sources, (slug, key, sid)
        entry = {
            'candidate_id': key, 'name': title, 'creator': creator,
            'item_type': 'person' if person else 'work',
            'standing_position_draft': i, 'reading_position_draft': positions[key],
            'reading_movement_up': i - positions[key],
            'source_ids': ids,
            'standing_argument_proposed': historical,
            'reading_argument_proposed': today,
            'uncertainty': caution,
            'confidence_in_exact_positions': 'low; editorial hypothesis, not measured consensus',
            'final_criteria': None, 'final_assessments': None, 'final_score': None,
            'english_edition_status': 'not_applicable_to_person' if person else 'specific_edition_verification_pending',
        }
        if key == 'darwin':
            entry['english_edition_status'] = 'historical_English_edition_verified'
            entry['edition_evidence'] = {'source_id': 'R174', 'publisher': 'John Murray', 'year': 1859, 'edition': 'first edition', 'access': 'complete hosted transcription; introduction consulted', 'purchase_availability': 'not_checked'}
        candidates.append(entry)
    proposal = {
        'target_id': slug, 'version': '2026-09-12-two-lenses-v1',
        'status': 'partial_editorial_proposal_not_published',
        'methodology': '../DRAFT_METHOD.md',
        'owner_direction': 'Show both orderings to expose the tradeoffs',
        'intended_final_length': '100–200', 'pilot_candidate_count': 25,
        'eligible_sources_in_target': len(eligible),
        'comparison_universe': 'the same selected 25 candidates in each lens; not an exhaustive global comparison',
        'coverage_gaps': spec['gaps'], 'tradeoffs': spec['tradeoffs'],
        'candidates': candidates,
    }
    (folder / 'provisional-ranking-v1.json').write_text(json.dumps(proposal, ensure_ascii=False, indent=2) + '\n')
    by_key = {c['candidate_id']: c for c in candidates}
    lines = [f"# {spec['title']} — two provisional orderings", '',
             '**25-candidate pilot; incomplete research; not published.** Both columns use the same candidate pool. Positions are proposed editorial judgments, not source-list positions, computed scores or established consensus. Exact-position confidence is low throughout.', '',
             f"Target evidence: **{len(eligible)} consulted sources**. Intended eventual length: 100–200. Most specific English editions remain pending; see the JSON for the limited verification completed. [Method](../DRAFT_METHOD.md) · [Machine-readable proposal](provisional-ranking-v1.json) · [Full source ledger](sources.json)", '',
             '| Position | Critical standing and enduring influence | Reading value today |',
             '| ---: | --- | --- |']
    for i, (a, b) in enumerate(zip(standing, reading), 1):
        lines.append(f"| {i} | {by_key[a]['name']} | {by_key[b]['name']} |")
    lines += ['', '## What changes, and why', '']
    lines += ['- ' + t for t in spec['tradeoffs']]
    lines += ['', 'These movements are hypotheses made explicit for review. The current evidence does not establish that adjacent candidates are distinguishable with this precision.', '',
              '## Candidate arguments and evidence', '',
              'The arguments below are the proposed synthesis. Linked sources support inclusion, interpretation or reception; they do not themselves assert these exact positions. A single source or narrow excerpt leaves a particularly weak comparative case.', '',
              '| Candidate | Standing / reading | Proposed standing case | Proposed reading case | Evidence and unresolved issue |',
              '| --- | ---: | --- | --- | --- |']
    for c in candidates:
        refs = ', '.join(f"[{sid}]({sources[sid]['canonical_url']})" for sid in c['source_ids'])
        label = c['name'] + (f" — {c['creator']}" if c['creator'] else '')
        lines.append(f"| {label} | {c['standing_position_draft']} / {c['reading_position_draft']} | {c['standing_argument_proposed']} | {c['reading_argument_proposed']} | {refs}. {c['uncertainty']} |")
    lines += ['', '## Outstanding comparisons', '', spec['gaps'], '',
              'Before publication: expand the candidate pool, strengthen thin dossiers, verify specific complete English editions, review work/collection identities, and develop the owner-controlled criteria and weights. Keep these draft positions separate from every publisher’s original order and from personal overrides.', '']
    (folder / 'PROVISIONAL_RANKING.md').write_text('\n'.join(lines))

    groups = Counter()
    for s in eligible:
        domain = s['domain_or_platform'].removeprefix('www.')
        # Make the most consequential shared ownership visible rather than
        # presenting author names appended to publisher labels as new owners.
        if domain in {'penguin.co.uk', 'sites.prh.com', 'penguinrandomhouse.com'}:
            group = 'Penguin Random House'
        elif domain in {'plato.stanford.edu', 'ndpr.nd.edu', 'iep.utm.edu', 'doppiozero.com', 'newhumanist.org.uk'}:
            group = domain
        else:
            group = s.get('publisher_group') or domain
        groups[group] += 1
    claim_map = defaultdict(list)
    for s in sources.values():
        for claim in s.get('candidates_or_claims_supported', []):
            claim_map[claim].append(s['source_id'])
    audit = {
        'target_id': slug, 'eligible_records': len(eligible),
        'distinct_underlying_sources': len({s['underlying_source_id'] for s in eligible}),
        'by_family': dict(Counter(s['source_family'] for s in eligible).most_common()),
        'by_domain': dict(Counter(s['domain_or_platform'] for s in eligible).most_common()),
        'by_language': dict(Counter(s['language'] for s in eligible).most_common()),
        'by_access': dict(Counter(s['access_level'] for s in eligible).most_common()),
        'by_recorded_publisher_group_with_known_normalizations': dict(groups.most_common()),
        'publisher_group_warning': 'Not an audited count of independent owners. Some source metadata embeds author names in publisher labels. Domain counts provide a more conservative concentration view; hosting country is not author origin.',
        'claims_as_recorded_not_resolved_catalog_entities': dict(sorted(claim_map.items())),
        'candidate_specific_reconsultations': ['../_runs/2026-09-12/batch-24.json', '../_runs/2026-09-12/batch-25.json'],
    }
    assert audit['eligible_records'] == audit['distinct_underlying_sources']
    (folder / 'evidence-audit-v1.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n')
    notes = [f"# {spec['title']} — research state", '',
             'Updated 12 September 2026. Research resumed on the owner’s request; the earlier build-time pause is superseded. Scope remains this target only.', '',
             f"**{len(eligible)} distinct eligible consulted sources saved and imported.** The hard minimum of 50 is met; research is incomplete. The owner wants substantially greater depth, often over 100 and toward 200 or more where useful, with worldwide and non-English exploration. Neither 50 nor 100 is a completion rule.", '',
             '**New deliverable:** [two provisional 25-candidate orderings](PROVISIONAL_RANKING.md), with proposed reasons, source links, disagreements and explicit gaps. The owner selected both critical standing/enduring influence and reading value today. Final criteria, weights, assessments and scores remain unset. No app ranking entries have been populated; importing evidence is separate from publication.', '',
             '[Cumulative ledger](sources.json) · [Batch history](BATCH_LOG.md) · [Diversity and claim audit](evidence-audit-v1.json) · [Proposal data](provisional-ranking-v1.json) · [Method](../DRAFT_METHOD.md)', '',
             '## Actual source mix', '', '| Family | Sources |', '| --- | ---: |']
    notes += [f'| {k} | {v} |' for k, v in audit['by_family'].items()]
    notes += ['', 'Largest domains: ' + '; '.join(f'{k}: {v}' for k, v in list(audit['by_domain'].items())[:8]) + '.', '',
              'Consulted languages: ' + '; '.join(f'{k}: {v}' for k, v in audit['by_language'].items()) + '.', '',
              'These counts do not imply balanced geographic coverage. English scholarly reference material and repeated critical platforms still contribute substantial concentration. Independently authored pages can count separately, but shared ownership, common data and repeated arguments must not become independent ranking votes. Primary texts support interpretation, not independent reception. Abstract/summary-only items support narrow claims only.', '',
              '## Next useful work', '', spec['gaps'], '',
              'Expand beyond this pilot toward the intended 100–200 candidates; verify complete English editions, resolve aliases and compilation boundaries, and collect direct comparisons and serious dissent for thin dossiers. Philosophy needs more independent reader discussion and non-reference scholarship; literature needs deeper candidate-specific scholarship; nonfiction needs many more non-philosophy sources. Continue saving/importing every small batch.', '',
              '## Preservation and status', '',
              'Earlier source records were preserved without --update-existing. The original all-books ledger and notes were snapshotted before continuation. Completed-research dates remain unset. Private data, source positions, revisions and owner preferences must remain intact. These files record an honest partial checkpoint because the owner redirected effort toward concrete ranking synthesis; source exploration continues to be required.', '']
    (folder / 'RESEARCH.md').write_text('\n'.join(notes))
    index.append(f"| {spec['title']} | {len(eligible)} | 25 | [Compare both]({slug}/PROVISIONAL_RANKING.md) |")

index += ['', 'The first research pass has many more sources than the earlier 51-source all-books survey, but the corpus is still uneven. The next step is to strengthen the weakest placement arguments and complete English-edition checks while expanding both the source base and candidate pool. Do not treat these pilot positions as a final answer to the full all-time scope.', '']
(ROOT / 'research' / 'RANKING_DRAFTS.md').write_text('\n'.join(index))
print('Rendered five proposals, five audits, five research notes, and draft index; no database writes.')
