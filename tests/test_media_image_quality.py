"""Only byte-identical reviewed placeholders may be rejected/reopened."""
import hashlib
import io
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image
from research import enrichment_queue, media_image_quality as quality, media_inventory
from research import enrich_catalog_covers_public as public, enrich_media_alternatives as alternatives
from research.media_transport import CandidateRejected


class ExactPlaceholderTests(unittest.TestCase):
    def setUp(self):
        output = io.BytesIO()
        Image.new('RGB', (320, 220), '#334455').save(output, format='PNG')
        self.placeholder = output.getvalue()
        self.digest = hashlib.sha256(self.placeholder).hexdigest()
        change = patch.object(quality, 'KNOWN_PLACEHOLDERS', {self.digest: len(self.placeholder)})
        change.start()
        self.addCleanup(change.stop)
        media_inventory._inspect_file.cache_clear()
        self.addCleanup(media_inventory._inspect_file.cache_clear)

    def test_byte_identical_placeholder_is_rejected_by_both_download_paths(self):
        with self.assertRaisesRegex(CandidateRejected, 'Known provider placeholder'):
            alternatives.validate_image(self.placeholder)
        with patch.object(public, 'fetch_bytes', return_value=self.placeholder):
            with self.assertRaisesRegex(CandidateRejected, 'Known provider placeholder'):
                public.read_image('https://archive.org/services/img/public-fixture')

    def test_same_dimensions_and_same_size_do_not_classify_a_different_image(self):
        # Changing a PNG's trailing bytes changes its hash without changing
        # its pixels/dimensions. Similar-looking genuine covers are not banned.
        modified = self.placeholder + b'public-trailing-byte'
        with patch.object(quality, 'KNOWN_PLACEHOLDERS', {self.digest: len(modified)}):
            self.assertIsNone(quality.placeholder_digest(modified))
            self.assertEqual(alternatives.validate_image(modified), 'png')

    def test_placeholder_inventory_and_lookup_reference_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'original.png'
            path.write_bytes(self.placeholder)
            field = SimpleNamespace(path=path, name='covers/original.png')
            self.assertEqual(media_inventory.image_state(root, 'original.png'), 'known_placeholder')
            self.assertEqual(quality.placeholder_reference(field),
                             {'path': field.name, 'sha256': self.digest, 'size': len(self.placeholder)})
            self.assertTrue(quality.needs_cover(SimpleNamespace(default_edition=SimpleNamespace(cover=field))))
            path.write_bytes(self.placeholder + b'not-the-known-file')
            self.assertEqual(media_inventory.image_state(root, 'original.png'), 'ready')
            self.assertFalse(quality.needs_cover(SimpleNamespace(default_edition=SimpleNamespace(cover=field))))

    def test_symlink_or_unreadable_existing_cover_never_authorizes_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'image.png').write_bytes(self.placeholder)
            (root / 'symlink.png').symlink_to(root / 'image.png')
            self.assertIsNone(quality.placeholder_file(root / 'symlink.png'))
            self.assertIsNone(quality.placeholder_file(root / 'absent.png'))

    def test_exact_repair_policy_reopens_success_once_preserving_history_and_later_wait(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(enrichment_queue, 'STATE', Path(directory)):
            ledger = Path(directory) / 'outcomes.jsonl'
            queue = enrichment_queue.Queue('covers', ledger)
            self.addCleanup(queue.close)
            original = {'id': 1, 'title': 'Public Book', 'authors': ['Public Writer']}
            repairing = {**original, 'placeholder_replacement': {'path': 'covers/logo.png', 'sha256': self.digest}}
            with ledger.open('a') as audit:
                self.assertTrue(queue.due(original, 'same-source'))
                queue.finish(original, {'status': 'covered'}, audit)
                self.assertFalse(queue.due(original, 'same-source'))
                policy = quality.lookup_policy('same-source', repairing)
                self.assertTrue(queue.due(repairing, policy))
                retry = time.time() + 3600
                queue.finish(repairing, {'status': 'provider_deferred', 'provider_outage': True,
                                        'retry_after': retry}, audit)
                self.assertFalse(queue.due(repairing, policy))
            self.assertEqual(len(ledger.read_text().splitlines()), 2)
            self.assertEqual(queue.db.execute('SELECT state,next_retry FROM attempts').fetchone(), ('provider_wait', retry))

    def test_alternative_candidates_continue_after_exact_placeholder_rejection(self):
        genuine = self.placeholder + b'genuine-different-file'
        candidates = [{'image_url': 'https://example.org/' + name, 'source': 'https://example.org/record',
                       'credit': 'Credited source'} for name in ('logo.png', 'cover.png')]
        diagnostics = {}
        with patch.object(alternatives, 'fetch', side_effect=[self.placeholder, genuine]):
            result = alternatives.download_candidates(candidates, diagnostics=diagnostics)
        self.assertEqual(result['image_url'], 'https://example.org/cover.png')
        self.assertIn('Known provider placeholder', diagnostics['candidate_rejections'][0])

    def test_repair_migration_preserves_existing_deadline_and_reopens_legacy_success_once(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(enrichment_queue, 'STATE', Path(directory)):
            ledger = Path(directory) / 'outcomes.jsonl'
            queue = enrichment_queue.Queue('covers', ledger)
            self.addCleanup(queue.close)
            item = {'id': 1, 'title': 'Public Book', 'authors': ['Public Writer'],
                    'placeholder_replacement': {'path': 'covers/logo.png', 'sha256': self.digest}}
            with ledger.open('a') as audit:
                queue.due(item, 'old-policy')
                deadline = time.time() + 3600
                queue.finish(item, {'status': 'provider_deferred', 'provider_outage': True,
                                    'retry_after': deadline}, audit)
                before = queue.db.execute('SELECT * FROM attempts').fetchone()
                self.assertFalse(quality.lookup_due(queue, item, 'old-policy'))
                self.assertEqual(queue.db.execute('SELECT * FROM attempts').fetchone(), before)
                self.assertEqual(queue.summary()['next_retry'], deadline)
                with patch.object(quality.time, 'time', return_value=deadline + 1):
                    self.assertTrue(quality.lookup_due(queue, item, 'old-policy'))
                queue.finish(item, {'status': 'no_safe_match'}, audit)
                self.assertFalse(quality.lookup_due(queue, item, 'old-policy'))
                # Simulate an older success imported without input fingerprints.
                queue.db.execute("UPDATE attempts SET fingerprint=NULL,state='complete'")
                queue.db.commit()
                self.assertTrue(quality.lookup_due(queue, item, 'old-policy'))
                queue.finish(item, {'status': 'no_safe_match'}, audit)
                self.assertFalse(quality.lookup_due(queue, item, 'old-policy'))
