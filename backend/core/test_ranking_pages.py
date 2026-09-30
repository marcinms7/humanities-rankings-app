"""Bounded ranking reads, original positions, shared privacy and cross-page edits."""
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import LibraryItem, Ranking, RankingEntry, RankingPreference, ResearchSource, Work


class RankingPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user('ranking-pages-owner')
        cls.other = get_user_model().objects.create_user('ranking-pages-other')
        cls.ranking = Ranking.objects.create(title='Personal page fixture', slug='personal-page-fixture',
            origin='personal', owner=cls.owner, sharing_enabled=True, criteria=[{'id': 'value', 'label': 'Reading value'}],
            scope={'private_marker': 'SECRET_SCOPE'})
        cls.works = [Work.objects.create(title=f'Pagination book {index:02d}') for index in range(30)]
        cls.entries = [RankingEntry.objects.create(ranking=cls.ranking, work=work, position=index + 1,
            source_rank=100 + index, rationale='SECRET_RATIONALE', assessments={'value': (index + 1) / 3})
            for index, work in enumerate(cls.works)]
        RankingPreference.objects.create(user=cls.owner, ranking=cls.ranking, weights={'value': 100},
            overrides={str(cls.entries[0].pk): {'value': 9}}, bookmarked=True)
        LibraryItem.objects.create(user=cls.owner, work=cls.works[0], notes='SECRET_LIBRARY_NOTE', rating=10)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings_override = override_settings(CATALOG_SEARCH_INDEX=self.directory.name + '/search.sqlite3')
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

    def page(self, **params):
        return self.client.get(f'/api/ranking-browse/{self.ranking.pk}/', params)

    def test_personal_pages_preserve_manual_positions_and_bound_book_serialization(self):
        response = self.page(page=2)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.data['count'], len(response.data['results'])), (30, 6))
        self.assertEqual([row['display_position'] for row in response.data['results']], list(range(25, 31)))
        self.assertTrue(response.data['results'][0]['can_move_up'])
        self.assertFalse(response.data['results'][-1]['can_move_down'])
        self.assertNotIn('description', response.data['results'][0]['book'])

    def test_adjacent_move_across_page_boundary_requires_current_revision(self):
        response = self.client.post(f'/api/rankings/{self.ranking.pk}/reorder/',
            {'entry_id': self.entries[24].pk, 'direction': -1, 'expected_revision': self.ranking.revision}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        page = self.page(page=1).data
        self.assertEqual(page['results'][-1]['id'], self.entries[24].pk)
        self.assertEqual(self.page(page=2).data['results'][0]['id'], self.entries[23].pk)
        stale = self.client.post(f'/api/rankings/{self.ranking.pk}/reorder/',
            {'entry_id': self.entries[24].pk, 'direction': -1, 'expected_revision': self.ranking.revision}, format='json')
        self.assertEqual(stale.status_code, 409)
        missing = self.client.post(f'/api/rankings/{self.ranking.pk}/reorder/',
            {'entry_id': self.entries[24].pk, 'direction': -1}, format='json')
        self.assertEqual(missing.status_code, 400)

    def test_compact_entry_mutation_does_not_return_the_entire_list(self):
        response = self.client.delete(f'/api/rankings/{self.ranking.pk}/entries/?compact=1',
            {'entry_id': self.entries[-1].pk, 'expected_revision': self.ranking.revision}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(set(response.data), {'detail', 'revision'})
        self.assertEqual(response.data['revision'], self.ranking.revision + 1)

    def test_weighted_preview_pages_sort_before_pagination_and_keep_global_positions(self):
        url = f'/api/rankings/{self.ranking.pk}/preview/?paged=1&page=2'
        response = self.client.post(url, {'weights': {'value': 100}, 'overrides': {}}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([row['id'] for row in response.data['results']], [entry.pk for entry in reversed(self.entries[:6])])
        self.assertEqual([row['display_position'] for row in response.data['results']], list(range(25, 31)))
        filtered = self.client.post(f'/api/rankings/{self.ranking.pk}/preview/?paged=1&search=Pagination%20book%2000',
            {'weights': {'value': 100}, 'overrides': {}}, format='json')
        self.assertEqual(filtered.status_code, 200, filtered.data)
        self.assertEqual(filtered.data['results'][0]['display_position'], 30)
        legacy = self.client.post(f'/api/rankings/{self.ranking.pk}/preview/', {'weights': {'value': 100}}, format='json')
        self.assertIsInstance(legacy.data, list)
        self.assertEqual(len(legacy.data), 30)

    def test_country_pages_count_placements_and_keep_country_local_ranks(self):
        self.ranking.scope = {'group_by': 'country'}
        self.ranking.origin = 'curated'
        self.ranking.owner = None
        self.ranking.sharing_enabled = False
        self.ranking.is_public = True
        self.ranking.save()
        for index, entry in enumerate(self.entries):
            entry.groupings = [{'country': f'Country {index // 3:02d}', 'section_index': index // 3,
                'local_rank': index % 3 + 1, 'region': 'Fixture', 'confidence': 'High', 'language': 'English',
                'form_reported': 'Book', 'affiliation_note': '', 'source_ids': []}]
            entry.save()
        extra = {**self.entries[0].groupings[0], 'country': 'Country 10', 'section_index': 10, 'local_rank': 2}
        self.entries[0].groupings.append(extra)
        self.entries[0].save()
        response = self.page(page=2)
        self.assertEqual((response.data['count'], len(response.data['results'])), (31, 7))
        self.assertEqual(response.data['count_unit'], 'placements')
        self.assertEqual(response.data['results'][-1]['grouping']['country'], 'Country 10')
        self.assertEqual(response.data['results'][-1]['display_position'], 2)
        self.assertEqual(self.page(country='Country 10').data['results'][0]['display_position'], 2)

    def test_shared_pages_never_include_owner_scores_notes_or_private_scope(self):
        self.client.force_authenticate(None)
        url = f'/api/shared/{self.ranking.share_token}/'
        response = self.client.get(url, {'paged': 1, 'page': 1})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.data['page']['count'], len(response.data['page']['results'])), (30, 24))
        text = str(response.data)
        for private in ['SECRET_SCOPE', 'SECRET_RATIONALE', 'SECRET_LIBRARY_NOTE']:
            self.assertNotIn(private, text)
        row = response.data['page']['results'][0]
        self.assertIsNone(row['context'])
        self.assertIsNone(row['score'])
        self.assertEqual(row['assessments'], {})
        self.assertIsNone(response.data['ranking']['preference'])
        compact = self.client.get(url, {'compact': 1})
        self.assertNotIn('entries', compact.data)
        self.ranking.sharing_enabled = False
        self.ranking.save()
        self.assertEqual(self.client.get(url, {'paged': 1}).status_code, 404)

    def test_private_ranking_pages_and_candidates_require_owner_access(self):
        self.client.force_authenticate(self.other)
        self.assertEqual(self.page().status_code, 404)
        self.assertEqual(self.client.get(f'/api/rankings/{self.ranking.pk}/candidates/').status_code, 404)
        response = self.client.get('/api/rankings/', {'paged': 1, 'mode': 'saved'})
        self.assertEqual(response.data['count'], 0)

    def test_candidate_pages_exclude_existing_entries_without_loading_full_books(self):
        additions = [Work.objects.create(title=f'Unused eligible book {index:02d}') for index in range(27)]
        response = self.client.get(f'/api/rankings/{self.ranking.pk}/candidates/', {'page': 2})
        self.assertEqual((response.data['count'], len(response.data['results'])), (27, 3))
        self.assertEqual(set(response.data['results'][0]), {'id', 'title'})
        self.assertTrue(set(row['id'] for row in response.data['results']).issubset({work.pk for work in additions}))

    def test_index_and_sources_are_bounded_with_legacy_default_compatibility(self):
        for index in range(30):
            Ranking.objects.create(title=f'Public index {index:02d}', slug=f'public-index-{index}', is_public=True,
                scope={'countries': ['France' if index % 2 else 'Japan']})
            ResearchSource.objects.create(ranking=self.ranking, source_id=f's{index:02d}', underlying_source_id=f'source-{index}', title='Source',
                url=f'https://example.com/{index}', family='reference')
        response = self.client.get('/api/rankings/', {'paged': 1, 'mode': 'all', 'page': 2})
        self.assertEqual((response.data['count'], len(response.data['results'])), (30, 6))
        filtered = self.client.get('/api/rankings/', {'paged': 1, 'mode': 'all', 'country': 'Japan'})
        self.assertEqual(filtered.data['count'], 15)
        self.assertEqual(filtered.data['facets']['countries'], ['France', 'Japan'])
        sources = self.client.get(f'/api/rankings/{self.ranking.pk}/sources/', {'paged': 1, 'page': 2})
        self.assertEqual((sources.data['count'], len(sources.data['results'])), (30, 6))
        self.assertEqual(len(self.client.get(f'/api/rankings/{self.ranking.pk}/entries/').data), 30)
