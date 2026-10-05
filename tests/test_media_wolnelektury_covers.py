import copy
import unittest
from unittest.mock import Mock, patch

from research import media_wolnelektury_covers as wl
from research.media_transport import CandidateRejected, ProviderOutage


class WolneLekturyCoverTests(unittest.TestCase):
    def setUp(self):
        wl._catalogue_cache = None
        self.item = {'id': 1, 'title': 'Pożegnanie z Marią', 'authors': ['Tadeusz Borowski'],
                     'provider_identifiers': {}, 'edition_id': 42}
        self.row = {'title': self.item['title'], 'author': 'Tadeusz Borowski', 'slug': 'borowski',
                    'href': 'https://wolnelektury.pl/api/books/borowski/',
                    'url': 'https://wolnelektury.pl/katalog/lektura/borowski/'}
        self.detail = {'title': self.row['title'], 'url': self.row['url'],
                       'authors': [{'name': 'Tadeusz Borowski'}], 'parent': None, 'preview': False,
                       'cover': 'https://wolnelektury.pl/media/book/cover/borowski.jpg',
                       'simple_cover': 'https://wolnelektury.pl/media/book/cover_simple/borowski_abc.jpg',
                       'xml': 'https://wolnelektury.pl/media/book/xml/borowski.xml'}
        self.xml = '''<utwor><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
          <rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/">
            <dc:title>Pożegnanie z Marią</dc:title><dc:creator>Borowski, Tadeusz</dc:creator>
            <dc:rights>Domena publiczna</dc:rights>
            <dc:relation.coverImage.attribution>Bez tytułu, Teresa Żarnowerówna, domena publiczna</dc:relation.coverImage.attribution>
          </rdf:Description></rdf:RDF></utwor>'''
        self.text_fetch = Mock(return_value=self.xml)
        self.fetch = Mock(side_effect=self._fetch)

    def tearDown(self):
        wl._catalogue_cache = None

    def _fetch(self, url, **kwargs):
        return [self.row] if url == wl.CATALOGUE_URL else self.detail

    def test_bulk_preparation_preserves_fingerprint_and_reuses_index(self):
        original = copy.deepcopy(self.item)
        prepared = wl.prepare_items([self.item, {**self.item, 'title': 'Another work'}], fetch=self.fetch)
        self.assertEqual(prepared, [original])
        wl.candidates(prepared[0], fetch=self.fetch, text_fetch=self.text_fetch)
        wl.candidates(self.item, fetch=self.fetch, text_fetch=self.text_fetch)
        self.assertEqual(sum(call.args[0] == wl.CATALOGUE_URL for call in self.fetch.call_args_list), 1)
        self.assertEqual(self.item, original)

    def test_exact_complete_author_and_title_are_required(self):
        for change in ({'authors': ['Borowski']}, {'authors': ['Another Borowski']},
                       {'title': 'Pożegnanie'}, {'title': 'Farewell to Maria'}):
            self.assertEqual(wl.prepare_items([{**self.item, **change}], fetch=self.fetch), [])
        self.assertEqual(self.fetch.call_count, 1)

    def test_only_supplied_reviewed_aliases_expand_matching(self):
        item = {**self.item, 'title': 'Farewell to Maria', 'title_aliases': [self.item['title']],
                'authors': ['Reviewed Pen Name'], 'author_aliases': self.item['authors']}
        self.assertEqual(wl.prepare_items([item], fetch=self.fetch), [item])
        self.assertEqual(wl.candidates(item, fetch=self.fetch, text_fetch=self.text_fetch)[0]['matched_title'],
                         self.item['title'])

    def test_unmatched_item_does_not_fetch_details(self):
        self.assertEqual(wl.candidates({**self.item, 'title': 'Unknown'}, fetch=self.fetch), [])
        self.assertEqual(self.fetch.call_count, 1)

    def test_child_story_and_preview_are_not_whole_work_covers(self):
        for change in ({'parent': {'title': 'Collected stories'}}, {'preview': True}):
            self.detail.update(change)
            self.assertEqual(wl.candidates(self.item, fetch=self.fetch, text_fetch=self.text_fetch), [])
            self.detail.update(parent=None, preview=False)
        self.text_fetch.assert_not_called()

    def test_same_named_collection_can_follow_rejected_child(self):
        child = {**self.row, 'href': self.row['href'] + 'story/'}
        fetch = Mock(side_effect=lambda url, **kw: [child, self.row] if url == wl.CATALOGUE_URL else
                     {**self.detail, 'parent': {'title': self.item['title']}} if url == child['href'] else self.detail)
        self.assertEqual(len(wl.candidates(self.item, fetch=fetch, text_fetch=self.text_fetch)), 1)
        self.assertEqual(fetch.call_count, 3)

    def test_malformed_catalogue_is_outage_never_global_negative(self):
        for data in (None, {}, [], [None], [{**self.row, 'href': None}]):
            with self.subTest(data=data), self.assertRaises(ProviderOutage):
                wl.prepare_items([self.item], fetch=Mock(return_value=data))
        # Real anonymous rows do not prevent unrelated complete identities.
        fetch = Mock(return_value=[self.row, {**self.row, 'author': None}])
        self.assertEqual(wl.prepare_items([self.item], fetch=fetch), [self.item])

    def test_partial_detail_is_deferred(self):
        for key in ('parent', 'preview', 'authors', 'cover'):
            incomplete = {k: v for k, v in self.detail.items() if k != key}
            fetch = Mock(side_effect=lambda url, **kw: [self.row] if url == wl.CATALOGUE_URL else incomplete)
            with self.subTest(key=key), self.assertRaises(ProviderOutage):
                wl.candidates(self.item, fetch=fetch, text_fetch=self.text_fetch)

    def test_changed_detail_identity_does_not_use_cover(self):
        self.detail['authors'] = [{'name': 'Another Writer'}]
        self.assertEqual(wl.candidates(self.item, fetch=self.fetch, text_fetch=self.text_fetch), [])
        self.text_fetch.assert_not_called()

    def test_advertised_cover_and_artwork_credit_preserved_without_license_guess(self):
        candidate = wl.candidates(self.item, fetch=self.fetch, text_fetch=self.text_fetch)[0]
        self.assertEqual(candidate['image_url'], self.detail['cover'])
        self.assertEqual(candidate['cover_basis'], 'representative_work')
        self.assertEqual(candidate['cover_kind'], 'library_generated_digital_edition')
        self.assertIn('Teresa Żarnowerówna', candidate['credit'])
        self.assertIn('Cover-design rights: see source', candidate['credit'])
        self.assertEqual(candidate['text_rights'], 'Domena publiczna')
        self.assertNotIn('license', candidate)
        self.assertTrue(candidate['image_respect_robots'])
        self.assertTrue(self.text_fetch.call_args.kwargs['respect_robots'])

    def test_external_or_non_cover_image_never_fetched(self):
        for image in ('https://evil.example/cover.jpg', 'https://wolnelektury.pl/media/portrait.jpg'):
            self.detail['cover'] = image
            with self.subTest(image=image), self.assertRaises(CandidateRejected):
                wl.candidates(self.item, fetch=self.fetch, text_fetch=self.text_fetch)
        self.text_fetch.assert_not_called()

    def test_unlettered_artwork_is_not_substituted_for_a_missing_full_cover(self):
        self.detail['cover'] = None
        self.assertEqual(wl.candidates(self.item, fetch=self.fetch, text_fetch=self.text_fetch), [])
        self.text_fetch.assert_not_called()

    def test_broken_or_wrong_attribution_is_deferred(self):
        for xml in ('<utwor>', '<utwor/>', self.xml.replace('Pożegnanie z Marią', 'Another Book'),
                    '<!DOCTYPE utwor [<!ENTITY bad "bad">]>' + self.xml):
            with self.subTest(xml=xml[:30]), self.assertRaises(ProviderOutage):
                wl.candidates(self.item, fetch=self.fetch, text_fetch=Mock(return_value=xml))

    def test_catalogue_memory_cache_respects_original_response_age(self):
        with patch.object(wl, 'fetch_json', self.fetch), patch.object(wl.time, 'time', return_value=100000), \
                patch.object(wl, 'response_cache_timestamp', return_value=100000 - wl.TTL + 1):
            wl.prepare_items([self.item])
        with patch.object(wl, 'fetch_json', self.fetch), patch.object(wl.time, 'time', return_value=100002), \
                patch.object(wl, 'response_cache_timestamp', return_value=100002):
            wl.prepare_items([self.item])
        self.assertEqual(self.fetch.call_count, 2)

    def test_provider_outage_is_not_cached_as_empty_catalogue(self):
        fetch = Mock(side_effect=[ProviderOutage('Cooling'), [self.row]])
        with self.assertRaises(ProviderOutage):
            wl.prepare_items([self.item], fetch=fetch)
        self.assertEqual(wl.prepare_items([self.item], fetch=fetch), [self.item])


if __name__ == '__main__':
    unittest.main()
