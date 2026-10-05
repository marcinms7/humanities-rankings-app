"""Offline regressions for Wikimedia's advertised thumbnail-host migration."""
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.request import Request

from PIL import Image

from research import enrichment_queue, enrich_catalog_portraits as portraits
from research import enrich_media_alternatives as media, media_linked_portraits as linked
from research import media_transport as transport
from research.media_matching import MATCHER_VERSION
from research.media_wikimedia import WIKIMEDIA_IMAGE_HOSTS


class WikimediaImagePolicyTests(unittest.TestCase):
    def test_policy_revision_reuses_verified_images_but_reopens_old_empty_results(self):
        item = {'id': 1, 'title': 'Samuel Butler'}
        current, previous = MagicMock(), MagicMock()
        current.get.return_value = None
        previous.get.return_value = []
        self.assertIsNone(portraits.cached_candidates(item, current, previous))
        current.put.assert_not_called()
        verified = [{'image_url': 'https://thumb.wikimedia.org/portrait.jpg', 'matched_works': ['Known book']}]
        previous.get.return_value = verified
        current.put.side_effect = lambda item, candidates: candidates
        self.assertEqual(portraits.cached_candidates(item, current, previous), verified)
        current.put.assert_called_once_with(item, verified)

    def claim(self, value):
        return {'mainsnak': {'datavalue': {'value': value}}}

    def image(self):
        return {'query': {'pages': [{'title': 'File:Butler.jpg', 'imageinfo': [{
            'thumburl': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/a/ab/Butler.jpg/500px-Butler.jpg',
            'url': 'https://upload.wikimedia.org/wikipedia/commons/a/ab/Butler.jpg',
            'descriptionurl': 'https://commons.wikimedia.org/wiki/File:Butler.jpg',
            'extmetadata': {'LicenseShortName': {'value': 'Public domain'}}}]}]}}

    def check_download(self, candidate):
        blob = io.BytesIO()
        Image.new('RGB', (120, 180), 'white').save(blob, format='PNG')

        def fetch(url, **kwargs):
            transport.validate_external_url(url, kwargs['allowed_hosts'])
            return blob.getvalue()

        with patch.object(media, 'fetch', side_effect=fetch):
            result = media.download_candidates([candidate])
        self.assertIsNotNone(result)
        self.assertEqual(result['image_url'], self.image()['query']['pages'][0]['imageinfo'][0]['thumburl'])
        self.assertIn('Public domain', result['credit'])

    def test_wikimedia_advertised_thumbnail_is_accepted_after_identity_checks(self):
        item = {'id': 1, 'title': 'Samuel Butler', 'works': ['The Way of All Flesh']}
        page = {'title': item['title'], 'pageid': 1, 'extract': 'He wrote The Way of All Flesh.',
                'pageprops': {'wikibase_item': 'Q312829'}}
        entity = {'entities': {'Q312829': {'claims': {
            'P31': [self.claim({'id': 'Q5'})], 'P18': [self.claim('Butler.jpg')]}}}}
        with patch.object(portraits, 'get_json', side_effect=[{'query': {'pages': [page]}}, entity, self.image()]):
            candidates = portraits.wikimedia_candidates([item])[1]
        self.check_download(candidates[0])
        self.assertEqual(candidates[0]['matched_works'], item['works'])

    def test_no_image_skips_full_articles_for_entire_batch(self):
        items = [{'id': index, 'title': f'Writer {index}', 'works': ['The Way of All Flesh']}
                 for index in range(1, 11)]
        pages = [{'title': item['title'], 'pageid': item['id'], 'extract': 'A writer.',
                  'pageprops': {'wikibase_item': f'Q{item["id"]}'}} for item in items]
        entities = {f'Q{item["id"]}': {'claims': {'P31': [self.claim({'id': 'Q5'})]}}
                    for item in items}
        def response(host, params):
            if 'ids' in params:
                return {'entities': entities}
            self.assertNotIn('pageids', params)
            requested = params['titles'].split('|')
            return {'query': {'pages': [page for page in pages if page['title'] in requested] +
                [{'title': title, 'missing': True} for title in requested if '(' in title]}}
        with patch.object(portraits, 'get_json', side_effect=response) as fetch:
            candidates = portraits.wikimedia_candidates(items)
        self.assertTrue(all(value == [] for value in candidates.values()))
        self.assertEqual(fetch.call_count, 5)

    def test_image_still_requires_full_article_work_corroboration(self):
        item = {'id': 1, 'title': 'Samuel Butler', 'works': ['The Way of All Flesh']}
        page = {'title': item['title'], 'pageid': 1, 'extract': 'A writer.',
                'pageprops': {'wikibase_item': 'Q312829'}}
        entity = {'entities': {'Q312829': {'claims': {
            'P31': [self.claim({'id': 'Q5'})], 'P18': [self.claim('Butler.jpg')]}}}}
        for text, expected in [('His book was The Way of All Flesh.', 1), ('He wrote a different book.', 0)]:
            missing = {'query': {'pages': [{'title': 'Samuel Butler (' + role + ')', 'missing': True}
                for role in ('philosopher', 'novelist', 'writer', 'poet', 'historian', 'author')]}}
            with self.subTest(text=text), patch.object(portraits, 'get_json', side_effect=[
                    {'query': {'pages': [page]}}, entity,
                    {'query': {'pages': [{'pageid': 1, 'extract': text}]}}, self.image() if expected else missing]) as fetch:
                candidates = portraits.wikimedia_candidates([item])[1]
                self.assertEqual(len(candidates), expected)
                self.assertEqual(fetch.call_args_list[2].args[1]['pageids'], 1)

    def test_intro_queries_respect_twenty_extract_limit(self):
        items = [{'id': index, 'title': f'Writer {index}', 'works': ['The Way of All Flesh']}
                 for index in range(1, 22)]
        def response(host, params):
            if 'titles' not in params:
                return {'entities': {}}
            titles = params['titles'].split('|')
            self.assertLessEqual(len(titles), 20)
            return {'query': {'pages': [{'title': title, 'pageid': int(title.split()[-1]),
                'extract': 'Wrote The Way of All Flesh.',
                'pageprops': {'wikibase_item': 'Q' + title.split()[-1]}} for title in titles]}}
        with patch.object(portraits, 'get_json', side_effect=response) as fetch:
            self.assertEqual(len(portraits.wikimedia_candidates(items)), 21)
        self.assertEqual(fetch.call_count, 3)

    def test_linked_wikidata_advertised_thumbnail_is_accepted_after_reciprocal_check(self):
        item = {'title': 'Samuel Butler', 'linked_works': [{
            'title': 'The Way of All Flesh', 'source_urls': ['https://openlibrary.org/works/OL22372W']}]}
        work = {'title': 'The Way of All Flesh', 'authors': [{'author': {'key': '/authors/OL24761A'}}]}
        author = {'name': item['title'], 'remote_ids': {'wikidata': 'Q312829'}}
        entity = {'entities': {'Q312829': {'claims': {
            'P31': [self.claim({'id': 'Q5'})], 'P648': [self.claim('OL24761A')],
            'P18': [self.claim('Butler.jpg')]}}}}
        with patch.object(linked, 'fetch_json', side_effect=[work, author, entity, self.image()]):
            candidates = linked.wikidata_candidates(item)
        self.check_download(candidates[0])
        self.assertEqual(candidates[0]['author_key'], 'OL24761A')

    def test_thumbnail_redirects_allow_only_exact_wikimedia_hosts(self):
        old = 'https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Butler.jpg/500px-Butler.jpg'
        new = self.image()['query']['pages'][0]['imageinfo'][0]['thumburl']
        redirects = transport._Redirects(WIKIMEDIA_IMAGE_HOSTS, 'upload.wikimedia.org', False)
        with patch.object(transport, '_throttle'):
            self.assertEqual(redirects.redirect_request(Request(old), None, 301, 'Moved', {}, new).full_url, new)
            for host in ('thumb.wikimedia.org.evil.test', 'arbitrary.wikimedia.org',
                         'thumb.wikimedia.org@evil.test', 'localhost', '127.0.0.1'):
                with self.subTest(host=host), self.assertRaises(transport.CandidateRejected):
                    redirects.redirect_request(Request(old), None, 301, 'Moved', {}, 'https://' + host + '/image')

    def test_old_thumbnail_failure_reopens_and_preserves_old_audit_and_cache(self):
        item = {'id': 1, 'title': 'Samuel Butler', 'works': ['The Way of All Flesh']}
        old_policy = MATCHER_VERSION + ':wikimedia-human-work-confirmed-v5'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(enrichment_queue, 'STATE', root / 'queue'), patch.object(transport, 'STATE', root / 'http'):
                ledger = root / 'outcomes.jsonl'
                queue = enrichment_queue.Queue('portraits', ledger)
                try:
                    queue.due(item, old_policy)
                    with ledger.open('a') as stream:
                        queue.finish(item, {'work_id': item['id'], 'status': 'no_safe_match'}, stream)
                    audit = ledger.read_bytes()
                    old_store = transport.CandidateStore('wikimedia-portraits', version=old_policy)
                    old_store.put(item, [{'image_url': self.image()['query']['pages'][0]['imageinfo'][0]['thumburl'],
                                          'allowed_image_hosts': ['upload.wikimedia.org', 'commons.wikimedia.org']}])
                    self.assertFalse(queue.due(item, old_policy))
                    self.assertTrue(queue.due(item, portraits.POLICY))
                    self.assertEqual(ledger.read_bytes(), audit)
                    self.assertTrue(old_store.get(item))
                    self.assertIsNone(transport.CandidateStore('wikimedia-portraits', version=portraits.POLICY).get(item))
                finally:
                    queue.close()
