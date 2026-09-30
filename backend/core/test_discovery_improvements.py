"""Discovery and comparison regressions for the next authorized isolated suite run."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import (Edition, LibraryItem, Ranking, RankingEntry, RankingPreference,
                     ReadingAttempt, SavedDiscoveryFilter, Tag, Work)
from .ranking_browse import position_map


class SavedDiscoveryBoundaries(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('saved-filter-reader')
        cls.other = get_user_model().objects.create_user('different-filter-reader')
        cls.work = Work.objects.create(title='Short Japanese philosophy', countries=['Japan'], field='philosophy')
        cls.edition = Edition.objects.create(work=cls.work, pages=200)
        cls.work.default_edition = cls.edition
        cls.work.save()
        cls.genre = Tag.objects.create(name='Discovery fixture genre', kind='genre')
        cls.work.tags.add(cls.genre)
        cls.ranking = Ranking.objects.create(title='Published fixture', slug='saved-filter-ranking', origin='external', is_public=True)
        RankingEntry.objects.create(ranking=cls.ranking, work=cls.work)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_saved_filters_are_private_for_read_update_delete_and_execution(self):
        saved = SavedDiscoveryFilter.objects.create(user=self.other, name='Private title', filters={'field': 'philosophy'})
        self.assertEqual(self.client.get('/api/saved-filters/').data, [])
        url = f'/api/saved-filters/{saved.pk}/'
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.patch(url, {'name': 'Changed'}, format='json').status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)
        for endpoint in ['personal-discovery', 'works', 'library']:
            self.assertEqual(self.client.get(f'/api/{endpoint}/?saved_filter={saved.pk}').status_code, 404)

    def test_filter_crud_normalizes_and_rejects_invalid_or_duplicate_definitions(self):
        result = self.client.post('/api/saved-filters/', {'name': '  Short philosophy  ', 'filters': {'field': 'philosophy', 'max_pages': '250'}}, format='json')
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual((result.data['name'], result.data['filters']['max_pages']), ('Short philosophy', 250))
        for filters in [{'max_pages': -1}, {'minimum': 1001}, {'bookmarked': True}, {'owner': self.other.pk}, []]:
            self.assertEqual(self.client.post('/api/saved-filters/', {'name': 'Invalid', 'filters': filters}, format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/saved-filters/', {'name': 'Short philosophy', 'filters': {}}, format='json').status_code, 400)
        saved_id = result.data['id']
        renamed = self.client.patch(f'/api/saved-filters/{saved_id}/', {'name': 'Renamed'}, format='json')
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.data['filters']['max_pages'], 250)
        self.assertEqual(self.client.delete(f'/api/saved-filters/{saved_id}/').status_code, 204)

    def test_bookmarks_history_and_catalog_filters_are_intersected(self):
        item = LibraryItem.objects.create(user=self.user, work=self.work)
        RankingPreference.objects.create(user=self.user, ranking=self.ranking, bookmarked=True)
        saved = SavedDiscoveryFilter.objects.create(user=self.user, name='Short unread Japanese philosophy', filters={
            'field': 'philosophy', 'country': 'Japan', 'genre': self.genre.name,
            'max_pages': 250, 'unread': 'yes', 'bookmarked': 'yes', 'minimum': 1})
        for endpoint in ['personal-discovery', 'works', 'library']:
            result = self.client.get(f'/api/{endpoint}/?saved_filter={saved.pk}')
            self.assertEqual(result.status_code, 200, result.data)
            self.assertEqual(result.data['count'], 1)
        ReadingAttempt.objects.create(user=self.user, work=self.work, status='finished', current_page=200)
        self.assertEqual(self.client.get(f'/api/personal-discovery/?saved_filter={saved.pk}').data['count'], 0)
        item.refresh_from_db()
        self.assertEqual(item.status, 'want_to_read')

    def test_frozen_unknown_length_is_not_replaced_by_catalog_length(self):
        unknown = Edition.objects.create(work=self.work)
        item = LibraryItem.objects.create(user=self.user, work=self.work, edition=unknown)
        self.assertIsNone(item.reading_basis['pages'])
        saved = SavedDiscoveryFilter.objects.create(user=self.user, name='Short', filters={'max_pages': 250})
        for endpoint in ['personal-discovery', 'works', 'library']:
            self.assertEqual(self.client.get(f'/api/{endpoint}/?saved_filter={saved.pk}').data['count'], 0)

    def test_legacy_missing_snapshot_uses_selected_edition_without_losing_explicit_unknowns(self):
        selected = Edition.objects.create(work=self.work, pages=80)
        LibraryItem.objects.bulk_create([LibraryItem(user=self.user, work=self.work, edition=selected)])
        result = self.client.get('/api/personal-discovery/?max_pages=100')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual([(row['id'], row['pages']) for row in result.data['results']], [(self.work.pk, 80)])

    def test_reading_collections_and_other_users_bookmarks_do_not_count_as_bookmarked_rankings(self):
        collection = Ranking.objects.create(title='Reading sequence', slug='saved-filter-sequence', origin='external', presentation='reading_sequence', is_public=True)
        RankingEntry.objects.create(ranking=collection, work=self.work)
        RankingPreference.objects.create(user=self.user, ranking=collection, bookmarked=True)
        RankingPreference.objects.create(user=self.other, ranking=self.ranking, bookmarked=True)
        result = self.client.get('/api/personal-discovery/?bookmarked=yes')
        self.assertEqual(result.data['count'], 0)


class RankingComparisonBoundaries(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('comparison-reader')
        cls.works = [Work.objects.create(title=f'Comparison work {index:02d}') for index in range(1, 31)]
        ids = [work.pk for work in cls.works]
        cls.ranking = Ranking.objects.create(title='Comparison fixture', slug='comparison-fixture', origin='curated', is_public=True, scope={'editorial': {
            'orders': {'standing': {'label': 'Critical standing', 'item_ids': ids}, 'reading': {'label': 'Reading value', 'item_ids': ids[::-1]}},
            'entries': {str(work.pk): {'standing': 'Recorded standing explanation', 'reading': 'Recorded reading explanation', 'caveat': 'Supplied evidence', 'sources': []} for work in cls.works}}})
        RankingEntry.objects.bulk_create([RankingEntry(ranking=cls.ranking, work=work, position=index) for index, work in enumerate(cls.works, 1)])

    def setUp(self):
        self.client = APIClient()

    def test_pages_and_filtered_comparison_keep_original_ranks_and_explanations(self):
        url = f'/api/ranking-browse/{self.ranking.pk}/'
        first = self.client.get(url)
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual((first.data['count'], len(first.data['results'])), (30, 24))
        filtered = self.client.get(url, {'search': 'Comparison work 30', 'lens': 'reading'})
        row = filtered.data['results'][0]
        self.assertEqual(row['comparison'], {'standing_rank': 30, 'reading_rank': 1, 'delta': 29})
        self.assertEqual(row['explanation']['reading'], 'Recorded reading explanation')
        self.assertIsNone(row['context'])
        self.assertEqual(filtered.data['comparison']['different'], 30)

    def test_identical_orders_do_not_claim_independent_judgments(self):
        scope = self.ranking.scope
        scope['editorial']['orders']['reading']['item_ids'] = scope['editorial']['orders']['standing']['item_ids']
        self.ranking.save()
        result = self.client.get(f'/api/ranking-browse/{self.ranking.pk}/', {'differences': 'yes'})
        self.assertEqual(result.data['count'], 0)
        self.assertTrue(result.data['comparison']['identical'])
        self.assertIn('not established', result.data['comparison']['status'])

    def test_nonrankings_and_country_groups_never_get_global_comparison_positions(self):
        for field, value in [('presentation', 'unranked'), ('scope', {**self.ranking.scope, 'group_by': 'country'})]:
            original = getattr(self.ranking, field)
            setattr(self.ranking, field, value)
            self.ranking.save()
            result = self.client.get(f'/api/ranking-browse/{self.ranking.pk}/')
            self.assertFalse(result.data['comparison']['available'])
            self.assertIsNone(result.data['results'][0]['comparison'])
            self.assertIsNone(result.data['results'][0]['display_position'])
            setattr(self.ranking, field, original)

    def test_compact_metadata_omits_dossiers_and_missing_positions_remain_unknown(self):
        detail = self.client.get(f'/api/rankings/{self.ranking.pk}/?compact=1')
        self.assertEqual(detail.data['scope']['editorial']['entries'], {})
        self.assertEqual(detail.data['scope']['editorial']['orders']['standing']['item_ids'], [])
        full = self.client.get(f'/api/rankings/{self.ranking.pk}/')
        self.assertEqual(len(full.data['scope']['editorial']['orders']['standing']['item_ids']), 30)
        self.assertEqual(position_map({'item_ids': [10, 20, 10, True, '30', 40]}), {20: 2, 40: 6})
        self.ranking.scope['editorial']['orders']['reading']['item_ids'] = self.ranking.scope['editorial']['orders']['reading']['item_ids'][1:]
        self.ranking.save()
        result = self.client.get(f'/api/ranking-browse/{self.ranking.pk}/', {'search': 'Comparison work 30'})
        self.assertIsNone(result.data['results'][0]['comparison']['reading_rank'])
        self.assertIsNone(result.data['results'][0]['comparison']['delta'])

    def test_private_and_archived_rankings_are_inaccessible_anonymously(self):
        private = Ranking.objects.create(title='Private comparison', slug='private-comparison', origin='personal', owner=self.user)
        self.assertEqual(self.client.get(f'/api/ranking-browse/{private.pk}/').status_code, 404)
        self.ranking.is_archived = True
        self.ranking.save()
        self.assertEqual(self.client.get(f'/api/ranking-browse/{self.ranking.pk}/').status_code, 404)

    def test_empty_saved_order_does_not_invent_positions_from_entry_ordinals(self):
        self.ranking.scope['editorial']['orders']['reading']['item_ids'] = []
        self.ranking.save()
        result = self.client.get(f'/api/ranking-browse/{self.ranking.pk}/?lens=reading')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertTrue(all(row['display_position'] is None for row in result.data['results']))

    def test_different_invalid_order_arrays_are_not_reported_as_identical(self):
        first, second, shared = [work.pk for work in self.works[:3]]
        self.ranking.scope['editorial']['orders']['standing']['item_ids'] = [first, first, shared]
        self.ranking.scope['editorial']['orders']['reading']['item_ids'] = [second, second, shared]
        self.ranking.save()
        result = self.client.get(f'/api/ranking-browse/{self.ranking.pk}/')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertFalse(result.data['comparison']['identical'])
        self.assertEqual(result.data['comparison']['compared'], 1)

    def test_published_rankings_keep_source_order_and_positions_even_with_editorial_metadata(self):
        self.ranking.origin = 'external'
        self.ranking.save()
        first = self.ranking.entries.get(work=self.works[0])
        first.source_rank = 42
        first.save()
        result = self.client.get(f'/api/ranking-browse/{self.ranking.pk}/?lens=reading')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data['results'][0]['work'], self.works[0].pk)
        self.assertEqual(result.data['results'][0]['display_position'], 42)
        self.assertFalse(result.data['comparison']['available'])
