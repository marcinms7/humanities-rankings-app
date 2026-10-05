"""Partial JSON remains usable without poisoning durable response caches."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

from research import media_transport as transport


class MediaPartialCacheTests(unittest.TestCase):
    URL = 'https://en.wikipedia.org/w/api.php?titles=Example'
    COMPLETE = {'query': {'pages': [{'pageid': 1, 'extract': 'Complete article'}]}}
    PARTIAL = {'query': {'pages': [{'pageid': 1, 'extract': 'Usable partial article'}]},
               'warnings': {'extracts': {'warning': 'Not all extracts were returned'}}}

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.now = 1000
        self.opener = MagicMock()
        self.response = MagicMock()
        self.response.__enter__.return_value = self.response
        self.response.geturl.return_value = self.URL
        self.response.status = 200
        self.response.headers = {}
        self.opener.open.return_value = self.response
        self.complete = Mock(side_effect=lambda data: 'warnings' not in data)
        for change in (patch.object(transport, 'STATE', self.root),
                       patch.object(transport, 'build_opener', return_value=self.opener),
                       patch.object(transport.time, 'time', side_effect=lambda: self.now),
                       patch.object(transport.time, 'sleep')):
            change.start()
            self.addCleanup(change.stop)

    def respond(self, payload):
        self.response.read.return_value = json.dumps(payload).encode()

    def request(self, **kwargs):
        return transport.fetch_json(self.URL, allowed_hosts={'en.wikipedia.org'},
                                    json_cacheable=self.complete, **kwargs)

    def cached_body(self):
        return next(path for path in (self.root / 'responses').rglob('*')
                    if path.is_file() and path.suffix != '.json')

    def seed_legacy_partial(self):
        self.respond(self.PARTIAL)
        transport.fetch_json(self.URL, allowed_hosts={'en.wikipedia.org'})
        return self.cached_body()

    def test_partial_fresh_payload_is_returned_without_cache_or_cooldown(self):
        self.respond(self.PARTIAL)
        self.assertEqual(self.request(), self.PARTIAL)
        self.complete.assert_called_once_with(self.PARTIAL)
        self.assertFalse((self.root / 'responses').exists())
        host = json.loads(next((self.root / 'hosts').glob('*.json')).read_text())
        self.assertNotIn('until', host)

    def test_complete_response_is_cached_and_predicate_rechecks_cache_hits(self):
        self.respond(self.COMPLETE)
        self.assertEqual(self.request(), self.COMPLETE)
        self.opener.open.side_effect = AssertionError('Expected complete cached response')
        self.assertEqual(self.request(), self.COMPLETE)
        self.assertEqual(self.opener.open.call_count, 1)
        self.assertEqual(self.complete.call_count, 2)
        self.assertEqual(json.loads(self.cached_body().read_bytes()), self.COMPLETE)

    def test_legacy_partial_is_retained_until_complete_network_replacement(self):
        cached = self.seed_legacy_partial()
        old = {path: path.read_bytes() for path in (cached, cached.with_suffix('.json'))}
        changed_partial = {**self.PARTIAL, 'query': {'pages': [{'pageid': 2, 'extract': 'Second partial'}]}}
        self.respond(changed_partial)
        self.assertEqual(self.request(), changed_partial)
        self.assertEqual(self.opener.open.call_count, 2)
        self.assertEqual({path: path.read_bytes() for path in old}, old)
        transport.time.sleep.assert_called_once_with(1.25)
        self.now += 2
        self.respond(self.COMPLETE)
        self.assertEqual(self.request(), self.COMPLETE)
        self.assertEqual(self.opener.open.call_count, 3)
        self.assertEqual(json.loads(cached.read_bytes()), self.COMPLETE)

    def test_partial_cache_cannot_bypass_host_cooldown(self):
        cached = self.seed_legacy_partial()
        previous = cached.read_bytes()
        transport._cooldown('en.wikipedia.org', 1900, 429)
        self.respond(self.COMPLETE)
        with self.assertRaises(transport.ProviderOutage) as caught:
            self.request()
        self.assertEqual(caught.exception.status, 429)
        self.assertEqual(caught.exception.retry_after, 1900)
        self.assertEqual(self.opener.open.call_count, 1)
        self.assertEqual(cached.read_bytes(), previous)
        self.now = 1900
        self.assertEqual(self.request(), self.COMPLETE)
        self.assertEqual(self.opener.open.call_count, 2)

    def test_api_error_never_reaches_accepting_predicate_or_cache(self):
        self.respond({'error': {'code': 'maxlag'}})
        self.complete.side_effect = lambda data: True
        with self.assertRaises(transport.ProviderOutage):
            self.request()
        self.complete.assert_not_called()
        self.assertFalse((self.root / 'responses').exists())

    def test_invalid_json_never_reaches_predicate_or_cache(self):
        self.response.read.return_value = b'<html>Unavailable</html>'
        with self.assertRaises(transport.ProviderOutage):
            self.request()
        self.complete.assert_not_called()
        self.assertFalse((self.root / 'responses').exists())

    def test_invalid_hook_rejected_before_any_request_or_cache_write(self):
        with self.assertRaises(ValueError):
            transport.fetch_bytes(self.URL, json_cacheable=self.complete)
        with self.assertRaises(ValueError):
            transport.fetch_json(self.URL, json_cacheable=True)
        self.opener.open.assert_not_called()
        self.assertFalse((self.root / 'responses').exists())

    def test_disabled_cache_still_returns_partial_payload(self):
        self.respond(self.PARTIAL)
        self.assertEqual(self.request(cache_ttl=0), self.PARTIAL)
        self.complete.assert_called_once_with(self.PARTIAL)
        self.assertFalse((self.root / 'responses').exists())
