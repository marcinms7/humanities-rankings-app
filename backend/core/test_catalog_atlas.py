"""Atlas geography is saved metadata; overlays belong only to the requester."""
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIRequestFactory, force_authenticate

from .catalog_atlas import CatalogAtlasSerializer, catalog_atlas, year_metadata
from .management.commands.export_frontend_contracts import schema_object
from .models import Edition, LibraryItem, Person, ReadingAttempt, Work
from .test_api_contracts import assert_shape


class CatalogAtlasTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = get_user_model().objects.create_user('atlas-reader')
        self.other = get_user_model().objects.create_user('another-atlas-reader')

    def request(self, params=None, *, user=None):
        request = self.factory.get('/api/catalog-atlas/', params or {})
        if user:
            force_authenticate(request, user=user)
        return catalog_atlas(request)

    def work(self, title, **kwargs):
        return Work.objects.create(title=title, **kwargs)

    def test_century_boundaries_have_no_year_zero(self):
        expected = {-201: '-3', -200: '-2', -101: '-2', -100: '-1', -1: '-1',
                    1: '1', 100: '1', 101: '2', 1900: '19', 1901: '20', 2000: '20', 2001: '21'}
        for year, century in expected.items():
            self.assertEqual(year_metadata(year), (year, century, 'known'))
        self.assertEqual(year_metadata(None), (None, 'unknown', 'missing'))
        for value in [0, -10001, 3001, True, '1900']:
            self.assertEqual(year_metadata(value), (None, 'unknown', 'invalid'))

    def test_missing_and_invalid_metadata_are_explicit_without_invented_labels(self):
        self.work('Known', original_year=-100, countries=['England', 'United Kingdom', 'England'])
        self.work('Missing')
        invalid = self.work('Invalid', original_year=0, countries={'country': 'France'})
        mixed = self.work('Mixed', countries=['Japan', None, '', 4])
        response = self.request()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['summary'], {'catalog': 4, 'saved': 0, 'read': 0,
            'undated': 3, 'unlocated': 2, 'invalid_year': 1, 'invalid_countries': 2})
        countries = {row['key']: row['count'] for row in response.data['countries']}
        self.assertEqual(countries, {'England': 1, 'Japan': 1, 'United Kingdom': 1, '__unknown__': 2})
        rows = {row['book']['id']: row for row in response.data['results']}
        self.assertIsNone(rows[invalid.pk]['original_year'])
        self.assertEqual(rows[invalid.pk]['date_status'], 'invalid')
        self.assertEqual(rows[invalid.pk]['book']['countries'], [])
        self.assertEqual(rows[mixed.pk]['book']['countries'], ['Japan'])
        assert_shape(self, schema_object(CatalogAtlasSerializer()), response.data)
        invalid.refresh_from_db()
        self.assertEqual(invalid.original_year, 0)
        self.assertEqual(invalid.countries, {'country': 'France'})

    def test_archived_works_authors_and_editions_are_not_exposed(self):
        self.work('Hidden work', is_archived=True, countries=['France'])
        work = self.work('Visible work', countries=['Japan'])
        edition = Edition.objects.create(work=work, pages=900, is_archived=True)
        work.default_edition = edition
        work.save(update_fields=['default_edition'])
        work.authors.add(Person.objects.create(name='Archived author', is_archived=True))
        work.authors.add(Person.objects.create(name='Visible author'))
        response = self.request()
        self.assertEqual(response.data['count'], 1)
        book = response.data['results'][0]['book']
        self.assertEqual([row['name'] for row in book['authors']], ['Visible author'])
        self.assertIsNone(book['edition'])
        self.assertEqual([row['key'] for row in response.data['countries']], ['Japan'])
        work.refresh_from_db()
        self.assertEqual(work.default_edition_id, edition.pk)

    def test_finished_history_is_read_even_during_a_new_attempt(self):
        reread = self.work('Rereading', original_year=1901, countries=['England'])
        old = self.work('History without a current item', original_year=1900, countries=['England'])
        wishlist = self.work('Wishlist', countries=['Japan'])
        LibraryItem.objects.create(user=self.user, work=reread, status='reading')
        LibraryItem.objects.create(user=self.user, work=wishlist)
        ReadingAttempt.objects.create(user=self.user, work=reread, status='finished')
        ReadingAttempt.objects.create(user=self.user, work=reread, status='finished')
        ReadingAttempt.objects.create(user=self.user, work=old, status='finished')
        response = self.request({'overlay': 'read'}, user=self.user)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['summary']['saved'], 2)
        self.assertEqual(response.data['summary']['read'], 2)
        rows = {row['book']['id']: row for row in response.data['results']}
        self.assertTrue(rows[reread.pk]['saved'])
        self.assertEqual(rows[reread.pk]['status'], 'reading')
        self.assertTrue(rows[reread.pk]['read'])
        self.assertFalse(rows[old.pk]['saved'])
        self.assertIsNone(rows[old.pk]['status'])

    def test_public_metadata_cache_does_not_share_reading_overlays(self):
        work = self.work('Shared book', original_year=2000, countries=['France'])
        LibraryItem.objects.create(user=self.user, work=work, status='finished')
        first = self.request(user=self.user)
        second = self.request(user=self.other)
        anonymous = self.request()
        self.assertEqual(first.data['summary']['read'], 1)
        self.assertEqual(first.data['countries'][0]['saved'], 1)
        for response in [second, anonymous]:
            self.assertEqual(response.data['summary']['read'], 0)
            self.assertEqual(response.data['countries'][0]['saved'], 0)
            self.assertFalse(response.data['results'][0]['read'])
            self.assertIsNone(response.data['results'][0]['status'])
        for response in [first, second, anonymous]:
            self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertFalse(anonymous.data['authenticated'])
        self.assertTrue(first.data['authenticated'])

    def test_facets_respect_other_dimensions_and_counts_remain_unique(self):
        shared = self.work('Both associations', original_year=1920, countries=['England', 'United Kingdom'])
        self.work('Earlier England', original_year=1880, countries=['England'])
        self.work('Same century elsewhere', original_year=1920, countries=['France'])
        LibraryItem.objects.create(user=self.user, work=shared)
        response = self.request({'country': 'England', 'century': '20', 'overlay': 'saved'}, user=self.user)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['summary']['catalog'], 1)
        self.assertEqual({row['key']: row['count'] for row in response.data['countries']},
                         {'England': 1, 'France': 1, 'United Kingdom': 1})
        self.assertEqual({row['key']: row['count'] for row in response.data['centuries']}, {'19': 1, '20': 1})
        self.assertEqual(sum(row['saved'] for row in response.data['countries']), 2)

    def test_unknown_filters_and_field_filters(self):
        unknown = self.work('Undated philosophy', field='philosophy')
        self.work('Dated philosophy', field='philosophy', original_year=1200)
        self.work('Undated literature')
        response = self.request({'country': '__unknown__', 'century': 'unknown', 'field': 'philosophy'})
        self.assertEqual([row['book']['id'] for row in response.data['results']], [unknown.pk])
        self.assertEqual(response.data['summary']['undated'], 1)
        self.assertEqual(response.data['summary']['unlocated'], 1)

    def test_pagination_is_fixed_and_order_is_stable(self):
        for number in range(27):
            self.work(f'Book {number:02}')
        first = self.request({'page_size': 100})
        second = self.request({'page': 2})
        self.assertEqual(first.data['count'], 27)
        self.assertEqual(len(first.data['results']), 24)
        self.assertEqual(len(second.data['results']), 3)
        self.assertEqual(second.data['results'][0]['book']['title'], 'Book 24')
        self.assertIsNotNone(first.data['next'])
        self.assertIsNotNone(second.data['previous'])
        self.assertIsNone(second.data['next'])
        self.assertEqual(self.request({'page': 3}).status_code, 404)

    def test_invalid_filters_and_anonymous_private_overlays_are_rejected(self):
        for params in [{'century': '0'}, {'century': '1900'}, {'century': 'later'}, {'overlay': 'other'},
                       {'field': 'other'}, {'overlay': 'read'}, {'overlay': 'saved'}]:
            self.assertEqual(self.request(params).status_code, 400, params)
        request = self.factory.post('/api/catalog-atlas/', {})
        force_authenticate(request, user=self.user)
        self.assertEqual(catalog_atlas(request).status_code, 405)

    def test_card_queries_are_bounded_and_only_page_rows_are_loaded(self):
        for number in range(30):
            work = self.work(f'Work {number:02}', countries=['England'], original_year=1900)
            work.authors.add(Person.objects.create(name=f'Author {number:02}'))
        self.request(user=self.user)  # Public metadata cache may be warm on later pages.
        with CaptureQueriesContext(connection) as queries:
            response = self.request({'page': 2}, user=self.user)
        self.assertEqual(len(response.data['results']), 6)
        self.assertLessEqual(len(queries), 5, [row['sql'] for row in queries])
        work_queries = [row['sql'] for row in queries if 'FROM "core_work"' in row['sql']]
        self.assertEqual(len(work_queries), 1)

    def test_search_and_archiving_update_saved_catalog_results(self):
        work = self.work('Unusual matching title', countries=['Greece'], original_year=-400)
        self.work('Unrelated book')
        response = self.request({'q': 'unusual'})
        self.assertEqual([row['book']['id'] for row in response.data['results']], [work.pk])
        self.assertEqual(response.data['centuries'][0]['key'], '-4')
        work.is_archived = True
        work.save(update_fields=['is_archived'])
        self.assertEqual(self.request().data['count'], 1)
