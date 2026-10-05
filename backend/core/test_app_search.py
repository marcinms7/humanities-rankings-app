"""App navigation search is bounded and never searches other readers' content."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .app_search import AppSearchResponseSerializer
from .management.commands.export_frontend_contracts import schema_object
from .models import ClassicalStudyProfile, LibraryItem, Person, Ranking, ResearchSource, Work
from .search import rebuild_index
from .test_api_contracts import assert_shape


class AppSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user('search-owner', is_staff=True)
        cls.reader = get_user_model().objects.create_user('search-reader')
        cls.staff = get_user_model().objects.create_user('search-staff', is_staff=True)
        cls.person = Person.objects.create(name='Pláto')
        cls.book = Work.objects.create(title='Republic')
        cls.book.authors.add(cls.person)
        cls.archived = Work.objects.create(title='Plato archived book', is_archived=True)
        cls.hidden_person = Person.objects.create(name='Plato archived person', is_archived=True)
        cls.researched = Ranking.objects.create(slug='search-researched', title='Guardian researched choices', is_public=True)
        cls.published = Ranking.objects.create(slug='search-published', title='Guardian original order',
            origin='external', presentation='ranked', is_public=True)
        cls.collection = Ranking.objects.create(slug='search-collection', title='Guardian reading collection',
            origin='external', presentation='unranked', is_public=True)
        cls.sequence = Ranking.objects.create(slug='search-sequence', title='Guardian reading sequence',
            origin='external', presentation='reading_sequence', is_public=True)
        cls.unpublished = Ranking.objects.create(slug='search-unpublished', title='Guardian unpublished')
        cls.archived_ranking = Ranking.objects.create(slug='search-archived', title='Guardian archived', is_public=True, is_archived=True)
        cls.personal = Ranking.objects.create(slug='search-personal', title='Guardian my personal list',
            origin='personal', owner=cls.reader)
        cls.foreign = Ranking.objects.create(slug='search-foreign', title='Guardian other reader secret',
            origin='personal', owner=cls.owner, sharing_enabled=True)
        cls.source = ResearchSource.objects.create(ranking=cls.published, source_id='guardian-public',
            underlying_source_id='guardian-public', title='Guardian source record', url='https://example.test/list?a=1&b=2', family='publisher')
        ResearchSource.objects.create(ranking=cls.foreign, source_id='guardian-private',
            underlying_source_id='guardian-private', title='Guardian private source', url='https://example.test/private', family='publisher')
        ResearchSource.objects.create(ranking=cls.archived_ranking, source_id='guardian-archived',
            underlying_source_id='guardian-archived', title='Guardian archived source', url='https://example.test/archived', family='publisher')
        LibraryItem.objects.create(user=cls.reader, work=cls.book, notes='onlyprivatekeyword')

    def setUp(self):
        self.client = APIClient()
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        aliases = Path(directory.name) / 'aliases.json'
        aliases.write_text(json.dumps({'works': {}, 'people': {str(self.person.pk): ['Plato']}}))
        settings = override_settings(CATALOG_SEARCH_INDEX=Path(directory.name) / 'search.sqlite3',
                                     CATALOG_SEARCH_ALIASES=aliases)
        settings.enable()
        self.addCleanup(settings.disable)
        rebuild_index()

    def search(self, query, user=None):
        self.client.force_authenticate(user)
        response = self.client.get('/api/app-search/', {'q': query})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        assert_shape(self, schema_object(AppSearchResponseSerializer()), response.json())
        return {group['key']: group for group in response.data['groups']}

    def test_anonymous_search_keeps_discovery_sections_distinct_and_private_content_hidden(self):
        groups = self.search('Guardian')
        self.assertEqual(set(groups), {'researched', 'published', 'collections'})
        self.assertEqual([row['id'] for row in groups['published']['items']], [str(self.published.pk)])
        self.assertEqual({row['id'] for row in groups['collections']['items']}, {str(self.collection.pk), str(self.sequence.pk)})
        all_ids = {row['id'] for group in groups.values() for row in group['items']}
        self.assertNotIn(str(self.unpublished.pk), all_ids)
        self.assertNotIn(str(self.archived_ranking.pk), all_ids)

    def test_indexed_book_author_alias_search_rechecks_archives(self):
        groups = self.search('Plato')
        self.assertEqual([row['id'] for row in groups['books']['items']], [str(self.book.pk)])
        self.assertEqual(groups['books']['items'][0]['subtitle'], 'Pláto')
        self.assertEqual([row['id'] for row in groups['authors']['items']], [str(self.person.pk)])
        self.assertEqual(groups['authors']['more_href'], '#/authors?q=Plato')
        self.book.is_archived = True
        self.book.save(update_fields=['is_archived'])
        self.assertNotIn('books', self.search('Plato'))

    def test_personal_lists_only_appear_for_their_owner_even_if_share_link_enabled(self):
        groups = self.search('Guardian', self.reader)
        self.assertEqual([row['id'] for row in groups['personal']['items']], [str(self.personal.pk)])
        staff_groups = self.search('Guardian', self.staff)
        self.assertNotIn('personal', staff_groups)
        self.assertNotIn('other reader secret', json.dumps(staff_groups))

    def test_sources_link_to_exact_target_and_url_without_exposing_private_or_archived_ledgers(self):
        groups = self.search('Guardian', self.reader)
        rows = groups['sources']['items']
        self.assertEqual([row['id'] for row in rows], [str(self.source.pk)])
        fragment = urlsplit(rows[0]['href']).fragment
        route, query = fragment.split('?')
        self.assertEqual(route, '/sources')
        self.assertEqual(parse_qs(query), {'ranking': [str(self.published.pk)], 'url': [self.source.url]})
        self.assertEqual(groups['sources']['more_href'], '#/sources?search=Guardian')

    def test_private_notes_are_never_searchable_for_any_account(self):
        for user in (None, self.reader, self.owner, self.staff):
            self.assertEqual(self.search('onlyprivatekeyword', user), {})

    def test_owner_study_search_reads_real_static_content_without_creating_profile(self):
        self.assertFalse(ClassicalStudyProfile.objects.exists())
        module_groups = self.search('Plato', self.owner)
        self.assertIn('study', module_groups)
        self.assertTrue(any('?module=' in row['href'] for row in module_groups['study']['items']))
        glossary = self.search('arete', self.owner)['study']['items']
        self.assertTrue(any(row['href'].endswith('tab=glossary&term=arete') for row in glossary))
        desk = self.search('Reading desk', self.owner)['study']['items']
        self.assertEqual(desk[0]['href'], '#/classical-education?tab=desk')
        self.assertFalse(ClassicalStudyProfile.objects.exists())

    def test_study_is_unavailable_to_other_readers_including_staff(self):
        for user in (None, self.reader, self.staff):
            self.assertNotIn('study', self.search('Reading desk', user))

    def test_each_group_is_bounded_with_continuation_not_fake_counts(self):
        for index in range(8):
            Work.objects.create(title=f'Bounded fixture {index}')
        rebuild_index()
        group = self.search('Bounded')['books']
        self.assertEqual(len(group['items']), 5)
        self.assertTrue(group['has_more'])
        self.assertEqual(group['more_href'], '#/catalog?q=Bounded')
        self.assertFalse(self.search('Republic')['books']['has_more'])

    def test_empty_and_punctuation_queries_do_not_dump_the_catalog(self):
        for query in ('', '   ', '"*()'):
            self.assertEqual(self.search(query, self.owner), {})
        response = self.client.get('/api/app-search/', {'q': 'x' * 400})
        self.assertEqual(len(response.data['query']), 300)

    def test_search_is_read_only(self):
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.post('/api/app-search/', {'q': 'Plato'}).status_code, 405)
