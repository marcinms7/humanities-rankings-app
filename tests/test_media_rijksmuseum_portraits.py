import copy
import unittest
from urllib.parse import parse_qs, urlsplit

from research import media_rijksmuseum_portraits as source
from research.media_transport import ProviderOutage


class RijksmuseumPortraitTests(unittest.TestCase):
    def setUp(self):
        self.item = {'title': 'Alexander Pope', 'works': ['The Rape of the Lock']}
        self.identity = {'uri': 'https://dbpedia.org/resource/Alexander_Pope', 'wikidata': 'Q164047',
                         'matched_works': ['The Rape of the Lock'], 'ranked_philosopher': False}
        self.object_uri = 'https://id.rijksmuseum.nl/200137829'
        self.visual_uri = 'https://id.rijksmuseum.nl/202137829'
        self.digital_uri = 'https://id.rijksmuseum.nl/50068788166661224874'
        self.record = {'id': self.object_uri, 'type': 'HumanMadeObject',
                       'identified_by': [{'type': 'Name', 'content': 'Portret van Alexander Pope op 57-jarige leeftijd'}],
                       'shows': [{'id': self.visual_uri}],
                       'produced_by': {'carried_out_by': [{'notation': {'@language': 'en', '@value': 'John Faber'}}]}}
        self.visual = {'id': self.visual_uri, 'type': 'VisualItem', 'shown_by': [{'id': self.object_uri}],
                       'represents': [{'id': 'https://id.rijksmuseum.nl/21059745', 'type': 'Person',
                                       'equivalent': [{'id': 'http://www.wikidata.org/entity/Q164047', 'type': 'Person'}]}],
                       'subject_to': [{'type': 'Right', 'classified_as': [
                           {'id': 'https://creativecommons.org/publicdomain/mark/1.0/'}]}],
                       'digitally_shown_by': [{'id': self.digital_uri}]}
        self.digital = {'id': self.digital_uri, 'type': 'DigitalObject',
                        'digitally_shows': [{'id': self.visual_uri}],
                        'referred_to_by': [{'content': 'downloadbaar'}, {'content': 'zichtbaar'}],
                        'access_point': [{'id': 'https://iiif.micr.io/sfeAK/full/max/0/default.jpg'}]}
        self.hits = [{'id': self.object_uri}]
        self.calls = []

    def fetch(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if '/search/collection?' in url:
            self.assertEqual(parse_qs(urlsplit(url).query)['aboutActor'], ['Alexander Pope'])
            return {'orderedItems': self.hits}
        return {self.object_uri: self.record, self.visual_uri: self.visual,
                self.digital_uri: self.digital}[url.split('?')[0]]

    def identities(self, item, **kwargs):
        return [self.identity]

    def candidates(self, item=None):
        return source.candidates(item or self.item, fetch=self.fetch, identities=self.identities)

    def test_live_pope_authority_rights_image_chain(self):
        rows = self.candidates()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['image_url'], 'https://iiif.micr.io/sfeAK/full/600,/0/default.jpg')
        self.assertEqual(rows[0]['matched_works'], ['The Rape of the Lock'])
        self.assertEqual(rows[0]['source'], self.object_uri)
        self.assertEqual(rows[0]['wikidata_id'], 'Q164047')
        self.assertIn('John Faber', rows[0]['credit'])
        self.assertIn('Rijksmuseum', rows[0]['credit'])
        self.assertEqual(len(self.calls), 4)
        self.assertTrue(all(kwargs['allowed_hosts'] == source.API_HOSTS for _, kwargs in self.calls))

    def test_matching_name_without_verified_work_or_identity_is_rejected(self):
        self.identity['matched_works'] = []
        self.assertEqual(self.candidates(), [])
        self.assertEqual(self.calls, [])
        self.identity['matched_works'] = ['The Rape of the Lock']
        self.identity['wikidata'] = ''
        self.assertEqual(self.candidates(), [])

    def test_ranked_philosopher_exception_requires_actual_ranked_catalog_person(self):
        self.identity.update(matched_works=[], ranked_philosopher=True)
        self.assertEqual(self.candidates(), [])
        rows = self.candidates({**self.item, 'ranked': True})
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['ranked_philosopher'])
        self.assertEqual(rows[0]['matched_works'], [])

    def test_other_wikidata_subject_and_creators_qid_do_not_match(self):
        self.visual['represents'][0]['equivalent'][0]['id'] = 'http://www.wikidata.org/entity/Q1'
        self.record['produced_by']['carried_out_by'][0]['equivalent'] = [{'id': 'http://www.wikidata.org/entity/Q164047'}]
        self.assertEqual(self.candidates(), [])

    def test_group_portrait_is_rejected(self):
        self.visual['represents'].append({'id': 'https://id.rijksmuseum.nl/2101', 'type': 'Person'})
        self.assertEqual(self.candidates(), [])

    def test_bookplate_coat_of_arms_and_scene_are_not_portraits(self):
        for title in ['Ex libris van Alexander Pope', 'The works of Alexander Pope',
                      'Alexander Pope', 'Monument for Alexander Pope', 'Spotprent op Alexander Pope']:
            self.record['identified_by'][0]['content'] = title
            self.assertEqual(self.candidates(), [])

    def test_metadata_cc0_does_not_license_the_visual(self):
        rights = self.visual.pop('subject_to')
        self.visual['subject_of'] = [{'subject_to': rights}]
        self.assertEqual(self.candidates(), [])
        self.visual['subject_to'] = [{'classified_as': [{'id': 'https://rightsstatements.org/vocab/InC/1.0/'}]}]
        self.assertEqual(self.candidates(), [])

    def test_link_chain_must_point_back_to_same_object_and_visual(self):
        self.visual['shown_by'][0]['id'] = 'https://id.rijksmuseum.nl/999'
        self.assertEqual(self.candidates(), [])
        self.visual['shown_by'][0]['id'] = self.object_uri
        self.digital['digitally_shows'][0]['id'] = 'https://id.rijksmuseum.nl/999'
        self.assertEqual(self.candidates(), [])

    def test_non_downloadable_image_is_rejected(self):
        self.digital['referred_to_by'] = [{'content': 'zichtbaar'}]
        self.assertEqual(self.candidates(), [])

    def test_credentials_foreign_hosts_manifest_and_bad_ports_rejected(self):
        for uri in ['https://iiif.micr.io.evil.test/X/full/max/0/default.jpg',
                    'https://user:password@iiif.micr.io/X/full/max/0/default.jpg',
                    'https://iiif.micr.io:444/X/full/max/0/default.jpg',
                    'https://iiif.micr.io/X/info.json',
                    'https://iiif.micr.io/X/full/max/0/default.jpg?token=secret']:
            self.digital['access_point'][0]['id'] = uri
            self.assertEqual(self.candidates(), [])
        self.hits = [{'id': 'https://id.rijksmuseum.nl.evil.test/200137829'}]
        before = len(self.calls)
        self.assertEqual(self.candidates(), [])
        self.assertEqual(len(self.calls) - before, 1)

    def test_response_ids_and_types_must_agree_with_requested_records(self):
        self.visual['id'] = self.object_uri
        self.assertEqual(self.candidates(), [])
        self.visual['id'] = self.visual_uri
        self.visual['type'] = 'LinguisticObject'
        self.assertEqual(self.candidates(), [])

    def test_no_more_than_three_objects_and_no_retry_of_outage(self):
        self.hits = [{'id': self.object_uri}] * 100
        self.record['identified_by'] = []
        self.assertEqual(self.candidates(), [])
        self.assertEqual(len(self.calls), 4)
        def down(url, **kwargs):
            raise ProviderOutage('rate limited')
        with self.assertRaises(ProviderOutage):
            source.candidates(self.item, fetch=down, identities=self.identities)

    def test_multiple_verified_identities_are_ambiguous(self):
        identities = lambda item, **kwargs: [self.identity, copy.deepcopy(self.identity)]
        self.assertEqual(source.candidates(self.item, fetch=self.fetch, identities=identities), [])
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
