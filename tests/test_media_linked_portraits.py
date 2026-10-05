import unittest
from unittest.mock import patch

from research import media_linked_portraits as linked
from research.media_transport import ProviderOutage


class LinkedPortraitTests(unittest.TestCase):
    def item(self):
        return {'title': 'Samuel Butler', 'linked_works': [
            {'title': 'The Way of All Flesh', 'source_urls': ['https://openlibrary.org/works/OL22372W']} ]}

    def work(self):
        return {'title': 'The way of all flesh', 'authors': [{'author': {'key': '/authors/OL24761A'}}]}

    def author(self):
        return {'name': 'Samuel Butler', 'photos': [7063387], 'remote_ids': {'wikidata': 'Q312829'}}

    def claim(self, value):
        return {'mainsnak': {'datavalue': {'value': value}}}

    def entity(self):
        return {'entities': {'Q312829': {'claims': {
            'P31': [self.claim({'id': 'Q5'})], 'P648': [self.claim('OL24761A')],
            'P18': [self.claim('Butler.jpg')]}}}}

    def image(self):
        return {'query': {'pages': [{'imageinfo': [{
            'thumburl': 'https://upload.wikimedia.org/butler.jpg',
            'descriptionurl': 'https://commons.wikimedia.org/wiki/File:Butler.jpg',
            'extmetadata': {'LicenseShortName': {'value': 'Public domain'}}}]}]}}

    def test_verified_work_link_avoids_ambiguous_name_search(self):
        with patch.object(linked, 'fetch_json', side_effect=[self.work(), self.author()]) as fetch:
            candidates = linked.openlibrary_candidates(self.item())
        self.assertEqual(candidates[0]['matched_works'], ['The Way of All Flesh'])
        self.assertEqual(candidates[0]['author_key'], 'OL24761A')
        self.assertFalse(any('search' in call.args[0] for call in fetch.call_args_list))

    def test_saved_work_id_does_not_override_wrong_title(self):
        with patch.object(linked, 'fetch_json', return_value={**self.work(), 'title': 'Hudibras'}) as fetch:
            self.assertEqual(linked.openlibrary_candidates(self.item()), [])
        self.assertEqual(fetch.call_count, 1)

    def test_coauthor_with_wrong_name_never_supplies_portrait(self):
        with patch.object(linked, 'fetch_json', side_effect=[self.work(), {**self.author(), 'name': 'Someone Else'}]):
            self.assertEqual(linked.openlibrary_candidates(self.item()), [])

    def test_wrong_source_hostname_is_not_requested(self):
        item = self.item()
        item['linked_works'][0]['source_urls'] = ['https://openlibrary.org.evil.test/works/OL22372W']
        with patch.object(linked, 'fetch_json') as fetch:
            self.assertEqual(linked.openlibrary_candidates(item), [])
        fetch.assert_not_called()

    def test_two_distinct_same_name_authors_are_not_guessed(self):
        work = self.work()
        work['authors'].append({'author': {'key': '/authors/OL999A'}})
        with patch.object(linked, 'fetch_json', side_effect=[work, self.author(), self.author()]):
            self.assertEqual(linked.openlibrary_candidates(self.item()), [])

    def test_linked_wikidata_requires_human_and_retains_rights(self):
        with patch.object(linked, 'fetch_json', side_effect=[self.work(), self.author(), self.entity(), self.image()]):
            candidates = linked.wikidata_candidates(self.item())
        self.assertEqual(candidates[0]['wikidata'], 'Q312829')
        self.assertIn('Public domain', candidates[0]['credit'])
        self.assertEqual(candidates[0]['matched_works'], ['The Way of All Flesh'])

    def test_conflicting_reciprocal_id_is_rejected(self):
        entity = self.entity()
        entity['entities']['Q312829']['claims']['P648'] = [self.claim('OL999A')]
        with patch.object(linked, 'fetch_json', side_effect=[self.work(), self.author(), entity]) as fetch:
            self.assertEqual(linked.wikidata_candidates(self.item()), [])
        self.assertEqual(fetch.call_count, 3)

    def test_nonhuman_entity_never_supplies_portrait(self):
        entity = self.entity()
        entity['entities']['Q312829']['claims']['P31'] = [self.claim({'id': 'Q11424'})]
        with patch.object(linked, 'fetch_json', side_effect=[self.work(), self.author(), entity]):
            self.assertEqual(linked.wikidata_candidates(self.item()), [])

    def test_missing_reciprocal_id_needs_matching_name(self):
        entity = self.entity()
        entity['entities']['Q312829']['claims'].pop('P648')
        with patch.object(linked, 'fetch_json', side_effect=[self.work(), self.author(), entity]):
            self.assertEqual(linked.wikidata_candidates(self.item()), [])
        entity['entities']['Q312829']['labels'] = {'en': {'value': 'Samuel Butler'}}
        with patch.object(linked, 'fetch_json', side_effect=[self.work(), self.author(), entity, self.image()]):
            self.assertTrue(linked.wikidata_candidates(self.item()))

    def test_outage_propagates_without_exhausting_author_identity(self):
        with patch.object(linked, 'fetch_json', side_effect=ProviderOutage('HTTP 429')):
            with self.assertRaises(ProviderOutage):
                linked.openlibrary_candidates(self.item())
