"""Offline authority/rights validation for cached library identity handoffs."""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from research import media_cached_wikidata_portraits as provider
from research import media_transport as transport


class CachedWikidataPortraitTests(unittest.TestCase):
    def setUp(self):
        provider._index.cache_clear()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(provider._index.cache_clear)
        self.root = Path(self.temporary.name)
        self.patch = patch.object(transport, 'STATE', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.counter = 0

    def cache(self, url, data):
        self.counter += 1
        path = self.root / 'responses/ab' / str(self.counter)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
        path.with_suffix('.json').write_text(json.dumps({'final_url': url}))
        return path

    def item(self, identity=1):
        return {'id': identity, 'title': f'Jane Writer {identity}', 'works': [f'A Distinctive Known Work {identity}']}

    def seed(self, identity=1, *, author_number=None, role=None, qid=True, title=None):
        number = author_number or identity
        author = f'/authors/OL{number}A'
        record = {'key': author, 'name': f'Jane Writer {identity}'}
        if qid:
            record['remote_ids'] = {'wikidata': f'Q{number}'}
        self.cache('https://openlibrary.org' + author + '.json', record)
        author_link = {'author': {'key': author}, 'type': {'key': '/type/author_role'}}
        if role:
            author_link['role'] = role
        work = {'key': f'/works/OL{number}W', 'title': title or self.item(identity)['works'][0],
                'authors': [author_link]}
        self.cache('https://openlibrary.org' + author + '/works.json?limit=100', {'entries': [work]})
        return work

    def claim(self, value):
        return {'mainsnak': {'datavalue': {'value': value}}}

    def entity(self, identity=1, *, human=True, reciprocal=True, label=None, filenames=None):
        claims = {'P31': [self.claim({'id': 'Q5' if human else 'Q43229'})],
                  'P18': [self.claim(filename) for filename in (filenames or [f'Portrait {identity}.jpg'])]}
        if reciprocal:
            claims['P648'] = [self.claim(f'OL{identity}A' if reciprocal is True else reciprocal)]
        return {'claims': claims, 'labels': {'en': {'value': label or f'Jane Writer {identity}'}}, 'aliases': {}}

    def picture(self, filename):
        return {'title': 'File:' + filename, 'imageinfo': [{
            'thumburl': 'https://thumb.wikimedia.org/' + filename.replace(' ', '_'),
            'url': 'https://upload.wikimedia.org/' + filename.replace(' ', '_'),
            'descriptionurl': 'https://commons.wikimedia.org/wiki/File:' + filename.replace(' ', '_'),
            'extmetadata': {'LicenseShortName': {'value': 'CC BY 4.0'},
                            'Artist': {'value': '<b>Named artist</b>'}}}]}

    def responses(self, url, **kwargs):
        params = parse_qs(urlsplit(url).query)
        if 'ids' in params:
            return {'entities': {qid: self.entity(int(qid[1:])) for qid in params['ids'][0].split('|')}}
        return {'query': {'pages': [self.picture(title.removeprefix('File:')) for title in params['titles'][0].split('|')]}}

    def test_missing_cached_identity_sends_no_requests(self):
        with patch.object(transport, 'fetch_json') as fetch:
            with self.assertRaises(transport.ProviderOutage):
                provider.batch_candidates([self.item()])
        fetch.assert_not_called()

    def test_unique_identity_without_edition_link_retains_canonical_title_and_sources(self):
        self.seed(title='A Completely Different Reviewed Title')
        item = self.item()
        item['work_aliases'] = {item['works'][0]: ['A Completely Different Reviewed Title']}
        identity = provider.cached_identity(item)
        self.assertEqual(identity['matched_works'], item['works'])
        self.assertEqual(identity['author_key'], 'OL1A')
        self.assertEqual(identity['identity_sources'], ['https://openlibrary.org/authors/OL1A', 'https://openlibrary.org/works/OL1W'])

    def test_translator_role_does_not_establish_authorship(self):
        self.seed(role='translator')
        self.assertIsNone(provider.cached_identity(self.item()))

    def test_initials_are_not_treated_as_complete_name_identity(self):
        self.seed()
        self.assertIsNone(provider.cached_identity({**self.item(), 'title': 'J. Writer 1'}))

    def test_two_reciprocal_same_name_author_records_are_ambiguous_even_if_one_lacks_qid(self):
        self.seed()
        self.seed(author_number=2, qid=False)
        self.assertIsNone(provider.cached_identity(self.item()))

    def test_index_is_reused_without_rescanning_each_person(self):
        self.seed()
        with patch.object(provider, '_read', wraps=provider._read) as read:
            self.assertIsNotNone(provider.cached_identity(self.item()))
            calls = read.call_count
            self.assertIsNotNone(provider.cached_identity(self.item()))
            self.assertEqual(read.call_count, calls)
        self.assertGreater(calls, 0)

    def test_fifty_people_share_two_metadata_requests_and_keep_aligned_results(self):
        items = [self.item(identity) for identity in range(1, 51)]
        for identity in range(1, 51):
            self.seed(identity)
        with patch.object(transport, 'fetch_json', side_effect=self.responses) as fetch:
            results = provider.batch_candidates(items)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(len(results), 50)
        for identity, candidates in enumerate(results, 1):
            self.assertEqual(candidates[0]['wikidata'], f'Q{identity}')
            self.assertEqual(candidates[0]['matched_works'], self.item(identity)['works'])
            self.assertIn('Named artist', candidates[0]['credit'])
            self.assertIn('CC BY 4.0', candidates[0]['credit'])
            self.assertEqual(len(candidates), 2)
        self.assertTrue(all('openlibrary.org' not in call.args[0] for call in fetch.call_args_list))

    def test_wrong_entity_or_conflicting_authority_id_never_downloads(self):
        self.seed()
        for entity in (self.entity(human=False), self.entity(reciprocal='OL999A'),
                       self.entity(reciprocal=False, label='Different Person')):
            provider._entity_path('Q1').unlink(missing_ok=True)
            with self.subTest(entity=entity), patch.object(transport, 'fetch_json', return_value={'entities': {'Q1': entity}}) as fetch:
                self.assertEqual(provider.batch_candidates([self.item()]), [[]])
                self.assertEqual(fetch.call_count, 1)

    def test_matching_full_name_can_confirm_qid_when_reciprocal_property_absent(self):
        self.seed()
        entity = self.entity(reciprocal=False)
        with patch.object(transport, 'fetch_json', side_effect=[{'entities': {'Q1': entity}},
                {'query': {'pages': [self.picture('Portrait 1.jpg')]}}]):
            self.assertEqual(len(provider.batch_candidates([self.item()])[0]), 2)

    def test_incomplete_entities_defer_instead_of_producing_cached_negative(self):
        self.seed()
        for data in ({'entities': {}}, {'entities': None}, {'entities': {'Q1': {'claims': None}}}):
            with self.subTest(data=data), patch.object(transport, 'fetch_json', return_value=data) as fetch:
                with self.assertRaises(transport.ProviderOutage):
                    provider.batch_candidates([self.item()])
                self.assertFalse(fetch.call_args.kwargs['json_cacheable'](data))

    def test_incomplete_commons_response_defers_and_is_not_cacheable(self):
        self.seed()
        partial = {'query': {'pages': []}}
        with patch.object(transport, 'fetch_json', side_effect=[{'entities': {'Q1': self.entity()}}, partial]) as fetch:
            with self.assertRaises(transport.ProviderOutage):
                provider.batch_candidates([self.item()])
            self.assertFalse(fetch.call_args.kwargs['json_cacheable'](partial))

    def test_more_than_fifty_people_are_rejected_before_lookup(self):
        with self.assertRaises(ValueError):
            provider.batch_candidates([self.item()] * 51)

    def test_provider_outage_is_propagated_without_retries_or_fallback_calls(self):
        self.seed()
        error = transport.ProviderOutage('HTTP 429', status=429)
        with patch.object(transport, 'fetch_json', side_effect=error) as fetch:
            with self.assertRaises(transport.ProviderOutage) as caught:
                provider.batch_candidates([self.item()])
        self.assertIs(caught.exception, error)
        self.assertEqual(fetch.call_count, 1)

    def test_unsafe_image_urls_or_missing_rights_never_become_candidates(self):
        self.seed()
        for scenario in ('image', 'source', 'licence'):
            provider._entity_path('Q1').unlink(missing_ok=True)
            picture = self.picture('Portrait 1.jpg')
            info = picture['imageinfo'][0]
            if scenario == 'image':
                info['thumburl'] = info['url'] = 'http://127.0.0.1/private'
            elif scenario == 'source':
                info['descriptionurl'] = 'https://evil.invalid/fake-credit'
            else:
                info['extmetadata'] = {}
            with self.subTest(scenario=scenario), patch.object(transport, 'fetch_json', side_effect=[
                    {'entities': {'Q1': self.entity()}}, {'query': {'pages': [picture]}}]):
                self.assertEqual(provider.batch_candidates([self.item()]), [[]])

    def test_multiple_photos_chunk_commons_queries_at_fifty_files(self):
        items = [self.item(identity) for identity in range(1, 21)]
        for identity in range(1, 21):
            self.seed(identity)
        def fetch(url, **kwargs):
            params = parse_qs(urlsplit(url).query)
            if 'ids' in params:
                return {'entities': {f'Q{i}': self.entity(i, filenames=[f'{i}-{n}.jpg' for n in range(3)]) for i in range(1, 21)}}
            titles = params['titles'][0].split('|')
            self.assertLessEqual(len(titles), 50)
            return {'query': {'pages': [self.picture(title.removeprefix('File:')) for title in titles]}}
        with patch.object(transport, 'fetch_json', side_effect=fetch) as mocked:
            results = provider.batch_candidates(items)
        self.assertEqual(mocked.call_count, 3)
        self.assertTrue(all(len(candidates) == 6 for candidates in results))

    def test_later_commons_outage_keeps_first_group_candidates(self):
        items = [self.item(identity) for identity in range(1, 21)]
        for identity in range(1, 21):
            self.seed(identity)
        commons_requests = []
        error = transport.ProviderOutage('HTTP 429', status=429)
        def fetch(url, **kwargs):
            params = parse_qs(urlsplit(url).query)
            if 'ids' in params:
                return {'entities': {f'Q{i}': self.entity(i, filenames=[f'{i}-{n}.jpg' for n in range(3)]) for i in range(1, 21)}}
            commons_requests.append(url)
            if len(commons_requests) == 2:
                raise error
            return {'query': {'pages': [self.picture(title.removeprefix('File:'))
                                       for title in params['titles'][0].split('|')]}}
        with self.assertRaises(provider.PartialDiscovery) as caught:
            provider.batch_candidates(items, fetch)
        self.assertEqual(set(caught.exception.completed), set(range(16)))
        self.assertEqual(len(caught.exception.completed[15]), 6)
        self.assertNotIn(16, caught.exception.completed)
        self.assertEqual(caught.exception.status, 429)
        self.assertEqual(caught.exception.retry_after, error.retry_after)
        self.assertEqual(len(commons_requests), 2)

    def test_partial_commons_payload_preserves_verified_positive_and_complete_negative_only(self):
        for identity in range(1, 4):
            self.seed(identity)
        entity = self.entity(1)
        del entity['claims']['P18']
        with patch.object(transport, 'fetch_json', side_effect=[
                {'entities': {'Q1': entity, 'Q2': self.entity(2), 'Q3': self.entity(3)}},
                {'query': {'pages': [self.picture('Portrait 2.jpg')]}}]):
            with self.assertRaises(provider.PartialDiscovery) as caught:
                provider.batch_candidates([self.item(i) for i in range(1, 4)])
        self.assertEqual(set(caught.exception.completed), {0, 1})
        self.assertEqual(caught.exception.completed[0], [])
        self.assertEqual(len(caught.exception.completed[1]), 2)

    def test_changed_retry_batch_only_queries_unknown_authorities(self):
        for identity in range(1, 4):
            self.seed(identity)
        with patch.object(transport, 'fetch_json', side_effect=[
                {'entities': {'Q1': self.entity(1), 'Q2': self.entity(2)}},
                transport.ProviderOutage('HTTP 503', status=503)]):
            with self.assertRaises(provider.PartialDiscovery):
                provider.batch_candidates([self.item(1), self.item(2)])
        with patch.object(transport, 'fetch_json', side_effect=self.responses) as fetch:
            result = provider.batch_candidates([self.item(2), self.item(3)])
        params = parse_qs(urlsplit(fetch.call_args_list[0].args[0]).query)
        self.assertEqual(params['ids'], ['Q3'])
        self.assertEqual([rows[0]['wikidata'] for rows in result], ['Q2', 'Q3'])

    def test_partial_entity_response_checkpoints_present_entities_without_missing_negatives(self):
        with patch.object(transport, 'fetch_json', return_value={'entities': {'Q1': self.entity(1)}}):
            with self.assertRaises(transport.ProviderOutage):
                provider._entities(['Q1', 'Q2'], transport.fetch_json)
        self.assertTrue(provider._entity_path('Q1').exists())
        self.assertFalse(provider._entity_path('Q2').exists())
        with patch.object(transport, 'fetch_json', side_effect=self.responses) as fetch:
            result = provider._entities(['Q1', 'Q2'], transport.fetch_json)
        params = parse_qs(urlsplit(fetch.call_args.args[0]).query)
        self.assertEqual(params['ids'], ['Q2'])
        self.assertEqual(set(result), {'Q1', 'Q2'})

    def test_entity_checkpoint_inherits_http_age_and_expires_without_refresh(self):
        original_time = time.time() - 23 * 3600
        def cached_response(url, **kwargs):
            path = transport._response_cache_path(url, kwargs['allowed_hosts'], False, True)
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {'entities': {'Q1': self.entity()}}
            path.write_text(json.dumps(data))
            path.with_suffix('.json').write_text(json.dumps({'final_url': url}))
            os.utime(path, (original_time, original_time))
            return data
        provider._entities(['Q1'], cached_response)
        saved = json.loads(provider._entity_path('Q1').read_text())
        self.assertAlmostEqual(saved['fetched_at'], original_time, places=4)
        with patch.object(transport, 'fetch_json') as fetch:
            provider._entities(['Q1'], transport.fetch_json)
            fetch.assert_not_called()
        with patch.object(provider.time, 'time', return_value=original_time + 25 * 3600), \
                patch.object(transport, 'fetch_json', side_effect=self.responses) as fetch:
            provider._entities(['Q1'], transport.fetch_json)
            fetch.assert_called_once()

    def test_malformed_or_future_entity_checkpoint_requires_fresh_validation(self):
        path = provider._entity_path('Q1')
        path.parent.mkdir(parents=True, exist_ok=True)
        for changes in ({'entity': {'claims': None}}, {'fetched_at': time.time() + 1000}, {'qid': 'Q2'}):
            saved = {'schema': 1, 'qid': 'Q1', 'fetched_at': time.time(), 'entity': self.entity(), **changes}
            path.write_text(json.dumps(saved))
            with self.subTest(changes=changes), patch.object(transport, 'fetch_json', side_effect=self.responses) as fetch:
                self.assertEqual(provider._entities(['Q1'], transport.fetch_json)['Q1'], self.entity())
                fetch.assert_called_once()

    def test_fresh_partial_entities_do_not_inherit_a_retained_rejected_http_cache_age(self):
        def fresh_partial(url, **kwargs):
            path = transport._response_cache_path(url, kwargs['allowed_hosts'], False, True)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({'entities': {}}))
            path.with_suffix('.json').write_text(json.dumps({'final_url': url}))
            os.utime(path, (100, 100))
            return {'entities': {'Q1': self.entity()}}
        started = time.time()
        with self.assertRaises(transport.ProviderOutage):
            provider._entities(['Q1', 'Q2'], fresh_partial)
        saved = json.loads(provider._entity_path('Q1').read_text())
        self.assertGreaterEqual(saved['fetched_at'], started)
        with patch.object(transport, 'fetch_json') as fetch:
            provider._entities(['Q1'], transport.fetch_json)
            fetch.assert_not_called()

    def test_transport_timestamp_requires_body_and_matching_response_policy(self):
        url = 'https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q1'
        hosts = {'www.wikidata.org'}
        path = transport._response_cache_path(url, hosts, False, True)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{}')
        os.utime(path, (100, 100))
        self.assertIsNone(transport.response_cache_timestamp(url, allowed_hosts=hosts))
        path.with_suffix('.json').write_text(json.dumps({'final_url': url}))
        self.assertEqual(transport.response_cache_timestamp(url, allowed_hosts=hosts), 100)
        self.assertIsNone(transport.response_cache_timestamp(url, allowed_hosts=hosts, json_response=False))
