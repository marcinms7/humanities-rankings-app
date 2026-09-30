import io
import unittest
from unittest.mock import patch
from PIL import Image
from research import enrich_media_alternatives as media
from research.enrich_catalog_portraits import norm


class AlternativeMediaTests(unittest.TestCase):
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
        with patch.object(media, 'fetch', side_effect=[data, b'image']):
            result = media.google_cover({'title': 'A Book', 'authors': ['Jane Writer']})
        self.assertEqual(result['source'], 'https://books.google.com/books?id=volume')
        self.assertEqual(result['image_url'], 'https://example.org/image')
        self.assertNotIn('pages', result)

    def test_portrait_requires_catalog_work_corroboration(self):
        responses = [{'docs': [{'key': 'OL123A', 'name': 'Jane Writer', 'top_work': 'Other Book'}]}, {'entries': [{'title': 'Other Book'}]}]
        with patch.object(media, 'fetch', side_effect=responses) as fetch:
            self.assertIsNone(media.openlibrary_portrait({'title': 'Jane Writer', 'authors': ['A Book']}))
        self.assertEqual(fetch.call_count, 2)

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
        with patch.object(media, 'fetch', side_effect=[data, info, b'image']):
            result = media.wikipedia_cover({'title': 'A Book', 'authors': ['Jane Writer']})
        self.assertEqual(result['source'], 'https://example.org/credit')
        self.assertIn('Public domain', result['credit'])
