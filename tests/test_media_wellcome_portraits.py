import copy
import unittest
from urllib.parse import parse_qs, urlsplit

from research import media_wellcome_portraits as source
from research.media_transport import ProviderOutage


class WellcomePortraitTests(unittest.TestCase):
    def setUp(self):
        self.person = {'title': 'Mungo Park', 'works': ['Travels in the Interior Districts of Africa']}
        self.subject = {'id': 'wwxwmdbc', 'type': 'Person', 'label': 'Mungo Park'}
        self.book = {'id': 'cnr6tz6p', 'title': 'Travels in the interior districts of Africa / [Mungo Park].',
                     'workType': {'id': 'a'}, 'contributors': [{'primary': True, 'roles': [], 'agent': self.subject}]}
        self.location = {'url': 'https://iiif.wellcomecollection.org/image/V0004485ER/info.json',
                         'credit': 'Wellcome Collection', 'license': {'id': 'pdm', 'label': 'Public Domain Mark',
                         'url': 'https://creativecommons.org/share-your-work/public-domain/pdm/'},
                         'accessConditions': [{'status': {'id': 'open'}}]}
        self.portrait = {'id': 'tbuzddup', 'title': 'Mungo Park. Line engraving after H. Edridge.',
                         'workType': {'id': 'k'}, 'subjects': [{'concepts': [self.subject]}],
                         'contributors': [{'agent': {'label': 'Henry Edridge'}}],
                         'items': [{'locations': [self.location]}]}
        self.calls = []

    def fetch(self, url, **kwargs):
        self.calls.append((url, kwargs))
        kind = parse_qs(urlsplit(url).query)['workType'][0]
        return {'results': [self.portrait if kind == 'k' else self.book]}

    def test_real_mungo_park_work_author_subject_and_item_rights(self):
        rows = source.candidates(self.person, self.fetch)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['source'], 'https://wellcomecollection.org/works/tbuzddup')
        self.assertEqual(rows[0]['image_url'], 'https://iiif.wellcomecollection.org/image/V0004485ER/full/600,/0/default.jpg')
        self.assertIn('Public Domain Mark', rows[0]['credit'])
        self.assertIn('Henry Edridge', rows[0]['credit'])
        self.assertIn('cnr6tz6p', rows[0]['identity_evidence'][0])
        self.assertEqual(len(self.calls), 2)
        self.assertTrue(all(kwargs['allowed_hosts'] == source.API_HOSTS for _, kwargs in self.calls))

    def test_namesake_and_wrong_work_rejected(self):
        self.book['contributors'][0]['agent'] = {**self.subject, 'id': 'xxxxxxxx'}
        self.assertEqual(source.candidates(self.person, self.fetch), [])
        self.book['contributors'][0]['agent'] = self.subject
        self.book['title'] = 'Unrelated travel book'
        self.assertEqual(source.candidates(self.person, self.fetch), [])

    def test_book_about_subject_and_translator_do_not_establish_authorship(self):
        self.book['contributors'][0]['roles'] = [{'label': 'translator'}]
        self.assertEqual(source.candidates(self.person, self.fetch), [])
        self.book['contributors'] = []
        self.book['subjects'] = [{'concepts': [self.subject]}]
        self.assertEqual(source.candidates(self.person, self.fetch), [])

    def test_just_a_matching_name_cannot_accept_portrait(self):
        self.assertEqual(source.candidates({**self.person, 'works': []}, self.fetch), [])

    def test_group_and_building_and_author_book_images_rejected(self):
        original = copy.deepcopy(self.portrait)
        for title in ['The house of Mungo Park. Photograph.', 'Mungo Park and his companions.', 'Mungo Park: his travels.']:
            self.portrait['title'] = title
            self.assertEqual(source.candidates(self.person, self.fetch), [])
        self.portrait = copy.deepcopy(original)
        self.portrait['subjects'][0]['concepts'].append({'id': 'another1', 'label': 'Another Person', 'type': 'Person'})
        self.assertEqual(source.candidates(self.person, self.fetch), [])
        self.portrait = copy.deepcopy(original)
        self.portrait['workType'] = {'id': 'a'}
        self.assertEqual(source.candidates(self.person, self.fetch), [])

    def test_restricted_or_unknown_rights_are_not_downloaded(self):
        for license_id in ['inc', 'unknown', 'cc-by-nc', '']:
            self.location['license']['id'] = license_id
            self.assertEqual(source.candidates(self.person, self.fetch), [])
        self.location['license']['id'] = 'pdm'
        self.location['accessConditions'] = [{'status': {'id': 'restricted'}}]
        self.assertEqual(source.candidates(self.person, self.fetch), [])

    def test_no_external_host_or_credentials_or_manifest_used_as_image(self):
        for url in ['https://iiif.wellcomecollection.org.evil.test/image/X/info.json',
                    'https://user:secret@iiif.wellcomecollection.org/image/X/info.json',
                    'https://iiif.wellcomecollection.org/image/X/info.json?token=secret',
                    'https://iiif.wellcomecollection.org/presentation/v2/b123',
                    'https://iiif.wellcomecollection.org:444/image/X/info.json']:
            self.location['url'] = url
            self.assertEqual(source.candidates(self.person, self.fetch), [])

    def test_picture_thumbnail_is_usable_but_generic_scan_thumbnail_is_not(self):
        self.portrait['items'] = []
        self.portrait['thumbnail'] = {**self.location, 'url': 'https://iiif.wellcomecollection.org/image/V0004485ER/full/300,/0/default.jpg'}
        self.assertEqual(len(source.candidates(self.person, self.fetch)), 1)
        self.portrait['thumbnail']['url'] = 'https://iiif.wellcomecollection.org/thumbs/book_0001.jp2/full/!200,200/0/default.jpg'
        self.assertEqual(source.candidates(self.person, self.fetch), [])

    def test_requests_are_bounded_and_provider_outage_propagates(self):
        source.candidates({**self.person, 'works': ['A', 'B', 'C', 'D']}, self.fetch)
        self.assertEqual(len(self.calls), 3)
        def down(url, **kwargs):
            raise ProviderOutage('rate limited')
        with self.assertRaises(ProviderOutage):
            source.candidates(self.person, down)

    def test_empty_picture_search_does_not_query_book_catalog(self):
        self.portrait['subjects'] = []
        self.assertEqual(source.candidates(self.person, self.fetch), [])
        self.assertEqual(len(self.calls), 1)


if __name__ == '__main__':
    unittest.main()
