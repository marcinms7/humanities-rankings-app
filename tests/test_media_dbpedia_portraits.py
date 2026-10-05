import copy
import unittest
from urllib.parse import parse_qs, urlsplit

from research import media_dbpedia_portraits as source
from research.media_transport import ProviderOutage


def binding(name='Terry Pratchett', work='Small Gods', **changes):
    row = {'person': {'type': 'uri', 'value': 'http://dbpedia.org/resource/Terry_Pratchett'},
           'name': {'type': 'literal', 'xml:lang': 'en', 'value': name},
           'workLabel': {'type': 'literal', 'xml:lang': 'en', 'value': work},
           'image': {'type': 'uri', 'value': 'http://commons.wikimedia.org/wiki/Special:FilePath/Terry_Pratchett.jpg?width=300'},
           'philosopher': {'type': 'typed-literal', 'value': 'false'},
           'wikidata': {'type': 'uri', 'value': 'http://www.wikidata.org/entity/Q46248'}}
    row.update(changes)
    return row


class DBpediaPortraitTests(unittest.TestCase):
    def setUp(self):
        self.item = {'title': 'Terry Pratchett', 'works': ['Small Gods']}
        self.rows = [binding()]
        self.info = {'thumburl': 'https://thumb.wikimedia.org/Terry_Pratchett.jpg',
                     'url': 'https://upload.wikimedia.org/Terry_Pratchett.jpg',
                     'descriptionurl': 'https://commons.wikimedia.org/wiki/File:Terry_Pratchett.jpg',
                     'extmetadata': {'LicenseShortName': {'value': 'CC BY-SA 4.0'},
                                     'Artist': {'value': '<b>Photographer</b>'},
                                     'ImageDescription': {'value': 'Portrait of Terry Pratchett'},
                                     'Categories': {'value': 'Terry Pratchett|Portrait photographs'}}}
        self.calls = []

    def fetch(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if urlsplit(url).hostname == 'dbpedia.org':
            return {'results': {'bindings': self.rows}}
        return {'query': {'pages': [{'title': 'File:Terry Pratchett.jpg', 'imageinfo': [self.info]}]}}

    def test_authored_work_primary_thumbnail_and_commons_credit(self):
        rows = source.candidates(self.item, self.fetch)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['matched_works'], ['Small Gods'])
        self.assertEqual(rows[0]['wikidata'], 'Q46248')
        self.assertEqual(rows[0]['identity_url'], 'https://dbpedia.org/resource/Terry_Pratchett')
        self.assertIn('Photographer · CC BY-SA 4.0', rows[0]['credit'])
        query = parse_qs(urlsplit(self.calls[0][0]).query)['query'][0]
        self.assertIn('a dbo:Person', query)
        self.assertIn('a dbo:WrittenWork ; dbo:author ?person', query)
        self.assertIn('dbo:thumbnail', query)
        self.assertNotIn('depiction', query)
        self.assertTrue(self.calls[0][1]['reject_partial_sparql'])

    def test_name_only_wrong_work_and_wrong_name_rejected_without_commons_lookup(self):
        for item in [dict(self.item, works=[]), dict(self.item, works=['Unrelated book']),
                     dict(self.item, title='John Pratchett')]:
            self.calls.clear()
            self.assertEqual(source.candidates(item, self.fetch), [])
            self.assertEqual(len(self.calls), 1)

    def test_reviewed_work_alias_keeps_canonical_identity(self):
        item = {**self.item, 'works': ['Small Deities'], 'work_aliases': {'Small Deities': ['Small Gods']}}
        self.assertEqual(source.verified_identities(item, self.fetch)[0]['matched_works'], ['Small Deities'])
        self.assertEqual(source.verified_identities({**item, 'work_aliases': {}}, self.fetch), [])

    def test_only_supported_work_disambiguators_removed(self):
        self.rows = [binding(work='Small Gods (novel)')]
        self.assertTrue(source.candidates(self.item, self.fetch))
        for suffix in ['film', 'volume 2', 'second edition', 'Pratchett novel']:
            self.rows = [binding(work='Small Gods (' + suffix + ')')]
            self.assertEqual(source.candidates(self.item, self.fetch), [])

    def test_distinct_work_corroborated_identities_rejected(self):
        other = copy.deepcopy(self.rows[0])
        other['person']['value'] = 'http://dbpedia.org/resource/Terry_Pratchett_(other)'
        self.rows.append(other)
        self.assertEqual(source.verified_identities(self.item, self.fetch), [])

    def test_ranked_philosopher_exception_requires_both_conditions(self):
        self.rows = [binding(work='', philosopher={'value': 'true'})]
        self.assertEqual(source.candidates(self.item, self.fetch), [])
        result = source.candidates(dict(self.item, ranked=True), self.fetch)
        self.assertTrue(result[0]['ranked_philosopher'])
        self.assertEqual(result[0]['identity_basis'], 'dbpedia_ranked_philosopher')
        self.rows[0]['philosopher']['value'] = 'false'
        self.assertEqual(source.candidates(dict(self.item, ranked=True), self.fetch), [])

    def test_identity_without_thumbnail_remains_available_to_independent_source(self):
        self.rows[0].pop('image')
        identities = source.verified_identities(self.item, self.fetch)
        self.assertEqual(identities[0]['wikidata'], 'Q46248')
        self.assertEqual(identities[0]['images'], [])
        self.assertEqual(source.candidates(self.item, self.fetch), [])

    def test_conflicting_wikidata_ids_not_arbitrarily_selected(self):
        other = copy.deepcopy(self.rows[0])
        other['wikidata']['value'] = 'http://www.wikidata.org/entity/Q9999'
        self.rows.append(other)
        self.assertEqual(source.verified_identities(self.item, self.fetch)[0]['wikidata'], '')

    def test_unsafe_or_noncommons_primary_images_not_resolved(self):
        for url in ['https://commons.wikimedia.org.evil.test/wiki/Special:FilePath/Terry.jpg',
                    'https://user:secret@commons.wikimedia.org/wiki/Special:FilePath/Terry.jpg',
                    'https://commons.wikimedia.org/wiki/Special:FilePath/Terry.jpg?token=secret',
                    'https://commons.wikimedia.org/wiki/Special:FilePath/../Terry.jpg',
                    'https://commons.wikimedia.org/wiki/Special:FilePath/Terry.svg',
                    'https://commons.wikimedia.org:444/wiki/Special:FilePath/Terry.jpg']:
            self.rows[0]['image']['value'] = url
            self.assertEqual(source.candidates(self.item, self.fetch), [])

    def test_actual_cyril_connolly_blue_plaque_and_other_objects_rejected(self):
        for category in ['Blue plaques in Eastbourne', 'Graves of authors', 'Book covers',
                         'Buildings in London', 'Group photographs', 'Signatures']:
            self.info['extmetadata']['Categories']['value'] = category
            self.assertEqual(source.candidates(self.item, self.fetch), [])

    def test_unrelated_sitter_or_missing_rights_rejected(self):
        self.info['extmetadata']['LicenseShortName']['value'] = 'All rights reserved'
        self.assertEqual(source.candidates(self.item, self.fetch), [])
        self.info['extmetadata']['LicenseShortName']['value'] = 'CC BY 2.0'
        self.rows[0]['image']['value'] = 'http://commons.wikimedia.org/wiki/Special:FilePath/Someone_Else.jpg'
        self.assertEqual(source.candidates(self.item, self.fetch), [])

    def test_group_description_rejected_even_when_file_is_named_for_one_person(self):
        self.info['extmetadata']['ImageDescription']['value'] = 'Terry Pratchett and Neil Gaiman at a signing'
        self.assertEqual(source.candidates(self.item, self.fetch), [])

    def test_many_people_use_one_metadata_query_and_one_commons_request(self):
        rows = source.batch_candidates([self.item, self.item], self.fetch)
        self.assertEqual([len(row) for row in rows], [2, 2])
        self.assertEqual(len(self.calls), 2)
        with self.assertRaises(ValueError):
            source.batch_candidates([self.item] * (source.MAX_BATCH + 1), self.fetch)

    def test_truncated_results_and_provider_outage_do_not_become_no_match(self):
        self.rows *= source.MAX_ROWS + 1
        with self.assertRaises(ProviderOutage):
            source.candidates(self.item, self.fetch)
        def down(*args, **kwargs):
            raise ProviderOutage('provider temporarily unavailable')
        with self.assertRaises(ProviderOutage):
            source.candidates(self.item, down)

    def test_names_are_sparql_escaped_and_alias_count_bounded(self):
        item = {'title': 'Name "quoted" \\ end', 'title_aliases': ['A', 'B', 'C', 'D'], 'works': []}
        source.candidates(item, self.fetch)
        query = parse_qs(urlsplit(self.calls[0][0]).query)['query'][0]
        self.assertIn('"Name \\"quoted\\" \\\\ end"@en', query)
        self.assertNotIn('"C"@en', query)
        self.assertNotIn('"D"@en', query)


if __name__ == '__main__':
    unittest.main()
