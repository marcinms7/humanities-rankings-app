from types import SimpleNamespace
import unittest

from research.enrich_media_alternatives import portrait_lookup_item


class PortraitAliasIntegrationTests(unittest.TestCase):
    def test_aliases_are_separate_from_transactional_catalog_titles(self):
        works = [SimpleNamespace(pk=7, title='Canonical Title', is_archived=False),
                 SimpleNamespace(pk=8, title='Archived Title', is_archived=True)]
        person = SimpleNamespace(pk=11, name='Jane Writer', source_url='', biography='',
                                 works=SimpleNamespace(all=lambda: works))
        aliases = {'works': {'7': ['Reviewed Title'], '8': ['Archived Alias']}, 'people': {}}
        item = portrait_lookup_item(person, aliases)
        self.assertEqual(item['works'], ['Canonical Title'])
        self.assertEqual(item['authors'], ['Canonical Title'])
        self.assertEqual(item['work_aliases'], {'Canonical Title': ['Reviewed Title']})
        self.assertNotIn('work_aliases', portrait_lookup_item(person))
