"""Partial Wikimedia metadata never turns provider gaps into negative evidence."""
import unittest
from unittest.mock import patch

from research import enrich_catalog_portraits as portraits
from research.media_transport import CandidateRejected, ProviderOutage


class PartialPortraitDiscoveryTests(unittest.TestCase):
    def item(self, identity):
        return {'id': identity, 'title': f'Writer {identity}', 'works': [f'The Unmistakable Work {identity}']}

    def page(self, identity, *, matched=True, title=None, qid=None):
        return {'title': title or f'Writer {identity}', 'pageid': identity,
                'extract': f'Wrote The Unmistakable Work {identity}.' if matched else 'An author.',
                'pageprops': {'wikibase_item': qid or f'Q{identity}'}}

    def entities(self, identities):
        def claim(value):
            return {'mainsnak': {'datavalue': {'value': value}}}
        return {'entities': {f'Q{identity}': {'claims': {
            'P31': [claim({'id': 'Q5'})], 'P18': [claim(f'Portrait {identity}.jpg')]}}
            for identity in identities}}

    def images(self, identities):
        return {'query': {'pages': [{'title': f'File:Portrait {identity}.jpg', 'imageinfo': [{
            'thumburl': f'https://thumb.wikimedia.org/portrait-{identity}.jpg',
            'extmetadata': {'LicenseShortName': {'value': 'Public domain'}}}]}
            for identity in identities]}}

    def article(self, identity, *, matched=True):
        return {'query': {'pages': [{'pageid': identity,
            'extract': f'<p>Wrote <i>The Unmistakable Work {identity}</i>.</p>' if matched else '<p>No catalog work.</p>'}]}}

    def outage(self):
        return ProviderOutage('HTTP 429', status=429)

    def test_intro_verified_candidate_survives_later_full_article_outage(self):
        items = [self.item(1), self.item(2)]
        failure = self.outage()
        with patch.object(portraits, 'get_json', side_effect=[
                {'query': {'pages': [self.page(1), self.page(2, matched=False)]}},
                self.entities([1, 2]), self.images([1]), failure]) as fetch:
            result = portraits.wikimedia_candidates(items)
        self.assertEqual(result.completed, {1})
        self.assertEqual(result.deferred, {2: failure})
        self.assertEqual(result[1][0]['matched_works'], items[0]['works'])
        self.assertEqual(fetch.call_count, 4)
        self.assertNotIn('explaintext', fetch.call_args.args[1])

    def test_completed_full_article_survives_the_next_article_outage(self):
        items = [self.item(1), self.item(2)]
        with patch.object(portraits, 'get_json', side_effect=[
                {'query': {'pages': [self.page(1, matched=False), self.page(2, matched=False)]}},
                self.entities([1, 2]), self.article(1), self.images([1]), self.outage()]) as fetch:
            result = portraits.wikimedia_candidates(items)
        self.assertEqual(result.completed, {1})
        self.assertEqual(set(result.deferred), {2})
        self.assertEqual(len(result[1]), 1)
        self.assertEqual(fetch.call_count, 5)

    def test_commons_outage_keeps_prior_verified_people(self):
        items = [self.item(1), self.item(2)]
        with patch.object(portraits, 'get_json', side_effect=[
                {'query': {'pages': [self.page(1), self.page(2, matched=False)]}},
                self.entities([1, 2]), self.images([1]), self.article(2), self.outage()]) as fetch:
            result = portraits.wikimedia_candidates(items)
        self.assertEqual(result.completed, {1})
        self.assertEqual(set(result.deferred), {2})
        self.assertEqual(fetch.call_count, 5)

    def test_partial_commons_response_preserves_present_images_and_defers_omitted(self):
        items = [self.item(1), self.item(2)]
        with patch.object(portraits, 'get_json', side_effect=[
                {'query': {'pages': [self.page(1), self.page(2)]}}, self.entities([1, 2]), self.images([1])]):
            result = portraits.wikimedia_candidates(items)
        self.assertEqual(result.completed, {1})
        self.assertEqual(set(result.deferred), {2})
        self.assertIn('Incomplete', result.outage.reason)
        self.assertEqual(len(result[1]), 1)

    def test_omitted_title_is_deferred_without_a_false_negative(self):
        with patch.object(portraits, 'get_json', return_value={'query': {'pages': []}}) as fetch:
            result = portraits.wikimedia_candidates([self.item(1)])
        self.assertEqual(result.completed, set())
        self.assertEqual(set(result.deferred), {1})
        self.assertEqual(fetch.call_count, 1)

    def test_omitted_entity_is_deferred_without_a_false_negative(self):
        with patch.object(portraits, 'get_json', side_effect=[
                {'query': {'pages': [self.page(1)]}}, {'entities': {}}]) as fetch:
            result = portraits.wikimedia_candidates([self.item(1)])
        self.assertEqual(result.completed, set())
        self.assertEqual(set(result.deferred), {1})
        self.assertEqual(fetch.call_count, 2)

    def test_full_article_must_belong_to_the_requested_page(self):
        wrong_page = self.article(1)
        wrong_page['query']['pages'][0]['pageid'] = 99
        with patch.object(portraits, 'get_json', side_effect=[
                {'query': {'pages': [self.page(1, matched=False)]}}, self.entities([1]), wrong_page]) as fetch:
            result = portraits.wikimedia_candidates([self.item(1)])
        self.assertEqual(result.completed, set())
        self.assertEqual(set(result.deferred), {1})
        self.assertEqual(fetch.call_count, 3)

    def test_explicit_missing_titles_are_completed_only_after_bounded_qualification(self):
        def missing(host, params):
            return {'query': {'pages': [{'title': title, 'missing': True}
                                       for title in params['titles'].split('|')]}}
        with patch.object(portraits, 'get_json', side_effect=missing) as fetch:
            result = portraits.wikimedia_candidates([self.item(1)])
        self.assertEqual(result, {1: []})
        self.assertEqual(result.completed, {1})
        self.assertEqual(result.deferred, {})
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(len(fetch.call_args.args[1]['titles'].split('|')), 6)

    def test_failed_exact_namesake_gets_work_verified_qualified_fallback(self):
        def qualified_pages(host, params):
            return {'query': {'pages': [self.page(1, title=name, qid='Q2')
                if name.endswith('(philosopher)') else {'title': name, 'missing': True}
                for name in params['titles'].split('|')]}}
        responses = [
            {'query': {'pages': [self.page(1, matched=False)]}}, self.entities([1]),
            self.article(1, matched=False), qualified_pages, self.entities([2]), self.images([2])]
        def response(host, params):
            value = responses.pop(0)
            return value(host, params) if callable(value) else value
        with patch.object(portraits, 'get_json', side_effect=response) as fetch:
            result = portraits.wikimedia_candidates([self.item(1)])
        self.assertEqual(result.completed, {1})
        self.assertEqual(result[1][0]['wikidata'], 'Q2')
        self.assertEqual(result[1][0]['matched_works'], self.item(1)['works'])
        self.assertEqual(fetch.call_count, 6)
        self.assertEqual(responses, [])

    def test_conflicting_qualified_identities_remain_ambiguous(self):
        def response(host, params):
            if host.startswith('https://www.wikidata'):
                return self.entities([1, 2])
            titles = params['titles'].split('|')
            if len(titles) == 1:
                return {'query': {'pages': [{'title': titles[0], 'missing': True}]}}
            pages = [self.page(1, title=name, qid=f'Q{index + 1}') if index < 2
                     else {'title': name, 'missing': True} for index, name in enumerate(titles)]
            return {'query': {'pages': pages}}
        with patch.object(portraits, 'get_json', side_effect=response) as fetch:
            result = portraits.wikimedia_candidates([self.item(1)])
        self.assertEqual(result, {1: []})
        self.assertEqual(result.completed, {1})
        self.assertEqual(result.deferred, {})
        self.assertEqual(fetch.call_count, 3)

    def test_incomplete_metadata_is_returned_but_cannot_enter_the_http_cache(self):
        params = {'action': 'query', 'titles': 'File:Portrait 1.jpg|File:Portrait 2.jpg',
                  'prop': 'imageinfo'}
        partial = self.images([1])
        with patch.object(portraits, 'fetch_json', return_value=partial) as fetch:
            self.assertIs(portraits.get_json('https://commons.wikimedia.org/w/api.php', params), partial)
        cacheable = fetch.call_args.kwargs['json_cacheable']
        self.assertFalse(cacheable(partial))
        self.assertTrue(cacheable(self.images([1, 2])))

    def test_cache_completeness_checks_requested_extract_and_entity_properties(self):
        self.assertFalse(portraits.metadata_response_complete(
            {'ids': 'Q1|Q2', 'props': 'claims'}, self.entities([1])))
        self.assertFalse(portraits.metadata_response_complete(
            {'pageids': 1, 'prop': 'extracts'}, {'query': {'pages': [{'pageid': 1}]}}))
        self.assertFalse(portraits.metadata_response_complete(
            {'pageids': 1, 'prop': 'extracts'}, self.article(2)))
        self.assertTrue(portraits.metadata_response_complete(
            {'pageids': 1, 'prop': 'extracts'}, self.article(1)))
        self.assertTrue(portraits.metadata_response_complete(
            {'titles': 'Writer 1', 'prop': 'extracts'},
            {'query': {'pages': [{'title': 'Writer 1', 'missing': True}]}}))

    def test_missing_imageinfo_is_deferred_instead_of_cached_as_no_portrait(self):
        partial = self.images([1, 2])
        del partial['query']['pages'][1]['imageinfo']
        with patch.object(portraits, 'get_json', side_effect=[
                {'query': {'pages': [self.page(1), self.page(2)]}}, self.entities([1, 2]), partial]):
            result = portraits.wikimedia_candidates([self.item(1), self.item(2)])
        self.assertEqual(result.completed, {1})
        self.assertEqual(set(result.deferred), {2})
        self.assertFalse(portraits.metadata_response_complete(
            {'titles': 'File:Portrait 1.jpg|File:Portrait 2.jpg', 'prop': 'imageinfo'}, partial))

    def test_malformed_envelopes_are_rejected_and_never_cacheable(self):
        params = {'titles': 'Writer 1', 'prop': 'extracts'}
        malformed = [
            {'query': None}, {'query': {'pages': None}}, {'query': {'pages': [None]}},
            {'query': {'pages': [], 'redirects': None}},
            {'query': {'pages': [], 'normalized': None}},
            {'query': {'pages': [], 'redirects': [{'from': 'Writer 1'}]}},
        ]
        for payload in malformed:
            with self.subTest(payload=payload), patch.object(portraits, 'fetch_json', return_value=payload):
                self.assertFalse(portraits.metadata_response_complete(params, payload))
                with self.assertRaises(CandidateRejected):
                    portraits.get_json('https://en.wikipedia.org/w/api.php', params)

    def test_malformed_later_response_preserves_prior_verified_candidates(self):
        items = [self.item(1), self.item(2)]
        for payload in ({'query': None}, {'query': {'pages': None}},
                        {'query': {'pages': [], 'normalized': None}}):
            with self.subTest(payload=payload), patch.object(portraits, 'fetch_json', side_effect=[
                    {'query': {'pages': [self.page(1), self.page(2, matched=False)]}},
                    self.entities([1, 2]), self.images([1]), payload]) as fetch:
                result = portraits.wikimedia_candidates(items)
            self.assertEqual(result.completed, {1})
            self.assertEqual(set(result.deferred), {2})
            self.assertEqual(len(result[1]), 1)
            self.assertEqual(fetch.call_count, 4)

    def test_malformed_consumed_claim_and_image_fields_are_rejected(self):
        requests = [
            ({'ids': 'Q1', 'props': 'claims'}, {'entities': None}),
            ({'ids': 'Q1', 'props': 'claims'}, {'entities': {'Q1': {'claims': None}}}),
            ({'ids': 'Q1', 'props': 'claims'}, {'entities': {'Q1': {'claims': {'P31': None}}}}),
            ({'ids': 'Q1', 'props': 'claims'}, {'entities': {'Q1': {'claims': {'P31': [{'mainsnak': None}]}}}}),
            ({'titles': 'File:Portrait 1.jpg', 'prop': 'imageinfo'},
             {'query': {'pages': [{'title': 'File:Portrait 1.jpg', 'imageinfo': [None]}]}}),
            ({'titles': 'File:Portrait 1.jpg', 'prop': 'imageinfo'},
             {'query': {'pages': [{'title': 'File:Portrait 1.jpg', 'imageinfo': [{'extmetadata': None}]}]}}),
        ]
        for params, payload in requests:
            with self.subTest(params=params, payload=payload), patch.object(portraits, 'fetch_json', return_value=payload):
                self.assertFalse(portraits.metadata_response_complete(params, payload))
                with self.assertRaises(CandidateRejected):
                    portraits.get_json('https://www.wikidata.org/w/api.php', params)
