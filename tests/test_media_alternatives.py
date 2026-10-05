import io
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
from research import enrich_media_alternatives as media
from research import enrich_catalog_portraits as portraits
from research import media_transport as transport
from research.enrich_catalog_portraits import norm


def image_bytes(format='PNG'):
    stream = io.BytesIO()
    Image.new('RGB', (120, 180), 'white').save(stream, format=format)
    return stream.getvalue()


class AlternativeMediaTests(unittest.TestCase):
    def test_changed_reviewed_image_is_rejected_before_trying_next_candidate(self):
        blob = image_bytes()
        diagnostics = {}
        candidates = [
            {'image_url': 'https://example.org/changed.png', 'expected_sha256': '0' * 64},
            {'image_url': 'https://example.org/verified.png', 'expected_sha256': hashlib.sha256(blob).hexdigest()},
        ]
        with patch.object(media, 'fetch', return_value=blob):
            result = media.download_candidates(candidates, diagnostics)
        self.assertEqual(result['image_url'], candidates[1]['image_url'])
        self.assertEqual(len(diagnostics['candidate_rejections']), 1)
        self.assertIn('requires another identity review', diagnostics['candidate_rejections'][0])

    def test_google_rejects_wrong_author_and_partial_title(self):
        data = {'items': [
            {'id': 'wrong-author', 'volumeInfo': {'title': 'A Book', 'authors': ['Different Writer'], 'imageLinks': {'thumbnail': 'https://invalid/image'}}},
            {'id': 'wrong-title', 'volumeInfo': {'title': 'A Book: Study Guide', 'authors': ['Jane Writer'], 'imageLinks': {'thumbnail': 'https://invalid/image'}}},
        ]}
        with patch.object(media, 'fetch', return_value=data) as fetch:
            self.assertIsNone(media.google_cover({'title': 'A Book', 'authors': ['Jane Writer']}))
        self.assertEqual(fetch.call_count, 1)

    def test_google_retains_source_and_does_not_infer_edition_metadata(self):
        data = {'items': [{'id': 'volume', 'volumeInfo': {'title': 'A Book', 'authors': ['Jane Writer'], 'pageCount': 99, 'imageLinks': {'thumbnail': 'http://example.org/image'}}}]}
        with patch.object(media, 'fetch', side_effect=[data, image_bytes()]):
            result = media.google_cover({'title': 'A Book', 'authors': ['Jane Writer']})
        self.assertEqual(result['source'], 'https://books.google.com/books?id=volume')
        self.assertEqual(result['image_url'], 'https://example.org/image')
        self.assertNotIn('pages', result)

    def test_portrait_requires_catalog_work_corroboration(self):
        responses = [{'docs': [{'key': 'OL123A', 'name': 'Jane Writer', 'top_work': 'Other Book'}]},
                     {'name': 'Jane Writer', 'photos': [123]}, {'entries': [{'title': 'Other Book'}]}]
        with patch.object(media, 'fetch', side_effect=responses) as fetch:
            self.assertIsNone(media.openlibrary_portrait({'title': 'Jane Writer', 'authors': ['A Book']}))
        self.assertEqual(fetch.call_count, 3)
        self.assertIn('/works.json', fetch.call_args_list[-1].args[0])

    def test_author_without_photo_does_not_download_bibliography(self):
        for photos in ([], None, [-1, 0], [True, '123']):
            with self.subTest(photos=photos):
                responses = [{'docs': [{'key': 'OL123A', 'name': 'Jane Writer', 'top_work': 'Other Book'}]},
                             {'name': 'Jane Writer', 'photos': photos}]
                with patch.object(media, 'fetch', side_effect=responses) as fetch:
                    self.assertIsNone(media.openlibrary_portrait({'title': 'Jane Writer', 'authors': ['A Book']}))
                self.assertEqual(fetch.call_count, 2)
                self.assertFalse(any('/works.json' in call.args[0] for call in fetch.call_args_list))

    def test_photo_author_still_checks_bibliography_before_download(self):
        responses = [{'docs': [{'key': 'OL123A', 'name': 'Jane Writer', 'top_work': 'Other Book'}]},
                     {'name': 'Jane Writer', 'photos': [123]}, {'entries': [{'title': 'A Book',
                         'authors': [{'author': {'key': '/authors/OL123A'},
                                      'type': {'key': '/type/author_role'}}]}]}, image_bytes()]
        with patch.object(media, 'fetch', side_effect=responses) as fetch:
            match = media.openlibrary_portrait({'title': 'Jane Writer', 'authors': ['A Book']})
        self.assertEqual(match['matched_works'], ['A Book'])
        self.assertIn('/authors/OL123A.json', fetch.call_args_list[1].args[0])
        self.assertIn('/authors/OL123A/works.json', fetch.call_args_list[2].args[0])
        self.assertIn('/a/id/123-', fetch.call_args_list[3].args[0])

    def test_portrait_rejects_two_matching_author_identities(self):
        responses = [
            {'docs': [{'key': 'OL123A', 'name': 'Jane Writer', 'top_work': 'A Book'}, {'key': 'OL456A', 'name': 'Jane Writer', 'top_work': 'A Book'}]},
            {'photos': [123]}, {'photos': [456]},
        ]
        with patch.object(media, 'fetch', side_effect=responses):
            self.assertIsNone(media.openlibrary_portrait({'title': 'Jane Writer', 'authors': ['A Book']}))

    def test_bad_image_rejected_valid_gif_supported(self):
        with self.assertRaises(Exception):
            media.validate_image(b'<html>rate limit</html>')
        stream = io.BytesIO()
        Image.new('RGB', (100, 150)).save(stream, format='GIF')
        self.assertEqual(media.validate_image(stream.getvalue()), 'gif')

    def test_non_latin_identities_do_not_collapse_to_empty(self):
        self.assertNotEqual(norm('李白'), norm('杜甫'))
        self.assertTrue(norm('李白'))

    def test_wikipedia_requires_book_cover_caption(self):
        content = '{{Infobox book\n| author = [[Jane Writer]]\n| image = A Book.jpg\n| caption = Photograph of the author\n}}'
        data = {'query': {'pages': [{'title': 'A Book (novel)', 'revisions': [{'slots': {'main': {'content': content}}}]}]}}
        with patch.object(media, 'fetch', return_value=data) as fetch:
            self.assertIsNone(media.wikipedia_cover({'title': 'A Book', 'authors': ['Jane Writer']}))
        self.assertEqual(fetch.call_count, 1)

    def test_wikipedia_cover_retains_file_credit_and_license(self):
        content = '{{Infobox book\n| author = [[Jane Writer]]\n| image = A Book.jpg\n| caption = First edition cover\n}}'
        data = {'query': {'pages': [{'title': 'A Book (novel)', 'revisions': [{'slots': {'main': {'content': content}}}]}]}}
        info = {'query': {'pages': [{'imageinfo': [{'url': 'https://example.org/image', 'descriptionurl': 'https://example.org/credit', 'extmetadata': {'LicenseShortName': {'value': 'Public domain'}}}]}]}}
        with patch.object(media, 'fetch', side_effect=[data, info, image_bytes()]):
            result = media.wikipedia_cover({'title': 'A Book', 'authors': ['Jane Writer']})
        self.assertEqual(result['source'], 'https://example.org/credit')
        self.assertIn('Public domain', result['credit'])

    def test_google_invalid_first_candidate_does_not_hide_valid_second(self):
        data = {'items': [{'id': str(number), 'volumeInfo': {'title': 'A Book', 'authors': ['Jane Writer'],
            'imageLinks': {'thumbnail': f'https://example.org/{number}'}}} for number in (1, 2)]}
        with patch.object(media, 'fetch', side_effect=[data, b'<html>placeholder</html>', image_bytes()]):
            result = media.google_cover({'title': 'A Book', 'authors': ['Jane Writer']})
        self.assertEqual(result['image_url'], 'https://example.org/2')

    def test_image_outage_skips_other_candidates_on_the_same_host(self):
        candidates = [{'image_url': 'https://example.org/one'}, {'image_url': 'https://example.org/two'}]
        with patch.object(media, 'fetch', side_effect=transport.ProviderOutage('HTTP 429')) as fetch:
            with self.assertRaises(transport.ProviderOutage):
                media.download_candidates(candidates)
        self.assertEqual(fetch.call_count, 1)

    def test_image_outage_can_use_verified_candidate_on_a_different_host(self):
        candidates = [{'image_url': 'https://upload.wikimedia.org/original.jpg'},
                      {'image_url': 'https://upload.wikimedia.org/other.jpg'},
                      {'image_url': 'https://thumb.wikimedia.org/portrait.jpg',
                       'source': 'https://commons.wikimedia.org/wiki/File:Portrait.jpg',
                       'credit': 'Named photographer · CC BY 4.0.'}]
        diagnostics = {}
        with patch.object(media, 'fetch', side_effect=[transport.ProviderOutage('HTTP 429', status=429),
                                                     image_bytes()]) as fetch:
            result = media.download_candidates(candidates, diagnostics=diagnostics)
        self.assertEqual([call.args[0] for call in fetch.call_args_list],
                         [candidates[0]['image_url'], candidates[2]['image_url']])
        self.assertEqual(result['image_url'], candidates[2]['image_url'])
        self.assertEqual(result['credit'], candidates[2]['credit'])
        self.assertEqual(diagnostics['candidate_outages'][0]['http_status'], 429)

    def test_alternative_success_does_not_clear_a_persisted_host_cooldown(self):
        candidates = [{'image_url': 'https://upload.wikimedia.org/original.jpg'},
                      {'image_url': 'https://thumb.wikimedia.org/portrait.jpg'}]
        with tempfile.TemporaryDirectory() as directory, patch.object(transport, 'STATE', Path(directory)):
            until = transport.time.time() + 900
            transport._cooldown('upload.wikimedia.org', until, 429)
            saved = next((Path(directory) / 'hosts').glob('*.json'))
            original = saved.read_bytes()

            def fetch(url, **kwargs):
                if 'upload.wikimedia.org' in url:
                    transport._throttle('upload.wikimedia.org')
                return image_bytes()

            with patch.object(media, 'fetch', side_effect=fetch), patch.object(transport, 'build_opener') as network:
                self.assertIsNotNone(media.download_candidates(candidates))
            network.assert_not_called()
            self.assertEqual(saved.read_bytes(), original)

    def test_all_failed_candidates_raise_strongest_outage_with_latest_wait(self):
        candidates = [{'image_url': 'https://' + host + '/image'}
                      for host in ('one.example', 'two.example', 'three.example', 'one.example')]
        with patch.object(transport.time, 'time', return_value=1000):
            errors = [transport.ProviderOutage('HTTP 429', retry_after=1900, status=429),
                      transport.ProviderOutage('Provider returned an API error: maxlag',
                                              retry_after=3000, status=200, outage_type='maxlag'),
                      transport.CandidateRejected('HTTP 404')]
            with patch.object(media, 'fetch', side_effect=errors) as fetch:
                with self.assertRaises(transport.ProviderOutage) as raised:
                    media.download_candidates(candidates)
        self.assertEqual(fetch.call_count, 3)
        self.assertEqual(raised.exception.retry_after, 3000)
        self.assertEqual(raised.exception.status, 429)
        self.assertEqual(raised.exception.outage_type, 'unavailable')

    def test_alternative_outages_and_requests_remain_bounded(self):
        candidates = [{'image_url': f'https://host{index}.example/image'} for index in range(30)]
        diagnostics = {}
        with patch.object(media, 'fetch', side_effect=transport.ProviderOutage('HTTP 429', status=429)) as fetch:
            with self.assertRaises(transport.ProviderOutage):
                media.download_candidates(candidates, diagnostics=diagnostics)
        self.assertEqual(fetch.call_count, 16)
        self.assertEqual(len(diagnostics['candidate_outages']), 16)

    def test_candidate_rejections_are_auditable_and_success_still_advances(self):
        candidates = [{'image_url': 'https://example.org/one'}, {'image_url': 'https://example.org/two'}]
        diagnostics = {}
        with patch.object(media, 'fetch', side_effect=[
                transport.CandidateRejected('External host is outside the provider allowlist'), image_bytes()]):
            match = media.download_candidates(candidates, diagnostics=diagnostics)
        self.assertEqual(match['image_url'], 'https://example.org/two')
        self.assertEqual(diagnostics, {'candidate_count': 2,
            'candidate_rejections': ['External host is outside the provider allowlist']})

    def test_no_candidates_distinguished_from_download_rejections(self):
        diagnostics = {}
        self.assertIsNone(media.download_candidates([], diagnostics=diagnostics))
        self.assertEqual(diagnostics, {'candidate_count': 0, 'candidate_rejections': []})

    def test_portrait_uses_second_photo_after_missing_first(self):
        responses = [{'docs': [{'key': 'OL123A', 'name': 'Jane Writer', 'top_work': 'A Book'}]},
                     {'photos': [-1, 10, 11]}, transport.CandidateRejected('HTTP 404'), image_bytes()]
        with patch.object(media, 'fetch', side_effect=responses):
            result = media.openlibrary_portrait({'title': 'Jane Writer', 'authors': ['A Book']})
        self.assertIn('/a/id/11-', result['image_url'])
        self.assertEqual(result['author_key'], 'OL123A')

    def test_known_author_id_reuses_record_but_still_requires_work(self):
        item = {'title': 'Jane Writer', 'authors': ['A Book'], 'source_urls': ['https://openlibrary.org/authors/OL123A/Jane_Writer']}
        responses = [{'name': 'Jane Writer', 'photos': [10]}, {'entries': [{'title': 'A Book',
            'authors': [{'author': {'key': '/authors/OL123A'}, 'type': {'key': '/type/author_role'}}]}]}, image_bytes()]
        with patch.object(media, 'fetch', side_effect=responses) as fetch:
            result = media.openlibrary_portrait(item)
        self.assertEqual(result['author_key'], 'OL123A')
        self.assertNotIn('search/authors', fetch.call_args_list[0].args[0])
        with patch.object(media, 'fetch', side_effect=[responses[0], {'entries': [{'title': 'Different Book'}]}]):
            self.assertIsNone(media.openlibrary_portrait(item))

    def test_verified_candidates_survive_restart_during_image_outage(self):
        item = {'id': 1, 'title': 'A Book', 'authors': ['Jane Writer']}
        candidates = [{'source': 'https://example.org/book', 'image_url': 'https://example.org/image', 'credit': 'Recorded source'}]
        with tempfile.TemporaryDirectory() as directory, patch.object(transport, 'STATE', Path(directory)):
            with patch.object(media, 'provider_candidates', return_value=candidates) as lookup, patch.object(media, 'fetch', side_effect=transport.ProviderOutage('HTTP 503')):
                with self.assertRaises(transport.ProviderOutage):
                    media.cached_match(item, 'google-covers')
                self.assertEqual(lookup.call_count, 1)
            with patch.object(media, 'provider_candidates', side_effect=AssertionError('Metadata repeated')), patch.object(media, 'fetch', return_value=image_bytes()):
                result = media.cached_match(item, 'google-covers')
            self.assertEqual(result['source'], candidates[0]['source'])

    def test_publisher_image_keeps_host_and_robots_requirements(self):
        candidate = {'image_url': 'https://example.org/image', 'allowed_image_hosts': ['example.org'], 'image_respect_robots': True}
        with patch.object(media, 'fetch', return_value=image_bytes()) as fetch:
            self.assertIsNotNone(media.download_candidates([candidate]))
        self.assertEqual(fetch.call_args.kwargs['allowed_hosts'], ['example.org'])
        self.assertTrue(fetch.call_args.kwargs['respect_robots'])

    def test_missing_google_key_does_not_initialize_queue_or_fetch(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(media, 'RUN', Path(directory)), patch.dict(os.environ, {}, clear=True), patch.object(media.sys, 'argv', ['worker', 'google-covers']), patch.object(media, 'Queue') as queue, patch.object(media, 'fetch') as fetch:
            media.main()
            stats = json.loads((Path(directory) / 'google-covers-stats.json').read_text())
        self.assertEqual(stats['provider_status'], 'credential_required')
        self.assertEqual(stats['processed'], 0)
        queue.assert_not_called()
        fetch.assert_not_called()

    def test_truncated_jpeg_pixels_are_rejected_before_ingestion(self):
        blob = image_bytes('JPEG')[:-12]
        with Image.open(io.BytesIO(blob)) as image:
            image.verify()  # Demonstrate why header-only verification failed.
        with self.assertRaises(transport.CandidateRejected):
            media.validate_image(blob)

    def test_long_credit_preserves_one_complete_source_url(self):
        source = 'https://www.loc.gov/item/12345/'
        credit = media.image_credit({'source': source, 'credit': 'Historical depiction. ' + 'Rights details. ' * 60 + source})
        self.assertLessEqual(len(credit), 500)
        self.assertTrue(credit.endswith(source))
        self.assertEqual(credit.count(source), 1)

    def test_embedded_source_credentials_removed_from_downloaded_candidate_and_credit(self):
        source = 'https://example.org/item?token=sensitive-value'
        candidate = {'source': source, 'image_url': 'https://example.org/image', 'credit': 'Historical depiction from ' + source}
        with patch.object(media, 'fetch', return_value=image_bytes()):
            result = media.download_candidates([candidate])
        self.assertNotIn('sensitive-value', result['credit'])
        self.assertNotIn('token=', media.image_credit(candidate))


class WikimediaPortraitTests(unittest.TestCase):
    def item(self, **changes):
        return {'id': 1, 'title': 'Jane Writer', 'authors': ['Clear Thinking'], **changes}

    def page(self, text='Jane Writer wrote Clear Thinking.'):
        return {'title': 'Jane Writer', 'pageid': 10, 'extract': text,
                'pageprops': {'wikibase_item': 'Q123'}, 'fullurl': 'https://en.wikipedia.org/wiki/Jane_Writer'}

    def claim(self, value, rank='normal'):
        return {'rank': rank, 'mainsnak': {'datavalue': {'value': value}}}

    def entity(self, human=True, philosopher=False):
        claims = {'P31': [self.claim({'id': 'Q5' if human else 'Q11424'})],
                  'P18': [self.claim('Older.jpg'), self.claim('Preferred.jpg', 'preferred'), self.claim('Deprecated.jpg', 'deprecated')]}
        if philosopher:
            # Wikidata's real philosopher occupation, verified at /wiki/Q4964182.
            claims['P106'] = [self.claim({'id': 'Q4964182'})]
        return {'entities': {'Q123': {'claims': claims}}}

    def images(self):
        return {'query': {'pages': [{'title': 'File:' + name, 'imageinfo': [{
            'url': 'https://upload.wikimedia.org/' + name,
            'descriptionurl': 'https://commons.wikimedia.org/wiki/File:' + name,
            'extmetadata': {'LicenseShortName': {'value': 'CC BY 4.0'}, 'Artist': {'value': 'Named Artist'}}}]
        } for name in ('Older.jpg', 'Preferred.jpg')]}}

    def test_work_corroboration_requires_complete_title_tokens(self):
        self.assertEqual(portraits.corroborated_works(['Thinking'], 'Known for rethinking the issue.'), [])
        self.assertEqual(portraits.corroborated_works(['Clear Thinking'], 'She wrote “Clear Thinking”.'), ['Clear Thinking'])
        self.assertEqual(portraits.corroborated_works(['Clear Thinking'], 'Her unclear thinking attracted comment.'), [])

    def test_short_titles_need_publication_context_not_generic_words(self):
        self.assertEqual(portraits.corroborated_works(['Ragtime', 'Loving'],
            'He wrote Ragtime (1975), and she wrote Loving (1945).'), ['Ragtime', 'Loving'])
        self.assertEqual(portraits.corroborated_works(['Loving', 'It'],
            'Loving his family was important in 1945. It was a fine year.'), [])

    def test_disambiguation_uses_work_to_choose_novelist_not_namesake(self):
        disambiguation = {**self.page(), 'pageprops': {'wikibase_item': 'Q9', 'disambiguation': ''}}
        novelist = {**self.page(), 'title': 'Jane Writer (novelist)'}
        poet = {**self.page('Jane Writer wrote Other Poetry.'), 'title': 'Jane Writer (poet)',
                'pageprops': {'wikibase_item': 'Q456'}}
        missing = [{'title': 'Jane Writer (' + role + ')', 'missing': True}
                   for role in ('philosopher', 'writer', 'historian', 'author')]
        entities = self.entity()
        entities['entities']['Q456'] = {'claims': {'P31': [self.claim({'id': 'Q5'})]}}
        with patch.object(portraits, 'get_json', side_effect=[{'query': {'pages': [disambiguation]}},
                {'query': {'pages': [novelist, poet, *missing]}}, entities, self.images()]):
            self.assertEqual(len(portraits.wikimedia_candidates([self.item()])[1]), 2)

    def test_same_name_without_work_or_verified_occupation_is_rejected(self):
        response = {'query': {'pages': [self.page('Jane Writer has written many novels.')]}}
        with patch.object(portraits, 'get_json', side_effect=[response, response]) as fetch:
            self.assertEqual(portraits.wikimedia_candidates([self.item()]), {1: []})
        self.assertEqual(fetch.call_count, 2)

    def test_verified_human_candidates_keep_all_usable_photos_and_credits(self):
        with patch.object(portraits, 'get_json', side_effect=[{'query': {'pages': [self.page()]}}, self.entity(), self.images()]) as fetch:
            result = portraits.wikimedia_candidates([self.item()])[1]
        self.assertEqual([candidate['file'] for candidate in result], ['Preferred.jpg', 'Older.jpg'])
        self.assertIn('CC BY 4.0', result[0]['credit'])
        self.assertEqual(result[0]['matched_works'], ['Clear Thinking'])
        self.assertNotIn('blob', result[0])
        self.assertEqual(fetch.call_args_list[-1].args[1]['iiurlwidth'], 500)

    def test_nonhuman_entity_rejected_even_with_title_mention(self):
        missing = {'query': {'pages': [{'title': 'Jane Writer (' + role + ')', 'missing': True}
            for role in ('philosopher', 'novelist', 'writer', 'poet', 'historian', 'author')]}}
        with patch.object(portraits, 'get_json', side_effect=[{'query': {'pages': [self.page()]}},
                self.entity(human=False), missing]):
            self.assertEqual(portraits.wikimedia_candidates([self.item()]), {1: []})

    def test_ranked_exception_requires_explicit_philosopher_occupation(self):
        page = {'query': {'pages': [self.page('Jane Writer was a philosopher.')]}}
        item = self.item(authors=[], ranked=True)
        missing = {'query': {'pages': [{'title': 'Jane Writer (' + role + ')', 'missing': True}
            for role in ('philosopher', 'novelist', 'writer', 'poet', 'historian', 'author')]}}
        with patch.object(portraits, 'get_json', side_effect=[page, self.entity(), missing]):
            self.assertEqual(portraits.wikimedia_candidates([item]), {1: []})
        with patch.object(portraits, 'get_json', side_effect=[page, self.entity(philosopher=True), self.images()]):
            self.assertEqual(len(portraits.wikimedia_candidates([item])[1]), 2)

    def test_aliases_resolving_to_different_people_remain_unresolved(self):
        other = {**self.page(), 'title': 'J. Writer', 'pageprops': {'wikibase_item': 'Q456'}}
        with patch.object(portraits, 'get_json', return_value={'query': {'pages': [self.page(), other]}}) as fetch:
            self.assertEqual(portraits.wikimedia_candidates([self.item(title_aliases=['J. Writer'])]), {1: []})
        self.assertEqual(fetch.call_count, 1)
