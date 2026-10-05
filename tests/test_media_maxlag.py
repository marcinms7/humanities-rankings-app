"""Offline MediaWiki maxlag transport, persistence and recovery regressions."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from research import media_transport as transport
from research.media_provider_health import eligible, outcome


class MediaMaxlagTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.opener = MagicMock()
        self.response = MagicMock()
        self.response.__enter__.return_value = self.response
        self.response.geturl.return_value = 'https://www.wikidata.org/w/api.php'
        self.response.status = 200
        self.response.headers = {}
        self.response.read.return_value = b'{"error":{"code":"maxlag","info":"token=secret"}}'
        self.opener.open.return_value = self.response
        self.now = 1000
        for change in (patch.object(transport, 'STATE', self.root),
                       patch.object(transport, 'build_opener', return_value=self.opener),
                       patch.object(transport.time, 'time', side_effect=lambda: self.now),
                       patch.object(transport.time, 'sleep')):
            change.start()
            self.addCleanup(change.stop)

    def request(self):
        return transport.fetch_json('https://www.wikidata.org/w/api.php', allowed_hosts={'www.wikidata.org'})

    def test_http200_retry_after_survives_host_state_and_provider_health(self):
        self.response.headers = {'Retry-After': '37'}
        with self.assertRaises(transport.ProviderOutage) as first:
            self.request()
        error = first.exception
        self.assertEqual(error.retry_after, 1037)
        self.assertEqual(error.state_fields(), {'reason': 'Provider returned an API error: maxlag',
                                              'outage_type': 'maxlag', 'http_status': 200})
        self.assertFalse((self.root / 'responses').exists())
        host = json.loads(next((self.root / 'hosts').glob('*.json')).read_text())
        self.assertEqual((host['status'], host['outage_type'], host['until']), (200, 'maxlag', 1037))
        self.assertNotIn('secret', json.dumps(host))
        with self.assertRaises(transport.ProviderOutage) as second:
            self.request()
        self.assertEqual(second.exception.state_fields(), error.state_fields())
        self.assertEqual(self.opener.open.call_count, 1)
        health = outcome({}, {'provider_outage': True, 'retry_after': error.retry_after,
                              **error.state_fields()}, now=self.now)
        self.assertEqual(health['retry_at'], 1037)
        self.assertFalse(eligible(health, 1036))
        self.assertTrue(eligible(health, 1037))

    def test_maxlag_defaults_and_bad_headers_wait_at_least_five_seconds(self):
        for header in (None, '', 'invalid', 'NaN', 'Infinity', '-10', '0', '1'):
            with self.subTest(header=header), self.assertRaises(transport.ProviderOutage) as raised:
                transport._decode_json(self.response.read.return_value, retry_after=header, status=200)
            self.assertEqual(raised.exception.retry_after, 1005)
        with self.assertRaises(transport.ProviderOutage) as raised:
            transport._decode_json(self.response.read.return_value,
                                   retry_after='Thu, 01 Jan 1970 01:00:00 GMT', status=200)
        self.assertEqual(raised.exception.retry_after, 3600)

    def test_maxlag_recovery_backoff_caps_but_never_shortens_server_wait(self):
        health = {'consecutive_failures': 6, 'outage_type': 'unavailable'}
        for delay in (5, 10, 20, 40, 80, 160, 300, 300):
            health = outcome(health, {'provider_outage': True, 'outage_type': 'maxlag',
                'http_status': 200, 'retry_after': self.now + 5}, now=self.now)
            self.assertEqual(health['retry_at'], self.now + delay)
            self.now = health['retry_at']
        health = outcome(health, {'provider_outage': True, 'outage_type': 'maxlag',
            'http_status': 200, 'retry_after': self.now + 4000}, now=self.now)
        self.assertEqual(health['retry_at'], self.now + 4000)

    def test_http403_429_and_legacy_unknown_outages_keep_long_backoff(self):
        for status in (403, 429):
            with self.subTest(status=status):
                host = 'https://example.org/' + str(status)
                self.opener.open.side_effect = HTTPError(host, status, 'Restricted', {'Retry-After': '5'}, io.BytesIO())
                with self.assertRaises(transport.ProviderOutage) as raised:
                    transport.fetch_json(host)
                self.assertEqual(raised.exception.retry_after, self.now + 900)
                self.assertEqual(raised.exception.outage_type, 'unavailable')
                health = outcome({'outage_type': 'maxlag', 'consecutive_failures': 8}, {
                    'provider_outage': True, 'outage_type': 'maxlag', 'http_status': status}, now=self.now)
                self.assertEqual(health['retry_at'], self.now + 900)
                self.now += 1000
        legacy = outcome({}, {'provider_outage': True, 'retry_after': self.now + 5}, now=self.now)
        self.assertEqual(legacy['retry_at'], self.now + 900)

    def test_legacy_cached_api_error_obeys_cooldown_then_recovers_from_network(self):
        self.response.read.return_value = b'{"entities": {}}'
        self.request()
        cached = next(path for path in (self.root / 'responses').rglob('*') if path.is_file() and path.suffix != '.json')
        cached.write_bytes(b'{"error":{"code":"maxlag"}}')
        transport._cooldown('www.wikidata.org', 1005, 200, outage_type='maxlag',
                            reason='Provider returned an API error: maxlag')
        with self.assertRaises(transport.ProviderOutage):
            self.request()
        self.assertEqual(self.opener.open.call_count, 1)
        self.now = 1005
        self.assertEqual(self.request(), {'entities': {}})
        self.assertEqual(self.opener.open.call_count, 2)
        self.assertEqual(json.loads(cached.read_bytes()), {'entities': {}})

    def test_short_lag_cooldown_cannot_replace_existing_long_http_restriction(self):
        transport._cooldown('www.wikidata.org', 1900, 429)
        transport._cooldown('www.wikidata.org', 1005, 200, outage_type='maxlag')
        with self.assertRaises(transport.ProviderOutage) as raised:
            self.request()
        self.assertEqual(raised.exception.retry_after, 1900)
        self.assertEqual(raised.exception.status, 429)
        self.assertEqual(raised.exception.outage_type, 'unavailable')
        self.opener.open.assert_not_called()
