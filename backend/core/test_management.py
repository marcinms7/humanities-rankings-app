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
        self.assertEqual(Ranking.objects.get(slug='books-bce').scope['year_to'], -1)
