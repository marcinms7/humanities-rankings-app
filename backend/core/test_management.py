import json
from copy import deepcopy
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .models import Person, Ranking, RankingEntry, ResearchSource, Work


class ResearchImportTests(TestCase):
    def setUp(self):
        self.target = Ranking.objects.create(slug='books-all-time', title='All books', is_public=True)
        self.other = Ranking.objects.create(slug='books-ethics', title='Ethics', is_public=True)
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.file = Path(self.temp.name) / 'sources.json'
        self.ledger = {'target_id': self.target.slug, 'sources': [{
            'source_id': 'S01', 'underlying_source_id': 'independent-original', 'title': 'A consulted source',
            'canonical_url': 'https://example.com/review', 'source_family': 'critical_essay',
            'target_ids': [self.target.slug], 'relevance_by_target': {self.target.slug: 'A comparison of book-length works.'},
            'accessed_at': '2026-09-12', 'access_level': 'relevant_excerpt', 'count_eligible': True,
            'evidence_notes': 'A comparison useful to this scope.', 'disagreement_or_limitations': 'An excerpt only.',
            'depends_on_source_ids': [],
        }]}

    def run_import(self, ledger=None, **options):
        self.file.write_text(json.dumps(ledger or self.ledger))
        call_command('import_research', self.file, target=options.pop('target', self.target.slug), stdout=StringIO(), **options)

    def test_only_named_target_receives_evidence_and_full_ledger_is_retained(self):
        self.run_import()
        saved = self.target.sources.get()
        self.assertEqual(saved.metadata, self.ledger['sources'][0])
        self.assertEqual(self.other.sources.count(), 0)
        self.target.refresh_from_db()
        self.assertEqual(self.target.status, 'collecting')
        self.assertIsNone(self.target.last_researched_at)
        self.assertIsNone(self.target.last_sources_checked_at)
        self.assertEqual(RankingEntry.objects.count(), 0)

    def test_idempotence_preserves_manual_notes_until_explicit_update(self):
        self.run_import()
        saved = self.target.sources.get()
        saved.evidence = 'Owner-reviewed correction.'
        saved.save()
        self.run_import()
        saved.refresh_from_db()
        self.assertEqual(saved.evidence, 'Owner-reviewed correction.')
        self.assertEqual(self.target.sources.count(), 1)
        self.run_import(update_existing=True)
        saved.refresh_from_db()
        self.assertEqual(saved.evidence, self.ledger['sources'][0]['evidence_notes'])

    def test_target_mismatch_does_not_copy_a_corpus(self):
        with self.assertRaisesMessage(CommandError, 'exactly match'):
            self.run_import(target=self.other.slug)
        self.assertFalse(ResearchSource.objects.exists())

    def test_target_specific_relevance_is_required(self):
        self.ledger['sources'][0]['relevance_by_target'] = {self.other.slug: 'Unrelated subject'}
        with self.assertRaisesMessage(CommandError, 'explicit relevance'):
            self.run_import()
        self.assertFalse(ResearchSource.objects.exists())

    def test_duplicate_underlying_source_rejected_atomically(self):
        second = deepcopy(self.ledger['sources'][0])
        second['source_id'] = 'S02'
        self.ledger['sources'].append(second)
        with self.assertRaisesMessage(CommandError, 'deduplicate'):
            self.run_import()
        self.assertFalse(ResearchSource.objects.exists())

    def test_unconsulted_lead_cannot_be_counted(self):
        self.ledger['sources'][0]['access_level'] = 'discovery_lead'
        with self.assertRaisesMessage(CommandError, 'examined content'):
            self.run_import()
        self.ledger['sources'][0]['count_eligible'] = False
        self.run_import()
        self.assertFalse(self.target.sources.get().eligible)

    def test_invalid_dependencies_do_not_import_partial_evidence(self):
        self.ledger['sources'][0]['depends_on_source_ids'] = ['NOT-CONSULTED']
        with self.assertRaisesMessage(CommandError, 'dependency IDs'):
            self.run_import()
        self.assertFalse(ResearchSource.objects.exists())


class BootstrapTests(TestCase):
    def test_empty_definitions_are_created_without_overwriting_edits(self):
        call_command('bootstrap_rankings', stdout=StringIO())
        count = Ranking.objects.count()
        self.assertGreater(count, 50)
        ranking = Ranking.objects.get(slug='books-all-time')
        ranking.title = 'My edited title'
        ranking.save()
        call_command('bootstrap_rankings', stdout=StringIO())
        self.assertEqual(Ranking.objects.count(), count)
        ranking.refresh_from_db()
        self.assertEqual(ranking.title, 'My edited title')
        self.assertFalse(RankingEntry.objects.exists())
        self.assertFalse(ResearchSource.objects.exists())
        self.assertFalse(Work.objects.exists())
        self.assertFalse(Person.objects.exists())
        self.assertEqual(Ranking.objects.get(slug='books-century-20').scope['year_from'], 1901)
        self.assertFalse(Ranking.objects.filter(slug='books-bce').exists())
        self.assertEqual(Ranking.objects.get(slug='books-every-country').scope['group_by'], 'country')


class PreservedReportParsingTests(TestCase):
    def test_horror_report_keeps_title_and_author_columns(self):
        from research.import_owner_top150_reports import REPORTS, parse_entries, parse_sources
        report = next(r for r in REPORTS if r.slug == 'books-horror-all-time')
        root = Path(__file__).resolve().parents[2]
        text = (root / 'research/incoming/books-horror-all-time/2026-09-14-owner-chat-attachments/report.txt').read_text()
        entries = parse_entries(report, text, {s['source_id'] for s in parse_sources(report, text)})
        self.assertEqual(len(entries), 150)
        self.assertEqual((entries[0]['title'], entries[0]['attribution']), ('The Haunting of Hill House', 'Shirley Jackson'))
        self.assertEqual((entries[1]['title'], entries[1]['attribution']), ('Frankenstein', 'Mary Shelley'))

    def test_history_reports_keep_author_first_and_series_identity(self):
        from scripts.prepare_country_synthesis_intake import REPORTS, ranking_records
        root = Path(__file__).resolve().parents[2]
        cases = {'history-books-ancient-world': ('SPQR: A History of Ancient Rome', 'Mary Beard'),
                 'history-books-ancient-rome': ('The Roman Revolution', 'Ronald Syme'),
                 'history-books-england': ('The Making of the English Working Class', 'E. P. Thompson')}
        for target, expected in cases.items():
            text = (root / 'research/incoming' / target / '2026-09-13-owner-paste/report.txt').read_text()
            marker, count, _ = REPORTS[target]
            rows = ranking_records(target, text, marker, count)
            self.assertEqual(len(rows), 100)
            self.assertEqual((rows[0]['reported_title'], rows[0]['reported_author']), expected)
            if target == 'history-books-ancient-world':
                self.assertEqual((rows[5]['reported_title'], rows[5]['reported_author']), ('The Cambridge Ancient History', ''))

    def test_cover_matching_does_not_match_empty_transliterations(self):
        from research.enrich_catalog_covers_public import same_author, same_title
        self.assertFalse(same_title('李白', '杜甫')[0])
        self.assertFalse(same_author(['李白'], ['杜甫']))
        self.assertFalse(same_author(['Mary Shelley'], ['Percy Shelley']))
        self.assertTrue(same_author(['F. Scott Fitzgerald'], ['Francis Scott Fitzgerald']))
