import unittest
from unittest.mock import patch

from research import media_nobel_portraits as sources
from research.media_transport import CandidateRejected


class NobelPortraitTests(unittest.TestCase):
    source = 'https://www.nobelprize.org/prizes/literature/2009/muller/facts/'
    image = 'https://www.nobelprize.org/images/muller-12800-portrait-medium.jpg'
    person = {'title': 'Herta Müller', 'works': ['The Land of Green Plums']}

    def record(self, **extra):
        return {'id': '844', 'gender': 'female', 'knownName': {'en': 'Herta Müller'},
                'fullName': {'en': 'Herta Müller'}, 'nobelPrizes': [{'awardYear': '2009',
                    'links': [{'href': self.source}]}], **extra}

    def page(self, text='The Land of Green Plums (1996)', name='Herta Müller',
             credit='© The Nobel Foundation. Photo: U. Montan', image=None, after=''):
        return f'''<main><section class="page-section laureate-facts laur-844">
        <h1>{name}</h1><div class="image"><picture><img src="{image or self.image}" alt="{name}"></picture>
        <figcaption><p class="figcaption__attribution">{credit}</p></figcaption></div>
        <a href="{self.source.replace('facts/', 'bibliography/')}">Bibliography</a>
        <article class="page-content facts">{text}</article></section>{after}</main>'''.encode()

    def fetcher(self, *responses):
        self.calls = []
        responses = iter(responses)
        def fetch(url, **kwargs):
            self.calls.append((url, kwargs))
            result = next(responses)
            if isinstance(result, Exception):
                raise result
            return result
        return fetch

    def test_live_shape_preserves_credit_work_and_robots(self):
        rows = sources.candidates(self.person, self.fetcher({'laureates': [self.record()]}, self.page()))
        self.assertEqual(rows[0]['image_url'], self.image)
        self.assertEqual(rows[0]['matched_works'], ['The Land of Green Plums'])
        self.assertIn('Photo: U. Montan', rows[0]['credit'])
        self.assertTrue(rows[0]['image_respect_robots'])
        self.assertTrue(self.calls[1][1]['respect_robots'])

    def test_ambiguous_and_partial_name_not_accepted(self):
        records = [self.record(), self.record(id='999')]
        self.assertEqual(sources.candidates(self.person, self.fetcher({'laureates': records})), [])
        self.assertEqual(sources.candidates({'title': 'Müller'}, self.fetcher({'laureates': [self.record()]})), [])

    def test_bibliography_work_corroborates_same_laureate(self):
        bibliography = b'<main><h1>Herta M\xc3\xbcller</h1><article class="page-content entry-content"><em>The Land of Green Plums</em> / translated by Michael Hofmann</article></main>'
        rows = sources.candidates(self.person, self.fetcher({'laureates': [self.record()]}, self.page(text='No catalog title.'), bibliography))
        self.assertIn('/bibliography/', rows[0]['identity_evidence'][0])
        self.assertEqual(len(self.calls), 3)

    def test_wrong_person_bibliography_and_related_work_rejected(self):
        unrelated = '<article class="related">The Land of Green Plums</article>'
        bibliography = b'<main><h1>Different Writer</h1><article class="page-content">The Land of Green Plums</article></main>'
        self.assertEqual(sources.candidates(self.person, self.fetcher({'laureates': [self.record()]}, self.page(text='No work.', after=unrelated), bibliography)), [])

    def test_external_images_third_party_credit_wrong_identity_and_old_year_rejected(self):
        for kwargs in [{'image': 'https://www.nobelprize.org.evil.test/images/a-portrait-medium.jpg'},
                       {'credit': 'Photo: Unknown photographer'}, {'name': 'Different Writer'}]:
            self.assertEqual(sources.candidates(self.person, self.fetcher({'laureates': [self.record()]}, self.page(**kwargs))), [])
        old = self.record(nobelPrizes=[{'awardYear': '1909', 'links': [{'href': self.source.replace('/2009/', '/1909/')}]}])
        self.assertEqual(sources.candidates(self.person, self.fetcher({'laureates': [old]})), [])

    def test_untrusted_source_url_rejected(self):
        for url in [self.source + '?token=private', self.source.replace('www.nobelprize.org', 'www.nobelprize.org.evil.test'), self.source.replace('https://', 'https://user:password@')]:
            record = self.record(nobelPrizes=[{'awardYear': '2009', 'links': [{'href': url}]}])
            self.assertEqual(sources.candidates(self.person, self.fetcher({'laureates': [record]})), [])

    def test_unavailable_page_rejected(self):
        self.assertEqual(sources.candidates(self.person, self.fetcher({'laureates': [self.record()]}, CandidateRejected('removed'))), [])

    def test_bulk_index_reused_for_non_laureates_in_one_process(self):
        sources._default_index.cache_clear()
        self.addCleanup(sources._default_index.cache_clear)
        with patch.object(sources, '_fetch', return_value={'laureates': [self.record()]}) as fetch:
            for number in range(20):
                self.assertEqual(sources.candidates({'title': f'Other Writer {number}', 'works': []}), [])
        self.assertEqual(fetch.call_count, 1)


if __name__ == '__main__':
    unittest.main()
