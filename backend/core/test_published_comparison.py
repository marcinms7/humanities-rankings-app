"""Publisher comparison semantics, visibility and bounded response contracts."""
import json
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from .management.commands.export_frontend_contracts import schema_object
from .models import Edition, Person, Ranking, RankingEntry, Work
from .published_comparison import PublishedComparisonSerializer
from .test_api_contracts import assert_shape


class PublishedComparisonTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.reader = get_user_model().objects.create_user('comparison-reader')
        cls.staff = get_user_model().objects.create_user('comparison-staff', is_staff=True)
        cls.left = Ranking.objects.create(title='Publisher A', slug='comparison-a', origin='external',
            is_public=True, publisher='A', source_url='https://example.com/a',
            scope={'countries': ['England'], 'forms': ['book'], 'external_metadata': {
                'method': 'An editorial selection.', 'limitation': 'English-language books only.'},
                'external_import': {'unresolved_count': 2}})
        cls.right = Ranking.objects.create(title='Publisher B', slug='comparison-b', origin='external',
            is_public=True, publisher='B')
        cls.works = [Work.objects.create(title=f'Comparison book {index:02d}') for index in range(32)]
        cls.left_entries = [RankingEntry.objects.create(ranking=cls.left, work=work,
            position=index + 1, source_rank=index + 30) for index, work in enumerate(cls.works[:31])]
        cls.right_entries = [RankingEntry.objects.create(ranking=cls.right, work=work,
            position=index + 1, source_rank=index + 5) for index, work in enumerate(cls.works[1:])]

    def setUp(self):
        self.client = APIClient()
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings_override = override_settings(CATALOG_SEARCH_INDEX=self.directory.name + '/search.sqlite3')
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

    def compare(self, **params):
        return self.client.get('/api/published-comparison/', {
            'left': self.left.pk, 'right': self.right.pk, **params})

    def test_default_discovery_and_exact_original_positions(self):
        initial = self.client.get('/api/published-comparison/')
        self.assertEqual(initial.status_code, 200)
        self.assertIsNone(initial.data['summary'])
        self.assertEqual(len(initial.data['options']), 2)
        response = self.compare()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertEqual(response.data['summary'], dict(shared=30, left_only=1, right_only=1,
            union=32, comparable=30, different=30))
        self.assertEqual(response.data['count'], 30)
        self.assertEqual(len(response.data['results']), 24)
        row = response.data['results'][0]
        self.assertEqual((row['id'], row['left_rank'], row['right_rank'], row['delta']),
            (self.works[1].pk, 31, 5, -26))
        self.assertIn('Countries: England', response.data['left']['scope_labels'])
        self.assertEqual(response.data['left']['unresolved_count'], 2)
        self.assertEqual(response.data['left']['limitation'], 'English-language books only.')
        assert_shape(self, schema_object(PublishedComparisonSerializer()), json.loads(response.content))

    def test_ties_and_unrecorded_ranks_never_use_display_order(self):
        entry = self.left_entries[2]
        entry.source_rank = self.left_entries[1].source_rank
        entry.save()
        self.works[1].title = 'Z first in the source tie'
        self.works[1].save()
        self.works[2].title = 'A second in the source tie'
        self.works[2].save()
        missing = self.right_entries[2]
        missing.source_rank = None
        missing.save()
        response = self.compare()
        self.assertEqual([row['id'] for row in response.data['results'][:2]],
            [self.works[1].pk, self.works[2].pk])
        rows = {row['id']: row for row in response.data['results']}
        for pk in [self.works[1].pk, self.works[2].pk]:
            self.assertEqual(rows[pk]['left_rank'], 31)
            self.assertTrue(rows[pk]['left_tied'])
        row = rows[self.works[3].pk]
        self.assertTrue(row['in_right'])
        self.assertIsNone(row['right_rank'])
        self.assertIsNone(row['delta'])
        self.assertFalse(row['right_tied'])
        self.assertEqual(self.compare().data['summary']['comparable'], 29)

    def test_group_local_positions_are_not_compared_as_global_ranks(self):
        entry = self.left_entries[1]
        entry.groupings = [{'country': 'England', 'local_rank': 1}]
        entry.save()
        response = self.compare(search='Comparison book 01')
        row = response.data['results'][0]
        self.assertIsNone(row['left_rank'])
        self.assertIsNone(row['delta'])
        self.assertEqual(response.data['left']['known_ranks'], 30)

    def test_membership_tabs_and_swapping_do_not_invent_missing_positions(self):
        left_only = self.compare(view='left_only').data
        row = left_only['results'][0]
        self.assertEqual(left_only['count'], 1)
        self.assertEqual(row['id'], self.works[0].pk)
        self.assertEqual(row['left_rank'], 30)
        self.assertFalse(row['in_right'])
        self.assertIsNone(row['right_rank'])
        self.assertIsNone(row['delta'])
        self.assertEqual(self.compare(view='right_only').data['results'][0]['id'], self.works[-1].pk)
        swapped = self.compare(left=self.right.pk, right=self.left.pk).data
        row = swapped['results'][0]
        self.assertEqual((row['left_rank'], row['right_rank'], row['delta']), (5, 31, 26))

    def test_search_and_pages_preserve_source_ranks_and_full_list_summary(self):
        response = self.compare(page=2, page_size=1000)
        self.assertEqual((response.data['count'], len(response.data['results'])), (30, 6))
        self.assertEqual(response.data['results'][0]['left_rank'], 55)
        self.assertTrue(response.data['previous'])
        author = Person.objects.create(name='Élodie Exact')
        self.works[25].authors.add(author)
        response = self.compare(search='elodie exact')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['left_rank'], 55)
        self.assertEqual(response.data['summary']['shared'], 30)

    def test_sorting_largest_difference_retains_the_sign_and_unknown_last(self):
        self.right_entries[4].source_rank = 200
        self.right_entries[4].save()
        self.right_entries[5].source_rank = None
        self.right_entries[5].save()
        response = self.compare(sort='difference')
        self.assertEqual(response.data['results'][0]['id'], self.works[5].pk)
        self.assertEqual(response.data['results'][0]['delta'], 165)
        last = self.compare(sort='difference', page=2).data['results'][-1]
        self.assertEqual(last['id'], self.works[6].pk)
        self.assertIsNone(last['delta'])

    def test_visibility_excludes_collections_personal_archived_and_nonpublic_lists(self):
        rows = [
            Ranking.objects.create(title='Unranked', slug='comparison-unranked', origin='external',
                presentation='unranked', is_public=True),
            Ranking.objects.create(title='Sequence', slug='comparison-sequence', origin='external',
                presentation='reading_sequence', is_public=True),
            Ranking.objects.create(title='Curated', slug='comparison-curated', origin='curated', is_public=True),
            Ranking.objects.create(title='Archived', slug='comparison-archived', origin='external',
                is_archived=True, is_public=True),
            Ranking.objects.create(title='Private', slug='comparison-personal', origin='personal', owner=self.reader),
        ]
        draft = Ranking.objects.create(title='Draft', slug='comparison-draft', origin='external')
        for user in [None, self.reader, self.staff]:
            self.client.force_authenticate(user)
            for ranking in rows:
                self.assertEqual(self.compare(right=ranking.pk).status_code, 404)
            self.assertEqual(self.compare(right=draft.pk).status_code, 200 if user == self.staff else 404)

    def test_archived_records_are_excluded_from_counts_and_cards(self):
        self.works[1].is_archived = True
        self.works[1].save()
        self.left_entries[2].is_archived = True
        self.left_entries[2].save()
        author = Person.objects.create(name='Archived identity', is_archived=True)
        self.works[3].authors.add(author)
        edition = Edition.objects.create(work=self.works[3], pages=200, is_archived=True)
        self.works[3].default_edition = edition
        self.works[3].save()
        response = self.compare()
        self.assertEqual(response.data['summary']['shared'], 28)
        self.assertEqual(response.data['left']['total'], 29)
        self.assertEqual(response.data['right']['total'], 30)
        first = response.data['results'][0]['book']
        self.assertEqual(first['id'], self.works[3].pk)
        self.assertIsNone(first['edition'])
        self.assertEqual(first['authors'], [])

    def test_validation_and_get_only_behavior(self):
        for params in [{'left': 'bad'}, {'left': -1}, {'left': '9' * 100}, {'right': self.left.pk},
                       {'sort': 'bad'}, {'view': 'bad'}, {'search': 'x' * 301}]:
            response = self.compare(**params)
            self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(self.compare(right=9223372036854775807).status_code, 404)
        self.assertEqual(self.compare(page=999).status_code, 404)
        self.assertEqual(self.client.post('/api/published-comparison/', {}).status_code, 405)

    def test_matching_people_lists_and_catalog_identity(self):
        people_a = Ranking.objects.create(title='People A', slug='comparison-people-a', origin='external',
            item_type='person', is_public=True)
        people_b = Ranking.objects.create(title='People B', slug='comparison-people-b', origin='external',
            item_type='person', is_public=True)
        first, second = Person.objects.create(name='Shared name'), Person.objects.create(name='Shared name')
        RankingEntry.objects.create(ranking=people_a, person=first, source_rank=5)
        RankingEntry.objects.create(ranking=people_b, person=second, source_rank=5)
        response = self.compare(left=people_a.pk, right=people_b.pk)
        self.assertEqual(response.data['summary']['shared'], 0)
        self.assertEqual(self.compare(right=people_a.pk).status_code, 400)
        RankingEntry.objects.create(ranking=people_b, person=first, source_rank=7)
        response = self.compare(left=people_a.pk, right=people_b.pk)
        row = response.data['results'][0]
        self.assertEqual(row['person']['id'], first.pk)
        self.assertIsNone(row['book'])
        self.assertEqual(row['delta'], 2)
        assert_shape(self, schema_object(PublishedComparisonSerializer()), json.loads(response.content))

    def test_queries_are_bounded_for_full_cards(self):
        for work in self.works:
            work.authors.add(Person.objects.create(name=work.title + ' author'))
        with CaptureQueriesContext(connection) as queries:
            response = self.compare()
        self.assertEqual(len(response.data['results']), 24)
        self.assertLessEqual(len(queries), 8, '\n'.join(row['sql'] for row in queries))
