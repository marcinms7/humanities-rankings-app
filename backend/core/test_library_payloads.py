"""Privacy/pagination regressions saved for a future authorized isolated run."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient, APIRequestFactory

from .library_queries import library_queryset
from .models import Edition, LibraryItem, Person, Ranking, RankingEntry, RankingPreference, ReadingAttempt, Work
from .serializers import LibrarySerializer, WorkSerializer


class LibraryPayloadBoundaries(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('compact-library-reader')
        cls.other = get_user_model().objects.create_user('other-compact-reader')
        cls.person = Person.objects.create(name='Payload fixture author', biography='Detail biography ' * 50)
        cls.works, cls.items = [], []
        for index in range(30):
            work = Work.objects.create(title=f'Payload book {index:02d}', description='Full book detail ' * 50)
            work.authors.add(cls.person)
            edition = Edition.objects.create(work=work, pages=120, translation_notes='Detailed translation notes ' * 50)
            work.default_edition = edition
            work.save()
            cls.works.append(work)
            cls.items.append(LibraryItem.objects.create(user=cls.user, work=work, notes=f'Private note {index}',
                status='reading' if index % 2 else 'want_to_read', shelves=["Reader's shelf"] if index % 2 else ['Owned'],
                personal_tags=['weekend'], read_next_position=index + 1 if index < 28 else None))
        cls.foreign_item = LibraryItem.objects.create(user=cls.other, work=cls.works[0], notes='Another reader’s secret')
        cls.attempt = ReadingAttempt.objects.create(user=cls.user, work=cls.works[0], status='finished',
            notes='Private historical notes', reading_basis={'pages': 80, 'origin': 'selected', 'pages_basis': 'manually_recorded'})
        cls.foreign_attempt = ReadingAttempt.objects.create(user=cls.other, work=cls.works[0], status='finished', notes='Foreign historical notes')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_compact_library_is_paged_and_details_remain_available(self):
        result = self.client.get('/api/library/?compact=1')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual((result.data['count'], len(result.data['results'])), (30, 24))
        row = result.data['results'][0]
        self.assertNotIn('notes', row)
        self.assertNotIn('selected_edition', row)
        self.assertNotIn('description', row['book'])
        self.assertNotIn('biography', row['book']['authors'][0])
        self.assertNotIn('translation_notes', row['book']['edition'])
        detail = self.client.get(f"/api/library/{row['id']}/")
        self.assertIn('Private note', detail.data['notes'])
        default = self.client.get('/api/library/')
        self.assertEqual(len(default.data['results']), 30)
        self.assertIn('notes', default.data['results'][0])

    def test_exact_shelf_and_status_filters_have_consistent_status_counts(self):
        response = self.client.get('/api/library/', {'compact': '1', 'shelf': "Reader's shelf", 'tag': 'weekend', 'status': 'reading', 'search': 'Payload'})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 15)
        facets = self.client.get('/api/library/facets/', {'shelf': "Reader's shelf", 'status': 'want_to_read'})
        self.assertEqual(facets.data['total'], 15)
        self.assertEqual(facets.data['statuses']['reading'], 15)
        self.assertEqual(facets.data['statuses']['want_to_read'], 0)
        self.assertEqual(self.client.get('/api/library/?compact=1&shelf=Reader').data['count'], 0)

    def test_history_list_omits_notes_and_detail_enforces_ownership(self):
        summary = self.client.get('/api/library/history/?paged=1')
        self.assertEqual(summary.status_code, 200, summary.data)
        self.assertEqual(summary.data['count'], 1)
        self.assertTrue(summary.data['results'][0]['has_notes'])
        self.assertNotIn('notes', summary.data['results'][0])
        self.assertNotIn('reading_basis', summary.data['results'][0])
        detail = self.client.get(f'/api/library/history/{self.attempt.pk}/')
        self.assertEqual(detail.data['notes'], 'Private historical notes')
        self.assertEqual(detail.data['reading_basis']['pages'], 80)
        self.assertEqual(self.client.get(f'/api/library/history/{self.foreign_attempt.pk}/').status_code, 404)
        legacy = self.client.get('/api/library/history/')
        self.assertIsInstance(legacy.data, list)
        self.assertEqual(legacy.data[0]['notes'], 'Private historical notes')

    def test_selector_preserves_frozen_and_explicitly_unknown_lengths(self):
        self.works[0].default_edition.pages = 500
        self.works[0].default_edition.save()
        unknown = self.items[1]
        unknown.reading_basis = {**unknown.reading_basis, 'pages': None}
        unknown.save()
        response = self.client.get('/api/library/selector/')
        by_work = {row['work']: row for row in response.data}
        self.assertEqual(by_work[self.works[0].pk]['pages'], 120)
        self.assertIsNone(by_work[self.works[1].pk]['pages'])
        self.assertEqual(set(by_work[self.works[0].pk]), {'id', 'work', 'title', 'status', 'current_page', 'pages'})

    def test_read_next_pages_keep_global_order_and_only_return_shortlist(self):
        response = self.client.get('/api/library/read-next/?page=2')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.data['count'], len(response.data['results'])), (28, 4))
        self.assertEqual([row['read_next_position'] for row in response.data['results']], [25, 26, 27, 28])
        self.assertEqual(response.data['first_id'], self.items[0].pk)
        self.assertEqual(response.data['last_id'], self.items[27].pk)
        self.assertNotIn('notes', response.data['results'][0])

    def test_overview_is_bounded_and_private(self):
        result = self.client.get('/api/library/overview/')
        self.assertEqual((result.data['count'], result.data['reading_count'], len(result.data['currently_reading'])), (30, 15, 3))
        self.client.force_authenticate(self.other)
        result = self.client.get('/api/library/overview/')
        self.assertEqual((result.data['count'], result.data['reading_count']), (1, 0))
        self.assertEqual(len(self.client.get('/api/library/selector/').data), 1)
        self.assertEqual(self.client.get(f'/api/library/{self.items[0].pk}/').status_code, 404)

    def test_historical_editions_are_loaded_in_one_batch(self):
        ids = [item.pk for item in self.items[:3]]
        for work in self.works[:3]:
            work.default_edition = Edition.objects.create(work=work, pages=240)
            work.save()
        rows = list(library_queryset(self.user).filter(pk__in=ids))
        request = APIRequestFactory().get('/api/library/')
        request.user = self.user
        with self.assertNumQueries(1):
            serialized = LibrarySerializer(rows, many=True, context={'request': request}).data
        self.assertTrue(all(row['selected_edition']['pages'] == 120 for row in serialized))

    def test_recommendations_only_serialize_winning_books(self):
        ranking = Ranking.objects.create(title='Recommendation payload fixture', slug='payload-recommendations',
            origin='curated', status='published', is_public=True, criteria=[{'id': 'criterion', 'label': 'Fixture'}])
        RankingEntry.objects.bulk_create([RankingEntry(ranking=ranking, work=work, position=index + 1,
            assessments={'criterion': (index % 10) + 1}) for index, work in enumerate(self.works)])
        RankingPreference.objects.create(user=self.user, ranking=ranking, weights={'criterion': 100})
        original = WorkSerializer.get_reading_time
        with patch.object(WorkSerializer, 'get_reading_time', autospec=True, side_effect=original) as calculate:
            result = self.client.get('/api/rankings/recommendations/?limit=2')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(len(result.data['results']), 2)
        self.assertEqual(calculate.call_count, 2)
