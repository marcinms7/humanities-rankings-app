import io
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from research.media_inventory import image_state, unresolved_reason
from research.media_provider_health import outcome, eligible


class MediaHealthInventoryTests(unittest.TestCase):
    def test_repeated_outages_keep_a_sparse_recovery_probe(self):
        previous = {}
        for index in range(6):
            now = 1000 + index * 100000
            previous = outcome(previous, {'processed': 1, 'provider_errors': 1, 'provider_outage': True}, now=now)
            self.assertEqual(previous['status'], 'cooldown')
            self.assertFalse(eligible(previous, now))
            self.assertTrue(eligible(previous, previous['retry_at']))
            self.assertLessEqual(previous['retry_at'] - now, 21600)

    def test_recovery_clears_failure_streak_and_retry_after_is_honoured(self):
        old = {'status': 'cooldown', 'consecutive_failures': 5}
        deferred = outcome(old, {'provider_outage': True, 'retry_after': 999999}, now=1000)
        self.assertEqual(deferred['retry_at'], 999999)
        ready = outcome(old, {'processed': 1, 'covered': 1}, now=1000)
        self.assertEqual(ready['status'], 'ready')
        self.assertEqual(ready['consecutive_failures'], 0)

    def test_missing_credentials_do_not_repeatedly_send_requests(self):
        health = outcome({}, {'provider_status': 'credential_required', 'reason': 'API key is not configured.'}, now=1000)
        self.assertFalse(eligible(health, 999999))
        self.assertEqual(health['reason'], 'API key is not configured.')

    def test_file_coverage_requires_real_decodable_media(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.assertEqual(image_state(root, ''), 'missing_image')
            self.assertEqual(image_state(root, 'lost.jpg'), 'missing_file')
            (root / 'bad.jpg').write_text('<html>Not an image</html>')
            self.assertEqual(image_state(root, 'bad.jpg'), 'invalid_file')
            self.assertEqual(image_state(root, '../outside.jpg'), 'invalid_path')
            Image.new('RGB', (100, 150)).save(root / 'ok.jpg')
            self.assertEqual(image_state(root, 'ok.jpg'), 'ready')
            (root / 'ok.jpg').write_text('broken after initial check')
            self.assertEqual(image_state(root, 'ok.jpg'), 'invalid_file')

    def test_unresolved_reasons_distinguish_missing_work_from_provider_failure(self):
        self.assertEqual(unresolved_reason({'google-covers': {'state': 'pending'}},
            {'google-covers': {'status': 'credential_required'}}), 'provider_blocked')
        self.assertEqual(unresolved_reason({'covers': {'state': 'not_attempted'}}, {}), 'not_attempted')
        self.assertEqual(unresolved_reason({'covers': {'state': 'unresolved', 'status': 'openlibrary_ambiguous'}}, {}), 'identity_review')
        self.assertEqual(unresolved_reason({'covers': {'state': 'unresolved', 'status': 'no_safe_match'}}, {}), 'no_safe_match')

    def test_truncated_jpeg_is_not_counted_ready(self):
        stream = io.BytesIO()
        Image.effect_noise((300, 400), 100).convert('RGB').save(stream, format='JPEG')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'truncated.jpg').write_bytes(stream.getvalue()[:-1000])
            self.assertEqual(image_state(root, 'truncated.jpg'), 'invalid_file')

    def test_ready_unattempted_provider_takes_precedence_over_blocked_alternative(self):
        providers = {'google-covers': {'state': 'not_attempted'}, 'covers': {'state': 'not_attempted'}}
        health = {'google-covers': {'status': 'credential_required'}, 'covers': {'status': 'ready'}}
        self.assertEqual(unresolved_reason(providers, health), 'not_attempted')
        providers['covers'] = {'state': 'retryable'}
        self.assertEqual(unresolved_reason(providers, health), 'retry_needed')
        providers['covers'] = {'state': 'unresolved', 'status': 'no_safe_match'}
        self.assertEqual(unresolved_reason(providers, health), 'provider_blocked')

    def test_prior_success_for_currently_missing_image_needs_another_lookup(self):
        self.assertEqual(unresolved_reason({'covers': {'state': 'complete', 'status': 'covered'}}, {}), 'retry_needed')
