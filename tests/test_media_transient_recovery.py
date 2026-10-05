from email.message import Message
import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from research import media_transport as transport
from research.media_provider_health import outcome


class TransientRecoveryTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        change = patch.object(transport, 'STATE', Path(folder.name))
        change.start()
        self.addCleanup(change.stop)

    def test_server_recovery_backs_off_without_shortening_retry_after(self):
        now = [1000.0]
        opener = MagicMock()
        headers = Message()
        opener.open.side_effect = HTTPError('https://example.org/image', 502, 'Bad Gateway', headers, None)
        with patch.object(transport.time, 'time', side_effect=lambda: now[0]), \
                patch.object(transport, 'build_opener', return_value=opener):
            for delay in (60, 120, 240, 480, 900):
                with self.assertRaises(transport.ProviderOutage) as caught:
                    transport.fetch_bytes('https://example.org/image')
                self.assertEqual(caught.exception.retry_after, now[0] + delay)
                self.assertEqual(caught.exception.outage_type, 'transient')
                with self.assertRaises(transport.ProviderOutage):
                    transport._throttle('example.org')
                now[0] += delay
            headers['Retry-After'] = '1800'
            with self.assertRaises(transport.ProviderOutage) as caught:
                transport.fetch_bytes('https://example.org/image')
            self.assertEqual(caught.exception.retry_after, now[0] + 1800)

    def test_recovery_resets_only_transient_failure_streak(self):
        with patch.object(transport.time, 'time', return_value=1000):
            transport._cooldown('example.org', 1060, 502, outage_type='transient')
            transport._record_success('example.org')
            self.assertEqual(transport._transient_retry_after('example.org'), 1120)
        with patch.object(transport.time, 'time', return_value=1061):
            transport._record_success('example.org')
            self.assertEqual(transport._transient_retry_after('example.org'), 1121)

    def test_rate_limit_and_access_restrictions_keep_longer_waits(self):
        with patch.object(transport.time, 'time', return_value=1000):
            transport._cooldown('example.org', 1900, 429)
            transport._cooldown('example.org', 1060, 502, outage_type='transient')
            with self.assertRaises(transport.ProviderOutage) as caught:
                transport._throttle('example.org')
            self.assertEqual((caught.exception.status, caught.exception.retry_after), (429, 1900))
        for status in (403, 429):
            self.assertEqual(outcome({}, {'provider_outage': True, 'outage_type': 'transient',
                             'http_status': status}, now=1000)['retry_at'], 1900)

    def test_provider_schedule_distinguishes_server_fault_from_rate_limit(self):
        previous = {}
        for delay in (60, 120, 240, 480, 900, 900):
            previous = outcome(previous, {'provider_outage': True, 'outage_type': 'transient',
                               'http_status': 503}, now=1000)
            self.assertEqual(previous['retry_at'], 1000 + delay)
        self.assertEqual(outcome(previous, {'provider_outage': True, 'outage_type': 'transient',
                          'http_status': 503, 'retry_after': 9000}, now=1000)['retry_at'], 9000)

    def test_contact_is_explicit_and_cannot_inject_headers_or_credentials(self):
        with patch.dict(os.environ, {'MARGINALIA_MEDIA_CONTACT': ''}):
            self.assertEqual(transport.request_user_agent(), transport.USER_AGENT)
        for contact in ('contact@example.org', 'https://example.org/project'):
            with patch.dict(os.environ, {'MARGINALIA_MEDIA_CONTACT': contact}):
                self.assertIn(contact, transport.request_user_agent())
        for contact in ('test@example.org\r\nAuthorization:secret', 'https://user:secret@example.org/',
                        'https://example.org/?token=secret', 'http://127.0.0.1/'):
            with patch.dict(os.environ, {'MARGINALIA_MEDIA_CONTACT': contact}), self.assertRaises(ValueError):
                transport.request_user_agent()
