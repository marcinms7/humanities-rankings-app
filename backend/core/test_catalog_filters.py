"""Catalog toggles must count distinct final results and preserve owned presets."""
import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.http import QueryDict
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from .catalog_filters import CatalogFacetsSerializer, catalog_base, catalog_facets, apply_catalog_selections
from .management.commands.export_frontend_contracts import schema_object
from .models import Edition, LibraryItem, SavedDiscoveryFilter, Tag, Work
from .test_api_contracts import assert_shape


class CatalogFilterTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user('filter-reader')
        self.other = get_user_model().objects.create_user('other-filter-reader')
        self.france = Work.objects.create(title='French book', countries=['France', 'France'])
        self.russia = Work.objects.create(title='Russian essay', countries=['Russia'], form='essay')
        self.both = Work.objects.create(title='Both places', countries=['France', 'Russia'], field='philosophy')
        self.comma = Work.objects.create(title='Comma association', countries=['France, Russia'])
        self.unknown = Work.objects.create(title='Unknown location', countries=[])
        self.historical, _ = Tag.objects.get_or_create(name='Historical Fiction', defaults={'kind': 'genre'})
        self.satire, _ = Tag.objects.get_or_create(name='Satire', defaults={'kind': 'genre'})
        self.france.tags.add(self.historical, self.satire)
        self.russia.tags.add(self.satire)
        self.both.tags.add(self.historical)

    def params(self, values):
        query = QueryDict('', mutable=True)
        for key, value in values.items():
            query[key] = json.dumps(value) if isinstance(value, list) else str(value)
        return query

    def ids(self, values, user=None):
        works, selections = catalog_base(Work.objects.filter(is_archived=False), user or AnonymousUser(), self.params(values))
        return list(apply_catalog_selections(works, selections).values_list('pk', flat=True))

    def facets(self, values=None, user=None):
        works, selections = catalog_base(Work.objects.filter(is_archived=False), user or AnonymousUser(), self.params(values or {}))
        return catalog_facets(works, selections)

    def test_or_within_facets_and_across_facets_never_duplicates_books(self):
        ids = self.ids({'country_any': ['France', 'Russia'], 'genre_any': ['Satire', 'Historical Fiction']})
        self.assertEqual(set(ids), {self.france.pk, self.russia.pk, self.both.pk})
        self.assertEqual(len(ids), 3)
        self.assertEqual(self.ids({'country_any': ['France', 'Russia'], 'genre_any': ['Historical Fiction'],
                                   'field_any': ['literature'], 'form_any': ['book', 'essay']}), [self.france.pk])

    def test_excluding_any_membership_removes_the_whole_book(self):
        self.assertEqual(self.ids({'country_any': ['France'], 'country_not': ['Russia']}), [self.france.pk])
        self.assertEqual(self.ids({'genre_any': ['Historical Fiction'], 'genre_not': ['Satire']}), [self.both.pk])
        self.assertEqual(set(self.ids({'country_not': ['France', 'Russia']})), {self.comma.pk, self.unknown.pk})

    def test_comma_labels_and_legacy_single_links_are_exact(self):
        self.assertEqual(self.ids({'country_any': ['France, Russia']}), [self.comma.pk])
        self.assertEqual(set(self.ids({'country': 'France'})), {self.france.pk, self.both.pk})
        self.assertEqual(self.ids({'field': 'philosophy', 'genre': 'Historical Fiction'}), [self.both.pk])
        self.assertEqual(self.ids({'country': 'France', 'country_any': ['Russia']}), [self.both.pk, self.russia.pk])

    def test_saved_filters_inherit_facets_and_explicit_empty_overrides_preserve_private_constraints(self):
        for work in (self.france, self.russia, self.both):
            edition = Edition.objects.create(work=work, pages=100)
            work.default_edition = edition
            work.save(update_fields=['default_edition'])
        LibraryItem.objects.create(user=self.user, work=self.france, status='finished')
        preset = SavedDiscoveryFilter.objects.create(user=self.user, name='Unread French books',
            filters={'country': 'France', 'max_pages': 150, 'unread': 'yes'})
        base = {'saved_filter': preset.pk}
        self.assertEqual(self.ids(base, self.user), [self.both.pk])
        result = self.facets(base, self.user)
        self.assertTrue(result['facets']['country']['inherited'])
        self.assertEqual(result['facets']['country']['include'], ['France'])
        self.assertEqual(set(self.ids({**base, 'country_any': []}, self.user)), {self.both.pk, self.russia.pk})
        self.assertEqual(self.ids({**base, 'country_any': ['Russia'], 'field_any': ['literature']}, self.user), [self.russia.pk])

    def test_every_prospective_count_matches_the_actual_toggled_query(self):
        parameters = {'country_any': ['France'], 'genre_any': ['Historical Fiction', 'Satire'],
                      'form_not': ['essay']}
        response = self.facets(parameters)
        self.assertEqual(response['result_count'], len(self.ids(parameters)))
        for name, facet in response['facets'].items():
            for option in facet['options']:
                for mode in ('include', 'exclude'):
                    with self.subTest(facet=name, value=option['value'], toggle=mode):
                        include, exclude = set(facet['include']), set(facet['exclude'])
                        target, opposite = (include, exclude) if mode == 'include' else (exclude, include)
                        if option['value'] in target:
                            target.remove(option['value'])
                        else:
                            target.add(option['value'])
                            opposite.discard(option['value'])
                        changed = {**parameters, f'{name}_any': list(include), f'{name}_not': list(exclude)}
                        self.assertEqual(option[f'{mode}_count'], len(self.ids(changed)))

    def test_preset_prospective_counts_include_private_restrictions(self):
        LibraryItem.objects.create(user=self.user, work=self.france, status='finished')
        preset = SavedDiscoveryFilter.objects.create(user=self.user, name='Unread France',
            filters={'country': 'France', 'unread': 'yes'})
        base = {'saved_filter': preset.pk}
        data = self.facets(base, self.user)
        russia = next(row for row in data['facets']['country']['options'] if row['value'] == 'Russia')
        self.assertEqual(russia['include_count'], len(self.ids({**base, 'country_any': ['France', 'Russia']}, self.user)))
        self.assertEqual(russia['exclude_count'], 0)

    def test_archived_content_and_invalid_country_metadata_do_not_inflate_counts(self):
        Work.objects.create(title='Archived country', is_archived=True, countries=['Hidden'])
        Work.objects.create(title='Invalid object', countries={'country': 'France'})
        Work.objects.create(title='Invalid scalar', countries='France')
        archived = Tag.objects.create(name='Hidden genre', kind='genre', is_archived=True)
        self.france.tags.add(archived)
        data = self.facets({'country_any': ['France']})
        self.assertEqual(data['result_count'], 2)
        self.assertEqual(len(self.ids({'country_any': ['France']})), 2)
        self.assertNotIn('Hidden genre', data['genres'])
        self.assertNotIn('Hidden', [row['value'] for row in data['facets']['country']['options']])
        self.assertEqual(self.ids({'genre_any': ['Hidden genre']}), [])

    def test_missing_selected_value_is_still_removable_and_has_correct_count(self):
        data = self.facets({'country_any': ['Unrecorded']})
        option = next(row for row in data['facets']['country']['options'] if row['value'] == 'Unrecorded')
        self.assertEqual(data['result_count'], 0)
        self.assertEqual(option['include_count'], 5)
        self.assertEqual(option['exclude_count'], 5)

    def test_facet_queries_are_constant_for_many_country_labels(self):
        Work.objects.create(title='Many associations', countries=[f'Association {n}' for n in range(500)])
        works, selections = catalog_base(Work.objects.filter(is_archived=False), AnonymousUser(), self.params({}))
        with CaptureQueriesContext(connection) as captured:
            data = catalog_facets(works, selections)
        self.assertEqual(len(captured), 2)
        self.assertEqual(len(data['facets']['country']['options']), 503)
        assert_shape(self, schema_object(CatalogFacetsSerializer()), data)

    def test_legacy_facets_remain_field_specific_and_expanded_options_offer_other_fields(self):
        data = self.facets({'field': 'philosophy'})
        self.assertEqual(data['genres'], ['Historical Fiction'])
        self.assertEqual(data['countries'], ['France', 'Russia'])
        self.assertEqual(data['genre_catalog'], Tag.GENRES)
        self.assertIn('literature', [row['value'] for row in data['facets']['field']['options']])

    def test_list_and_facets_endpoints_enforce_preset_ownership(self):
        preset = SavedDiscoveryFilter.objects.create(user=self.user, name='Private', filters={'country': 'France'})
        for endpoint in ('/api/works/', '/api/works/facets/'):
            with self.subTest(endpoint=endpoint):
                self.client.force_authenticate(None)
                self.assertEqual(self.client.get(endpoint, {'saved_filter': preset.pk}).status_code, 403)
                self.client.force_authenticate(self.other)
                self.assertEqual(self.client.get(endpoint, {'saved_filter': preset.pk}).status_code, 404)
                self.client.force_authenticate(self.user)
                self.assertEqual(self.client.get(endpoint, {'saved_filter': preset.pk}).status_code, 200)

    def test_invalid_and_conflicting_arrays_fail_without_ignoring_filters(self):
        cases = ({'country_any': 'France,Russia'}, {'country_any': '{}'},
                 {'country_any': '[1]'}, {'country_any': json.dumps(['France'] * 51)},
                 {'field_any': '["not-a-subject"]'},
                 {'country_any': '["France"]', 'country_not': '["France"]'})
        for values in cases:
            for endpoint in ('/api/works/', '/api/works/facets/'):
                with self.subTest(endpoint=endpoint, values=values):
                    self.assertEqual(self.client.get(endpoint, values).status_code, 400)

    def test_paged_endpoint_and_facet_total_agree(self):
        values = {'country_any': '["France","Russia"]', 'genre_any': '["Satire","Historical Fiction"]'}
        response = self.client.get('/api/works/', {**values, 'compact': '1', 'page_size': 1})
        facets = self.client.get('/api/works/facets/', values)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 3)
        self.assertEqual(response.data['count'], facets.data['result_count'])
        self.assertEqual(len(response.data['results']), 1)
        self.assertIn('page=2', response.data['next'])
