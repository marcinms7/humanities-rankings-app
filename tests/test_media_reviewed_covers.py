import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research import media_reviewed_covers as reviewed
from research.media_library_sources import publisher_eligible


class ReviewedCoverTests(unittest.TestCase):
    def setUp(self):
        self.entry = {'work_id': 1, 'title': 'A Book', 'authors': ['A Writer'],
                      'source_url': 'https://publisher.example/books/one',
                      'image_url': 'https://images.example/one.jpg',
                      'image_attribution': 'Publisher cover; rights retained by creator.',
                      'evidence': {'title': 'A Book', 'authors': ['A Writer'], 'note': 'Reviewed product cover.'}}
        self.item = {'id': 1, 'title': 'A Book', 'authors': ['A Writer'], 'provider_identifiers': {'isbn': []}}

    def registry(self, entry=None):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'reviewed.json'
            path.write_text(json.dumps({'version': 1, 'candidates': [entry or self.entry]}))
            return reviewed.load_registry(path)

    def test_changed_catalog_identity_is_not_an_implicit_alias(self):
        registry = self.registry()
        for changed in ({'title': 'Another Book'}, {'authors': ['Another Writer']}, {'id': 2}):
            self.assertEqual(reviewed.prepare_items([{**self.item, **changed}], registry=registry), [])

    def test_source_revision_changes_only_its_item_fingerprint(self):
        original = reviewed.prepare_items([self.item], registry=self.registry())[0]
        newer = reviewed.prepare_items([self.item], registry=self.registry(
            {**self.entry, 'image_url': 'https://images.example/two.jpg'}))[0]
        self.assertNotEqual(original['provider_identifiers'], newer['provider_identifiers'])
        self.assertEqual(self.item['provider_identifiers'], {'isbn': []})

    def test_discovery_rereads_withdrawn_registry(self):
        prepared = reviewed.prepare_items([self.item], registry=self.registry())[0]
        with patch.object(reviewed, 'load_registry', return_value={}):
            self.assertEqual(reviewed.candidates(prepared), [])

    def test_private_or_credential_bearing_urls_are_rejected(self):
        for url in ('https://localhost/a', 'https://127.0.0.1/a', 'https://example.com/a?token=secret',
                    'http://example.com/a', 'https://user:password@example.com/a'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.registry({**self.entry, 'image_url': url})

    def test_missing_evidence_and_unreviewed_redirect_hosts_are_rejected(self):
        for changed in ({'evidence': {}}, {'image_attribution': ''},
                        {'allowed_image_hosts': ['unrelated.example']},
                        {'allowed_image_hosts': ['images.example', '127.0.0.1']},
                        {'cover_basis': 'edition_matched'}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self.registry({**self.entry, **changed})

    def test_reviewed_metadata_stays_representative_and_respects_robots(self):
        with patch.object(reviewed, 'load_registry', return_value=self.registry()):
            match = reviewed.candidates(self.item)[0]
        self.assertEqual(match['cover_basis'], 'representative_work')
        self.assertTrue(match['image_respect_robots'])
        self.assertEqual(match['source'], self.entry['source_url'])

    def test_ineligible_publisher_inputs_are_not_claimed_as_searches(self):
        self.assertFalse(publisher_eligible({'source_urls': ['https://openlibrary.org/works/OL1W']}))
        self.assertFalse(publisher_eligible({'publishers': ['Macmillan'], 'isbns': ['bad']}))
        self.assertTrue(publisher_eligible({'publishers': ['Macmillan'], 'isbns': ['9780141439518']}))
        self.assertTrue(publisher_eligible({'publishers': ['Faber & Faber']}))
        self.assertTrue(publisher_eligible({'source_urls': ['https://www.penguinrandomhouse.com/books/1']}))

    def test_only_identified_public_api_images_use_the_api_robots_policy(self):
        api = 'https://covers.openlibrary.org/b/id/123-L.jpg?default=false'
        entry = {**self.entry, 'source_url': 'https://openlibrary.org/works/OL123W',
                 'image_url': 'https://ia801234.us.archive.org/view_archive.php?file=123-L.jpg',
                 'evidence': {**self.entry['evidence'], 'api_image_url': api}}
        self.assertTrue(reviewed.is_openlibrary_api_image(entry))
        self.assertFalse(reviewed.is_openlibrary_api_image({**entry, 'image_url': 'https://archive.org/unrelated'}))
        self.assertFalse(reviewed.is_openlibrary_api_image({**entry, 'source_url': self.entry['source_url']}))
        self.assertFalse(reviewed.is_openlibrary_api_image({**entry, 'image_url': 'https://evil.example/view_archive.php'}))
