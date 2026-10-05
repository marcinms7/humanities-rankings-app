import hashlib
import io
import json
import os
from concurrent.futures import Future
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image
from research import enrich_catalog_covers_public as public
from research import enrich_media_alternatives as alternatives
from research import media_cover_rejections as rejections
from research.media_transport import CandidateRejected


class ReviewedCoverRejectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.registry = Path(self.temp.name) / 'rejections.json'
        change = patch.object(rejections, 'REGISTRY', self.registry)
        change.start()
        self.addCleanup(change.stop)
        self.addCleanup(rejections._read_registry.cache_clear)
        self.blob = b'public image for a different book'
        self.item = {'id': 12, 'title': 'Catalog Book', 'authors': ['First Writer', 'Second Writer']}
        self.entry = {'work_id': 12, 'title': 'Catalog Book', 'authors': ['Second Writer', 'First Writer'],
                      'image_sha256': hashlib.sha256(self.blob).hexdigest(), 'reason': 'Image labels another book',
                      'source_url': 'https://openlibrary.org/works/OL12W'}

    def write(self, entries=None, **payload):
        self.registry.write_text(json.dumps({'version': 1, 'rejections': entries if entries is not None else [self.entry], **payload}))

    def test_exact_identity_and_digest_reject_with_review_reason(self):
        self.write()
        with self.assertRaisesRegex(CandidateRejected, 'Image labels another book'):
            rejections.reject_reviewed_cover(self.item, self.blob)

    def test_other_work_title_author_or_bytes_are_unaffected(self):
        self.write()
        for changes, blob in [({'id': 13}, self.blob), ({'title': 'Different Book'}, self.blob),
                              ({'authors': ['Another Writer']}, self.blob),
                              ({'authors': ['First Writer']}, self.blob),
                              ({'authors': ['first writer', 'Second Writer']}, self.blob),
                              ({'id': True}, self.blob), ({}, self.blob + b'new bytes')]:
            with self.subTest(changes=changes, blob=blob):
                self.assertIsNone(rejections.reject_reviewed_cover({**self.item, **changes}, blob))

    def test_display_title_pins_catalog_identity_instead_of_cleaned_lookup_title(self):
        self.write()
        with self.assertRaises(CandidateRejected):
            rejections.reject_reviewed_cover({**self.item, 'title': 'Cleaned lookup', 'display_title': 'Catalog Book'}, self.blob)
        self.assertIsNone(rejections.reject_reviewed_cover({**self.item, 'display_title': 'Changed Catalog Book'}, self.blob))

    def test_missing_registry_returns_empty_and_does_not_block_images(self):
        self.assertEqual(rejections.load_registry(), [])
        self.assertIsNone(rejections.reject_reviewed_cover(self.item, self.blob))
        self.write()
        self.assertEqual(len(rejections.load_registry()), 1)
        self.registry.unlink()
        self.assertEqual(rejections.load_registry(), [])

    def test_registry_cache_reused_and_invalidated_by_changed_metadata(self):
        self.write()
        before = rejections._read_registry.cache_info()
        rejections.load_registry()
        rejections.load_registry()
        after = rejections._read_registry.cache_info()
        self.assertEqual(after.misses - before.misses, 1)
        self.assertEqual(after.hits - before.hits, 1)
        original = self.registry.stat()
        self.write([{**self.entry, 'work_id': 13}])
        os.utime(self.registry, ns=(original.st_atime_ns, original.st_mtime_ns + 1_000_000))
        self.assertIsNone(rejections.reject_reviewed_cover(self.item, self.blob))

    def test_atomic_replacement_refreshes_even_with_same_size_and_mtime(self):
        self.write()
        rejections.load_registry()
        original = self.registry.stat()
        replacement = self.registry.with_suffix('.new')
        replacement.write_text(self.registry.read_text().replace('"work_id": 12', '"work_id": 13'))
        os.utime(replacement, ns=(original.st_atime_ns, original.st_mtime_ns))
        self.assertEqual(replacement.stat().st_size, original.st_size)
        replacement.replace(self.registry)
        self.assertIsNone(rejections.reject_reviewed_cover(self.item, self.blob))

    def test_callers_cannot_mutate_cached_decisions(self):
        self.write()
        loaded = rejections.load_registry()
        loaded[0]['authors'].clear()
        loaded[0]['image_sha256'] = '0' * 64
        with self.assertRaises(CandidateRejected):
            rejections.reject_reviewed_cover(self.item, self.blob)

    def test_malformed_registry_and_entries_fail_visibly_even_for_unrelated_item(self):
        for payload in ['{', '[]', '{"version":true,"rejections":[]}', '{"version":2,"rejections":[]}',
                        '{"version":1,"rejections":{}}']:
            with self.subTest(payload=payload):
                self.registry.write_text(payload)
                with self.assertRaises(ValueError):
                    rejections.reject_reviewed_cover({'id': 99}, self.blob)
        for changes in [{'work_id': True}, {'work_id': 0}, {'title': ''}, {'authors': 'A Writer'},
                        {'authors': [None]}, {'image_sha256': 'not-a-hash'}, {'reason': ''},
                        {'source_url': 'https://user:secret@openlibrary.org/works/OL12W'},
                        {'source_url': 'https://127.0.0.1/record'}, {'private_notes': 'unexpected'},
                        {'automatic_hold': 'true'}, {'automatic_hold': 1}, {'automatic_hold': None}]:
            with self.subTest(changes=changes):
                self.write([{**self.entry, **changes}])
                with self.assertRaises(ValueError):
                    rejections.load_registry()

    def test_source_url_is_optional_and_empty_author_identity_is_exact(self):
        entry = {key: value for key, value in self.entry.items() if key != 'source_url'}
        self.write([{**entry, 'authors': []}])
        with self.assertRaises(CandidateRejected):
            rejections.reject_reviewed_cover({**self.item, 'authors': []}, self.blob)
        self.assertIsNone(rejections.reject_reviewed_cover(self.item, self.blob))

    def test_scope_hold_requires_manual_review_for_other_images_but_bad_hash_stays_denied(self):
        self.write([{**self.entry, 'automatic_hold': True}])
        self.assertTrue(rejections.requires_scope_review(self.item))
        with self.assertRaisesRegex(CandidateRejected, 'scope requires manual review'):
            rejections.reject_reviewed_cover(self.item, b'another potentially partial volume')
        self.assertIsNone(rejections.reject_reviewed_cover(self.item, b'manually verified whole work', reviewed=True))
        with self.assertRaisesRegex(CandidateRejected, 'Image labels another book'):
            rejections.reject_reviewed_cover(self.item, self.blob, reviewed=True)

    def test_scope_hold_does_not_follow_changed_work_identity(self):
        self.write([{**self.entry, 'automatic_hold': True}])
        for changes in [{'id': 13}, {'title': 'Changed Book'}, {'authors': ['Different Writer']},
                        {'display_title': 'Changed Catalog Book'}]:
            with self.subTest(changes=changes):
                item = {**self.item, **changes}
                self.assertFalse(rejections.requires_scope_review(item))
                self.assertIsNone(rejections.reject_reviewed_cover(item, self.blob))

    def test_false_or_absent_hold_only_rejects_the_pinned_image(self):
        for changes in [{}, {'automatic_hold': False}]:
            with self.subTest(changes=changes):
                self.write([{**self.entry, **changes}])
                self.assertFalse(rejections.requires_scope_review(self.item))
                self.assertIsNone(rejections.reject_reviewed_cover(self.item, b'other image'))
                with self.assertRaises(CandidateRejected):
                    rejections.reject_reviewed_cover(self.item, self.blob, reviewed=True)

    def image(self, color='white'):
        output = io.BytesIO()
        Image.new('RGB', (100, 150), color).save(output, format='PNG')
        return output.getvalue()

    def test_held_public_and_cached_automatic_lookups_never_request_images_or_metadata(self):
        self.write([{**self.entry, 'automatic_hold': True}])
        item = {**self.item, '_cached_candidates': [{'image_url': 'https://example.org/cover.png'}]}
        with patch.object(public, 'openlibrary') as ol, patch.object(public, 'internet_archive') as archive:
            self.assertEqual(public.lookup(item, False, False), (None, 'identity_review_complete_work_scope'))
        ol.assert_not_called()
        archive.assert_not_called()
        with patch.object(alternatives, 'fetch') as fetch, patch.object(alternatives, 'stored_candidates') as cache:
            with self.assertRaisesRegex(CandidateRejected, 'scope'):
                alternatives.cached_match(item, 'google-covers', cached_only=True)
        fetch.assert_not_called()
        cache.assert_not_called()

    def test_reviewed_cached_replacement_passes_hold_but_known_bad_image_does_not(self):
        bad, good = self.image('black'), self.image('white')
        self.write([{**self.entry, 'automatic_hold': True, 'image_sha256': hashlib.sha256(bad).hexdigest()}])
        item = {**self.item, '_cached_candidates': [{'image_url': 'https://example.org/cover.png'}]}
        with patch.object(alternatives, 'fetch', return_value=good):
            self.assertEqual(alternatives.cached_match(item, 'reviewed-covers', cached_only=True)['blob'], good)
        diagnostics = {}
        with patch.object(alternatives, 'fetch', return_value=bad):
            self.assertIsNone(alternatives.cached_match(item, 'reviewed-covers', diagnostics, cached_only=True))
        self.assertIn('Image labels another book', diagnostics['candidate_rejections'][0])

    def test_portrait_cache_does_not_apply_book_namespace_rejections(self):
        blob = self.image()
        self.write([{**self.entry, 'automatic_hold': True, 'image_sha256': hashlib.sha256(blob).hexdigest()}])
        # Even a coincidentally equal person ID/title/list must not use book rules.
        item = {**self.item, '_cached_candidates': [{'image_url': 'https://example.org/portrait.png'}]}
        with patch.object(alternatives, 'fetch', return_value=blob):
            self.assertEqual(alternatives.cached_match(item, 'openlibrary-portraits', cached_only=True)['blob'], blob)

    def test_public_download_rejects_wrong_hash_and_tries_next_image(self):
        self.write()
        candidates = [{'provider': 'openlibrary', 'source_key': '/works/OL12W', 'cover_id': i} for i in (1, 2)]
        with patch.object(public, 'read_image', side_effect=[self.blob, b'other valid cover']):
            result = public._download_openlibrary(candidates, set(), item=self.item)
        self.assertEqual(result['cover_id'], 2)

    def test_public_save_result_rechecks_a_review_added_after_worker_completion(self):
        completed = Future()
        completed.set_result(({'image': self.blob, 'provider': 'openlibrary'}, None))
        self.assertIsNotNone(public.completed_lookup_result(self.item, completed)[0])
        self.write()
        result, reason = public.completed_lookup_result(self.item, completed)
        self.assertIsNone(result)
        self.assertIn('no_safe_cover_reviewed_rejection', reason)
        self.assertNotIn('worker_error', reason)

    def test_save_guard_cannot_be_bypassed_by_manual_provider_for_known_bad_bytes(self):
        self.write([{**self.entry, 'automatic_hold': True}])
        with patch.object(alternatives, 'validate_image', return_value='png'):
            for provider in ['google-covers', 'reviewed-covers', 'catalog-covers']:
                with self.subTest(provider=provider), self.assertRaisesRegex(CandidateRejected, 'Image labels another book'):
                    alternatives.save_match(provider, self.item, {'blob': self.blob})

    def test_manual_save_replacement_reaches_transaction_but_automatic_save_is_held(self):
        self.write([{**self.entry, 'automatic_hold': True}])
        class TransactionBoundaryReached(Exception):
            pass
        models = SimpleNamespace(Work=object, Edition=object, Person=object)
        with patch.object(alternatives, 'validate_image', return_value='png'), \
                patch.dict(sys.modules, {'backend.core.models': models}), \
                patch('django.db.transaction.atomic', side_effect=TransactionBoundaryReached):
            for provider in ['reviewed-covers', 'catalog-covers']:
                with self.subTest(provider=provider), self.assertRaises(TransactionBoundaryReached):
                    alternatives.save_match(provider, self.item, {'blob': b'reviewed complete work'})
            with self.assertRaisesRegex(CandidateRejected, 'scope requires manual review'):
                alternatives.save_match('google-covers', self.item, {'blob': b'unreviewed partial volume'})


if __name__ == '__main__':
    unittest.main()
