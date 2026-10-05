import io
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image
from research import enrich_catalog_covers_public as media
from research.media_transport import CandidateRejected, ProviderOutage
from research.media_provider_health import outcome


class PublicCoverTests(unittest.TestCase):
    def item(self, **values):
        return {'id': 1, 'title': 'Pride and Prejudice', 'authors': ['Jane Austen'], **values}

    def doc(self, **values):
        return {'key': '/works/OL1W', 'title': 'Pride and Prejudice', 'author_name': ['Austen, Jane, 1775-1817'],
                'cover_i': 10, 'edition_count': 2, **values}

    def test_identifiers_require_valid_hosts_and_checksums_and_skip_archives(self):
        editions = [
            SimpleNamespace(source_url='https://openlibrary.org/works/OL123W/Pride', cover_source_url='',
                            isbn='978-0-14-143951-8', translation_notes='Open Library ID: OL456M', is_archived=False),
            SimpleNamespace(source_url='https://openlibrary.org.evil.test/works/OL999W', cover_source_url='',
                            isbn='9780141439519', translation_notes='Unrelated token OL666W', is_archived=False),
            SimpleNamespace(source_url='https://openlibrary.org/works/OL888W', cover_source_url='',
                            isbn='', translation_notes='', is_archived=True),
        ]
        self.assertEqual(media.edition_identifiers(editions), {
            'openlibrary': ['/works/OL123W', '/books/OL456M'], 'isbn': ['9780141439518']})
        self.assertEqual(media.valid_isbn('0-14-143951-3'), '0141439513')

    def test_item_reuses_active_edition_and_verified_alias_metadata(self):
        authors = SimpleNamespace(all=lambda: [SimpleNamespace(pk=5, name='Jane Austen')])
        default = SimpleNamespace(pk=11, isbn='0141439513', is_archived=False, source_url='https://www.penguinrandomhouse.com/books/1/',
                                  cover_source_url='', publisher='Penguin', translation_notes='')
        alternative = SimpleNamespace(pk=10, isbn='', is_archived=False, source_url='https://openlibrary.org/works/OL123W',
                                      cover_source_url='', publisher='', translation_notes='')
        work = SimpleNamespace(pk=1, title='Pride and Prejudice', authors=authors, original_year=1813,
                               media_editions=[alternative, default], default_edition=default, default_edition_id=11,
                               shared_priority=True)
        item = media.cover_lookup_item(work, {'works': {'1': ['Orgueil et Préjugés']}, 'people': {'5': ['Austen, Jane']}})
        self.assertEqual(item['edition_id'], 11)
        self.assertEqual(item['title_aliases'], ['Orgueil et Préjugés'])
        self.assertEqual(item['author_aliases'], ['Austen, Jane'])
        self.assertEqual(item['isbns'], ['0141439513'])
        self.assertEqual(item['provider_identifiers']['openlibrary'], ['/works/OL123W'])
        self.assertEqual(item['publishers'], ['Penguin'])
        self.assertEqual(item['source_urls'][0], default.source_url)
        self.assertTrue(item['shared_priority'])

    def test_saved_identifier_is_revalidated_and_avoids_search(self):
        responses = [
            {'title': 'Pride and Prejudice', 'authors': [{'author': {'key': '/authors/OL1A'}}], 'covers': [10]},
            {'name': 'Austen, Jane'},
        ]
        with patch.object(media, 'read_json', side_effect=responses) as fetch, patch.object(media, 'read_image', return_value=b'valid'):
            match, reason = media.openlibrary(self.item(provider_identifiers={'openlibrary': ['/works/OL123W']}))
        self.assertIsNone(reason)
        self.assertEqual(match['source_key'], '/works/OL123W')
        self.assertFalse(any('search.json' in call.args[0] for call in fetch.call_args_list))

    def test_saved_identifier_wrong_author_never_supplies_an_image(self):
        responses = [
            {'title': 'Pride and Prejudice', 'authors': [{'author': {'key': '/authors/OL1A'}}], 'covers': [10]},
            {'name': 'Different Writer'}, {'docs': []},
        ]
        with patch.object(media, 'read_json', side_effect=responses), patch.object(media, 'read_image') as image:
            match, reason = media.openlibrary(self.item(provider_identifiers={'openlibrary': ['/works/OL123W']}))
        self.assertIsNone(match)
        self.assertEqual(reason, 'openlibrary_no_safe_cover')
        image.assert_not_called()

    def test_isbn_record_needs_isbn_title_and_author_agreement(self):
        isbn = '9780141439518'
        responses = [
            {'key': '/books/OL2M', 'title': 'Pride and Prejudice', 'isbn_13': [isbn],
             'authors': [{'key': '/authors/OL1A'}], 'covers': [10]},
            {'name': 'Jane Austen'},
        ]
        with patch.object(media, 'read_json', side_effect=responses), patch.object(media, 'read_image', return_value=b'valid'):
            match, _ = media.openlibrary(self.item(provider_identifiers={'isbn': [isbn]}))
        self.assertEqual(match['source_key'], '/books/OL2M')
        wrong_record = {**responses[0], 'isbn_13': ['9780141439519']}
        with patch.object(media, 'read_json', side_effect=[wrong_record, {'docs': []}]), patch.object(media, 'read_image') as image:
            match, _ = media.openlibrary(self.item(provider_identifiers={'isbn': [isbn]}))
        self.assertIsNone(match)
        image.assert_not_called()

    def test_book_record_can_use_a_verified_linked_work_author(self):
        responses = [
            {'title': 'Pride and Prejudice', 'works': [{'key': '/works/OL1W'}], 'covers': [10]},
            {'title': 'Pride and Prejudice', 'authors': [{'author': {'key': '/authors/OL1A'}}]},
            {'name': 'Jane Austen'},
        ]
        with patch.object(media, 'read_json', side_effect=responses), patch.object(media, 'read_image', return_value=b'valid'):
            match, _ = media.openlibrary(self.item(provider_identifiers={'openlibrary': ['/books/OL2M']}))
        self.assertEqual(match['source_key'], '/books/OL2M')

    def test_mismatched_edition_author_is_not_overridden_by_linked_work(self):
        responses = [
            {'title': 'Pride and Prejudice', 'works': [{'key': '/works/OL1W'}],
             'authors': [{'key': '/authors/OL2A'}], 'covers': [10]},
            {'name': 'Someone Else'}, {'docs': []},
        ]
        with patch.object(media, 'read_json', side_effect=responses), patch.object(media, 'read_image') as image:
            match, _ = media.openlibrary(self.item(provider_identifiers={'openlibrary': ['/books/OL2M']}))
        self.assertIsNone(match)
        image.assert_not_called()

    def test_bad_first_image_falls_back_to_linked_edition_without_search_repeat(self):
        with patch.object(media, 'read_json', side_effect=[{'docs': [self.doc()]}, {'entries': [{'covers': [10, -1, 20, 30]}]}]) as fetch:
            with patch.object(media, 'read_image', side_effect=[CandidateRejected('gone'), b'valid']) as image:
                match, reason = media.openlibrary(self.item())
        self.assertIsNone(reason)
        self.assertEqual(match['cover_id'], 20)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(image.call_count, 2)

    def test_image_attempts_are_bounded(self):
        responses = [{'docs': [self.doc()]}, {'entries': [{'covers': list(range(11, 30))}]}]
        with patch.object(media, 'read_json', side_effect=responses), patch.object(media, 'read_image', side_effect=CandidateRejected('bad')) as image:
            match, reason = media.openlibrary(self.item())
        self.assertIsNone(match)
        self.assertEqual(image.call_count, media.MAX_IMAGE_CANDIDATES)
        self.assertEqual(reason, 'openlibrary_no_usable_image')

    def test_rate_limit_stops_image_candidates_and_records_provider_deferral(self):
        item = self.item()
        outage = ProviderOutage('Rate limited', status=429)
        with patch.object(media, 'read_json', return_value={'docs': [self.doc()]}), patch.object(media, 'read_image', side_effect=outage) as image:
            match, reason = media.openlibrary(item)
        self.assertIsNone(match)
        self.assertIn('provider_blocked', reason)
        self.assertTrue(item['_provider_outage'])
        self.assertEqual(item['_retry_after'], outage.retry_after)
        self.assertEqual(image.call_count, 1)

    def test_a_wrong_first_author_query_does_not_prevent_second_author_search(self):
        wrong = self.doc(title='A Guide to Pride and Prejudice')
        with patch.object(media, 'read_json', side_effect=[{'docs': [wrong]}, {'docs': [self.doc(key='/works/OL2W')]}]) as fetch:
            with patch.object(media, 'read_image', return_value=b'valid'):
                match, _ = media.openlibrary(self.item(authors=['First Writer', 'Jane Austen']))
        self.assertIsNotNone(match)
        self.assertEqual(fetch.call_count, 2)

    def test_equal_independent_work_identities_are_ambiguous(self):
        with patch.object(media, 'read_json', return_value={'docs': [self.doc(), self.doc(key='/works/OL2W')]}):
            with patch.object(media, 'read_image') as image:
                match, reason = media.openlibrary(self.item())
        self.assertIsNone(match)
        self.assertEqual(reason, 'openlibrary_ambiguous')
        image.assert_not_called()

    def test_archive_tries_next_verified_candidate_but_rejects_wrong_author(self):
        docs = [{'title': 'Pride and Prejudice', 'creator': ['Jane Austen'], 'identifier': key} for key in ['first', 'second']]
        docs.insert(0, {'title': 'Pride and Prejudice', 'creator': ['Someone Else'], 'identifier': 'wrong'})
        with patch.object(media, 'read_json', return_value={'response': {'docs': docs}}):
            with patch.object(media, 'read_image', side_effect=[CandidateRejected('gone'), b'valid']) as image:
                match, reason = media.internet_archive(self.item())
        self.assertIsNone(reason)
        self.assertEqual(match['identifier'], 'second')
        self.assertEqual(image.call_count, 2)

    def test_successful_archive_fallback_does_not_remain_provider_blocked(self):
        item = self.item()
        with patch.object(media, 'read_json', side_effect=ProviderOutage('Rate limited')):
            with patch.object(media, 'internet_archive', return_value=({'provider': 'internet_archive'}, None)):
                match, reason = media.lookup(item, False, False)
        self.assertIsNone(reason)
        self.assertEqual(match['provider'], 'internet_archive')
        self.assertNotIn('_provider_outage', item)
        self.assertNotIn('_provider_failures', item)
        self.assertNotIn('_retry_after', item)

    def test_transient_cover_failure_reaches_runner_without_fifteen_minute_penalty(self):
        item = self.item()
        now = time.time()
        failure = ProviderOutage('HTTP 503', status=503, outage_type='transient', retry_after=now + 60)
        with patch.object(media, 'read_json', side_effect=failure):
            media.lookup(item, True, False)
        stats = {'processed': 1, 'provider_errors': 1, **media.outage_summary(item['_provider_failures'])}
        health = outcome({}, stats, now=now)
        self.assertEqual(health['outage_type'], 'transient')
        self.assertEqual(health['http_status'], 503)
        self.assertEqual(health['retry_at'], failure.retry_after)

    def test_combined_cover_failures_keep_rate_limit_and_longest_retry(self):
        item = self.item()
        now = time.time()
        limited = ProviderOutage('HTTP 429', status=429, retry_after=now + 900)
        unavailable = ProviderOutage('HTTP 503', status=503, outage_type='transient', retry_after=now + 1800)
        for errors in ((limited, unavailable), (unavailable, limited)):
            item = self.item()
            for error in errors:
                media._provider_failure(item, 'openlibrary', error)
            stats = media.outage_summary(item['_provider_failures'])
            self.assertEqual(stats['http_status'], 429)
            self.assertEqual(stats['outage_type'], 'unavailable')
            self.assertEqual(stats['retry_after'], unavailable.retry_after)
            self.assertEqual(outcome({}, stats, now=now)['retry_at'], unavailable.retry_after)

    def test_cover_transport_uses_shared_identification_configuration(self):
        with patch.object(media, 'fetch_json', return_value={}) as metadata:
            media.read_json('https://openlibrary.org/search.json', {'title': 'Example'})
        self.assertNotIn('headers', metadata.call_args.kwargs)
        with patch.object(media, 'fetch_bytes', return_value=self.image_blob((100, 150))) as download:
            media.read_image('https://covers.openlibrary.org/b/id/1-L.jpg')
        self.assertNotIn('headers', download.call_args.kwargs)

    def test_image_validation_rejects_html_and_tiny_placeholders(self):
        for content in [b'<html>gone</html>', self.image_blob((1, 1))]:
            with patch.object(media, 'fetch_bytes', return_value=content):
                with self.assertRaises(CandidateRejected):
                    media.read_image('https://covers.openlibrary.org/b/id/1-L.jpg')
        valid = self.image_blob((100, 150))
        with patch.object(media, 'fetch_bytes', return_value=valid):
            self.assertEqual(media.read_image('https://covers.openlibrary.org/b/id/1-L.jpg'), valid)

    @staticmethod
    def image_blob(size):
        output = io.BytesIO()
        Image.new('RGB', size).save(output, format='PNG')
        return output.getvalue()

    def test_truncated_jpeg_is_rejected_even_when_header_verifies(self):
        output = io.BytesIO()
        Image.new('RGB', (300, 400)).save(output, format='JPEG')
        content = output.getvalue()[:-1000]
        with Image.open(io.BytesIO(content)) as picture:
            picture.verify()
        with patch.object(media, 'fetch_bytes', return_value=content):
            with self.assertRaises(CandidateRejected):
                media.read_image('https://covers.openlibrary.org/b/id/1-L.jpg')
