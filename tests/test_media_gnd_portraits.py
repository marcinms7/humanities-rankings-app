import copy
import unittest
from urllib.parse import parse_qs, urlsplit

from research import media_gnd_portraits as source
from research.media_transport import ProviderOutage


class GndPortraitTests(unittest.TestCase):
    def setUp(self):
        self.item = {'title': 'Tove Jansson', 'works': ['The Summer Book']}
        self.depiction = {'url': 'https://commons.wikimedia.org/wiki/File:Tove%20Jansson%201956b.jpg?uselang=de',
            'thumbnail': 'https://commons.wikimedia.org/wiki/Special:FilePath/Tove%20Jansson%201956b.jpg?width=270',
            'id': 'https://commons.wikimedia.org/wiki/Special:FilePath/Tove%20Jansson%201956b.jpg',
            'creatorName': ['Reino Loppinen; derivative work: Bff'],
            'license': [{'abbr': 'PD', 'id': 'https://creativecommons.org/publicdomain/mark/1.0/'}]}
        self.entity = {'id': 'https://d-nb.info/gnd/118920316', 'preferredName': 'Jansson, Tove',
            'type': ['Person', 'AuthorityResource', 'DifferentiatedPerson'], 'depiction': [self.depiction]}
        self.book = {'id': 'http://lobid.org/resources/990183966100206441#!', 'title': 'The summer book',
            'contribution': [{'agent': {'id': self.entity['id'], 'label': 'Jansson, Tove', 'type': ['Person']},
                'role': {'id': 'http://id.loc.gov/vocabulary/relators/aut', 'label': 'Autor/in'}}]}
        self.entities = [self.entity]
        self.books = [self.book]
        self.calls = []

    def fetch(self, url, **kwargs):
        self.calls.append((url, kwargs))
        records = self.entities if '/gnd/' in urlsplit(url).path else self.books
        return {'member': records, 'totalItems': len(records)}

    def test_real_work_author_gnd_and_per_image_rights_chain(self):
        result = source.candidates(self.item, self.fetch)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['subject_authority'], self.entity['id'])
        self.assertEqual(result[0]['matched_works'], ['The Summer Book'])
        self.assertEqual(result[0]['identity_evidence'][0]['source'], self.book['id'])
        self.assertIn('Reino Loppinen', result[0]['credit'])
        self.assertEqual(len(self.calls), 2)
        self.assertTrue(all(kwargs['allowed_hosts'] == source.API_HOSTS and kwargs['min_interval'] >= 2
                            and kwargs['cache_ttl'] >= 43200 for _, kwargs in self.calls))

    def test_namesake_wrong_work_and_unproven_name_do_not_accept(self):
        self.book['contribution'][0]['agent']['id'] = 'https://d-nb.info/gnd/123456789'
        self.assertEqual(source.candidates(self.item, self.fetch), [])
        self.book['contribution'][0]['agent']['id'] = self.entity['id']
        self.book['title'] = 'A book about Tove Jansson'
        self.assertEqual(source.candidates(self.item, self.fetch), [])
        self.books = []
        self.assertEqual(source.candidates(self.item, self.fetch), [])

    def test_translator_editor_subject_and_name_mismatch_rejected(self):
        for role in ['trl', 'edt', 'ill', 'oth']:
            self.book['contribution'][0]['role']['id'] = 'http://id.loc.gov/vocabulary/relators/' + role
            self.assertEqual(source.candidates(self.item, self.fetch), [])
        self.book['contribution'][0]['role']['id'] = 'http://id.loc.gov/vocabulary/relators/aut'
        self.book['contribution'][0]['agent']['label'] = 'Jansson, Lars'
        self.assertEqual(source.candidates(self.item, self.fetch), [])
        self.book['subject'] = [{'id': self.entity['id']}]
        self.book['contribution'] = []
        self.assertEqual(source.candidates(self.item, self.fetch), [])

    def test_no_photo_or_no_works_avoids_bibliography_lookup(self):
        self.entity['depiction'] = []
        self.assertEqual(source.candidates(self.item, self.fetch), [])
        self.assertEqual(len(self.calls), 1)
        self.entity['depiction'] = [self.depiction]
        self.calls = []
        self.assertEqual(source.candidates({**self.item, 'works': []}, self.fetch), [])
        self.assertEqual(len(self.calls), 1)

    def test_metadata_cc0_is_not_an_image_license_and_creator_required(self):
        for license in [[], [{'abbr': 'CC BY-NC', 'id': 'https://creativecommons.org/licenses/by-nc/4.0/'}],
                        [{'abbr': 'CC0', 'id': 'https://evil.test/publicdomain/zero/1.0/'}]]:
            self.depiction['license'] = license
            self.entity['describedBy'] = {'license': {'id': 'https://creativecommons.org/publicdomain/zero/1.0/'}}
            self.assertEqual(source.candidates(self.item, self.fetch), [])
        self.depiction['license'] = [{'abbr': 'CC0', 'id': 'http://creativecommons.org/publicdomain/zero/1.0/deed.en'}]
        self.depiction['creatorName'] = []
        self.assertEqual(source.candidates(self.item, self.fetch), [])

    def test_rejects_unsafe_image_and_authority_urls(self):
        for url in ['https://commons.wikimedia.org.evil.test/wiki/Special:FilePath/X.jpg',
                    'https://user:pass@commons.wikimedia.org/wiki/Special:FilePath/X.jpg',
                    'https://commons.wikimedia.org:444/wiki/Special:FilePath/X.jpg',
                    'https://commons.wikimedia.org/wiki/X.jpg', 'http://127.0.0.1/X.jpg']:
            self.depiction['id'] = self.depiction['thumbnail'] = url
            self.assertEqual(source.candidates(self.item, self.fetch), [])
        self.entity['id'] = 'https://d-nb.info.evil.test/gnd/118920316'
        self.assertEqual(source.candidates(self.item, self.fetch), [])

    def test_ambiguous_corroborated_namesake_without_image_still_rejects(self):
        second = {**self.entity, 'id': 'https://d-nb.info/gnd/123456789', 'depiction': []}
        self.entities.append(second)
        book = copy.deepcopy(self.book)
        book['contribution'][0]['agent']['id'] = second['id']
        self.books.append(book)
        self.assertEqual(source.candidates(self.item, self.fetch), [])

    def test_subtitle_combination_and_reviewed_aliases(self):
        self.item['works'] = [{'title': 'Summer: A memoir', 'title_aliases': ['The Summer Book']}]
        self.book['title'] = 'Summer'
        self.book['otherTitleInformation'] = ['A memoir']
        self.assertEqual(len(source.candidates(self.item, self.fetch)), 2)
        self.entity['preferredName'] = 'Unrelated Person'
        self.entity['variantName'] = ['Jansson, Tove']
        self.assertEqual(len(source.candidates(self.item, self.fetch)), 2)

    def test_catalog_work_alias_mapping_reaches_bibliography_query(self):
        self.item['works'] = ['Sommarboken']
        self.item['work_aliases'] = {'Sommarboken': ['The Summer Book']}
        result = source.candidates(self.item, self.fetch)
        self.assertEqual(result[0]['matched_works'], ['Sommarboken'])
        self.assertIn('summer', parse_qs(urlsplit(self.calls[1][0]).query)['q'][0])

    def test_undifferentiated_authority_and_missing_name_are_rejected(self):
        self.entity['type'] = ['Person', 'UndifferentiatedPerson']
        self.assertEqual(source.candidates(self.item, self.fetch), [])
        self.entity['type'] = ['Person', 'DifferentiatedPerson']
        self.entity['preferredName'] = 'Lars Jansson'
        self.assertEqual(source.candidates(self.item, self.fetch), [])

    def test_query_is_bounded_and_names_cannot_inject_lucene(self):
        item = {**self.item, 'works': ['The Summer Book'] + [f'Other title {i}' for i in range(20)],
                'title_aliases': ['Tove Jansson) OR *:*', *['ignored'] * 10]}
        source.candidates(item, self.fetch)
        query = parse_qs(urlsplit(self.calls[0][0]).query)['q'][0]
        self.assertNotIn('*:*', query)
        books_query = parse_qs(urlsplit(self.calls[1][0]).query)['q'][0]
        self.assertNotIn('"4"', books_query)
        self.assertEqual(len(self.calls), 2)

    def test_provider_outage_propagates_without_retrying(self):
        def down(url, **kwargs):
            raise ProviderOutage('HTTP 429')
        with self.assertRaises(ProviderOutage):
            source.candidates(self.item, down)

    def test_truncated_authority_or_bibliography_cannot_prove_unique_identity(self):
        for truncated_kind in ['gnd', 'resources']:
            self.calls = []
            self.entities = [self.entity, {**self.entity, 'id': 'https://d-nb.info/gnd/123456789', 'depiction': []}]
            def truncated(url, **kwargs):
                result = self.fetch(url, **kwargs)
                if urlsplit(url).path == f'/{truncated_kind}/search':
                    result['totalItems'] = 27
                return result
            self.assertEqual(source.candidates(self.item, truncated), [])
            self.assertEqual(len(self.calls), 1 if truncated_kind == 'gnd' else 2)

    def test_single_complete_authority_needs_one_authored_work_not_all_editions(self):
        def many_editions(url, **kwargs):
            result = self.fetch(url, **kwargs)
            if urlsplit(url).path == '/resources/search':
                result['totalItems'] = 27
            return result
        self.assertEqual(len(source.candidates(self.item, many_editions)), 2)
        self.book['contribution'][0]['role']['id'] = 'http://id.loc.gov/vocabulary/relators/trl'
        self.assertEqual(source.candidates(self.item, many_editions), [])
        self.book['contribution'][0]['role']['id'] = 'http://id.loc.gov/vocabulary/relators/aut'
        self.book['title'] = 'An unrelated work'
        self.assertEqual(source.candidates(self.item, many_editions), [])

    def test_missing_or_inconsistent_result_count_is_not_complete_evidence(self):
        for total in [None, True, -1, '1']:
            def invalid(url, **kwargs):
                return {**self.fetch(url, **kwargs), 'totalItems': total}
            with self.assertRaises(ValueError):
                source.candidates(self.item, invalid)
        def incomplete_page(url, **kwargs):
            return {**self.fetch(url, **kwargs), 'totalItems': 2}
        self.assertEqual(source.candidates(self.item, incomplete_page), [])


if __name__ == '__main__':
    unittest.main()
