"""Offline transport regressions: no provider requests or catalog writes."""
import io
import json
from pathlib import Path
import socket
import tempfile
import unittest
from email.message import Message
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.request import Request

from research import media_transport as transport


class MediaTransportTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        for target, replacement in (("STATE", self.root),):
            change = patch.object(transport, target, replacement)
            change.start()
            self.addCleanup(change.stop)
        self.opener = MagicMock()
        self.opener.open.side_effect = AssertionError('Unexpected HTTP request in offline test')
        change = patch.object(transport, 'build_opener', return_value=self.opener)
        change.start()
        self.addCleanup(change.stop)
        change = patch.object(transport.time, 'sleep')
        change.start()
        self.addCleanup(change.stop)

    def response(self, blob, final='https://example.org/data'):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = blob
        response.geturl.return_value = final
        self.opener.open.side_effect = None
        self.opener.open.return_value = response
        return response

    def test_rejects_private_addresses_and_exact_host_escape(self):
        for url in ('file:///tmp/image', 'http://localhost/x', 'http://127.0.0.1/x',
                    'http://[::1]/x', 'http://169.254.169.254/x', 'https://example.org:8443/x',
                    'https://name:secret@example.org/x'):
            with self.subTest(url=url), self.assertRaises(transport.CandidateRejected):
                transport.fetch_bytes(url)
        with self.assertRaises(transport.CandidateRejected):
            transport.fetch_bytes('https://sub.example.org/x', allowed_hosts={'example.org'})
        with self.assertRaises(transport.CandidateRejected):
            transport.fetch_bytes('https://example.org/x', allowed_hosts=set())
        self.opener.open.assert_not_called()

    def test_dns_private_resolution_is_rejected_before_socket_creation(self):
        resolved = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))]
        with patch.object(transport.socket, 'getaddrinfo', return_value=resolved), patch.object(transport.socket, 'socket') as create:
            with self.assertRaises(transport.CandidateRejected):
                transport._public_socket('example.org', 443, 2)
        create.assert_not_called()

    def test_openlibrary_archive_redirects_allow_only_numbered_storage_hosts(self):
        redirect = transport._Redirects(transport.OPENLIBRARY_IMAGE_HOSTS, 'covers.openlibrary.org', False)
        request = Request('https://covers.openlibrary.org/a/id/7063387-L.jpg?default=false')
        archive = 'https://archive.org/download/olcovers706/olcovers706-L.zip/7063387-L.jpg'
        storage = 'https://ia801508.us.archive.org/view_archive.php?file=7063387-L.jpg'
        with patch.object(transport, '_throttle'):
            self.assertEqual(redirect.redirect_request(request, None, 302, 'Found', {}, archive).full_url, archive)
            self.assertEqual(redirect.redirect_request(Request(archive), None, 302, 'Found', {}, storage).full_url, storage)
        for host in ('archive.org.evil.test', 'ia801508.us.archive.org.evil.test',
                     'arbitrary.us.archive.org', 'localhost', '127.0.0.1'):
            with self.subTest(host=host), self.assertRaises(transport.CandidateRejected):
                transport.validate_external_url('https://' + host + '/image', transport.OPENLIBRARY_IMAGE_HOSTS)
        with self.assertRaises(transport.CandidateRejected):
            transport.validate_external_url(storage, {'covers.openlibrary.org'})

    def test_dns_checked_address_is_the_address_actually_connected(self):
        resolved = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.215.14', 443))]
        connection = MagicMock()
        with patch.object(transport.socket, 'getaddrinfo', return_value=resolved) as resolve, patch.object(transport.socket, 'socket', return_value=connection):
            self.assertIs(transport._public_socket('example.org', 443, 2), connection)
        resolve.assert_called_once()
        connection.connect.assert_called_once_with(('93.184.215.14', 443))

    def test_unsafe_redirect_and_cross_origin_key_never_follow(self):
        redirect = transport._Redirects({'example.org', 'other.org'}, 'example.org', False)
        for source, destination in (('https://example.org/x', 'https://sub.example.org/x'),
                                    ('https://example.org/x', 'http://127.0.0.1/x'),
                                    ('https://example.org/x?key=secret', 'https://other.org/x')):
            with self.subTest(destination=destination), self.assertRaises(transport.CandidateRejected):
                redirect.redirect_request(Request(source), None, 302, 'Found', {}, destination)

    def test_success_cache_survives_new_fetch_without_network(self):
        self.response(b'{"value": 42}')
        self.assertEqual(transport.fetch_json('https://example.org/data'), {'value': 42})
        self.opener.open.side_effect = AssertionError('Cache miss')
        self.assertEqual(transport.fetch_json('https://example.org/data'), {'value': 42})
        self.assertEqual(self.opener.open.call_count, 1)

    def test_publisher_unicode_paths_are_encoded_without_changing_url_semantics(self):
        url = 'https://example.org/kitap_detay_sayfaları/a%20b.jpg?name=Łąka&size=200'
        expected = 'https://example.org/kitap_detay_sayfalar%C4%B1/a%20b.jpg?name=%C5%81%C4%85ka&size=200'
        self.response(b'image', final=expected)
        self.assertEqual(transport.fetch_bytes(url, allowed_hosts={'example.org'}), b'image')
        self.assertEqual(self.opener.open.call_args.args[0].full_url, expected)
        self.opener.open.side_effect = AssertionError('Second request should use the safe cached response')
        self.assertEqual(transport.fetch_bytes(url, allowed_hosts={'example.org'}), b'image')

    def test_provider_interval_applies_to_requests_and_redirects(self):
        self.response(b'public')
        with patch.object(transport, '_throttle') as throttle:
            transport.fetch_bytes('https://example.org/data', min_interval=2.1)
            throttle.assert_called_once_with('example.org', 2.1)
            handler = next(arg for arg in transport.build_opener.call_args.args
                           if isinstance(arg, transport._Redirects))
            handler.redirect_request(Request('https://example.org/data'), None, 302, 'Found', {},
                                     'https://example.org/redirected')
            self.assertEqual(throttle.call_args.args, ('example.org', 2.1))
        with patch.object(transport.time, 'time', return_value=1000):
            transport._throttle('new.example.org', 2.1)
        with patch.object(transport.time, 'time', return_value=1001):
            transport._throttle('new.example.org')
            self.assertAlmostEqual(transport.time.sleep.call_args.args[0], 1.1)

    def test_partial_sparql_http200_is_deferred_without_caching(self):
        for index, header in enumerate((('X-SPARQL-MaxRows', '10000'), ('X-SQL-State', 'S1TAT'),
                                       ('X-SQL-Message', 'Returning incomplete results: secret'))):
            response = self.response(b'{"results":{"bindings":[]}}', final=f'https://host{index}.example.org/data')
            response.status = 200
            response.headers = Message()
            response.headers[header[0]] = header[1]
            with self.subTest(header=header[0]), self.assertRaises(transport.ProviderOutage) as caught:
                transport.fetch_json(f'https://host{index}.example.org/data', reject_partial_sparql=True)
            self.assertNotIn('secret', str(caught.exception))
        self.assertFalse((self.root / 'responses').exists())

    def test_complete_sparql_cache_is_distinct_from_legacy_unchecked_cache(self):
        response = self.response(b'{"value":"unchecked"}')
        response.status = 200
        response.headers = Message()
        transport.fetch_json('https://example.org/data')
        response.read.return_value = b'{"value":"verified"}'
        self.assertEqual(transport.fetch_json('https://example.org/data', reject_partial_sparql=True),
                         {'value': 'verified'})
        self.opener.open.side_effect = AssertionError('Complete cache must be reused')
        self.assertEqual(transport.fetch_json('https://example.org/data', reject_partial_sparql=True),
                         {'value': 'verified'})
        self.assertEqual(self.opener.open.call_count, 2)

    def test_cache_cannot_bypass_new_allowlist_policy(self):
        self.response(b'public', final='https://other.org/image')
        transport.fetch_bytes('https://example.org/data')
        self.response(b'allowed', final='https://example.org/data')
        self.assertEqual(transport.fetch_bytes('https://example.org/data', allowed_hosts={'example.org'}), b'allowed')
        self.assertEqual(self.opener.open.call_count, 2)

    def test_robots_checked_even_when_response_is_cached(self):
        self.response(b'public')
        with patch.object(transport, '_check_robots', return_value=0) as robots:
            transport.fetch_bytes('https://example.org/data', respect_robots=True)
            self.assertEqual(robots.call_count, 1)
        with patch.object(transport, '_check_robots', side_effect=transport.CandidateRejected('Disallowed')):
            with self.assertRaises(transport.CandidateRejected):
                transport.fetch_bytes('https://example.org/data', respect_robots=True)
        self.assertEqual(self.opener.open.call_count, 1)

    def test_robots_disallow_and_crawl_delay_are_respected(self):
        content = 'User-agent: *\nDisallow: /private\nCrawl-delay: 4\nRequest-rate: 1/8\n'
        with patch.object(transport, 'fetch_text', return_value=content):
            with self.assertRaises(transport.CandidateRejected):
                transport._check_robots('https://example.org/private/image', {'example.org'})
            self.assertEqual(transport._check_robots('https://example.org/public', {'example.org'}), 8)

    def test_robots_missing_allowed_but_unavailable_deferred(self):
        with patch.object(transport, 'fetch_text', side_effect=transport.CandidateRejected('HTTP 404')):
            self.assertEqual(transport._check_robots('https://example.org/public', {'example.org'}), 0)
        with patch.object(transport, 'fetch_text', side_effect=transport.ProviderOutage('HTTP 503')):
            with self.assertRaises(transport.ProviderOutage):
                transport._check_robots('https://example.org/public', {'example.org'})

    def test_rate_limit_persists_and_does_not_contact_host_again(self):
        self.opener.open.side_effect = HTTPError('https://example.org/data?key=secret', 429, 'Limit', {'Retry-After': '3600'}, io.BytesIO())
        with patch.object(transport.time, 'time', return_value=1000):
            with self.assertRaises(transport.ProviderOutage) as raised:
                transport.fetch_bytes('https://example.org/data')
            self.assertEqual(raised.exception.retry_after, 4600)
            with self.assertRaises(transport.ProviderOutage):
                transport.fetch_bytes('https://example.org/other')
        self.assertEqual(self.opener.open.call_count, 1)
        self.assertNotIn('secret', ''.join(path.read_text() for path in self.root.rglob('*.json')))

    def test_not_found_is_candidate_failure_and_does_not_pause_host(self):
        self.opener.open.side_effect = HTTPError('https://example.org/missing', 404, 'Missing', {}, io.BytesIO())
        with self.assertRaises(transport.CandidateRejected):
            transport.fetch_bytes('https://example.org/missing')
        self.response(b'image')
        self.assertEqual(transport.fetch_bytes('https://example.org/data'), b'image')

    def test_dns_network_failure_is_provider_outage_without_exception_url(self):
        self.opener.open.side_effect = socket.gaierror('secret.example.invalid')
        with self.assertRaises(transport.ProviderOutage) as raised:
            transport.fetch_bytes('https://example.org/data')
        self.assertEqual(str(raised.exception), 'gaierror')

    def test_oversize_response_is_rejected_without_cache(self):
        response = self.response(b'x' * (transport.MAX_BYTES + 1))
        with self.assertRaises(transport.CandidateRejected):
            transport.fetch_bytes('https://example.org/data')
        response.read.assert_called_once_with(transport.MAX_BYTES + 1)
        self.assertFalse((self.root / 'responses').exists())

    def test_invalid_json_is_provider_outage_and_not_cached(self):
        self.response(b'<html>Service unavailable</html>')
        with self.assertRaises(transport.ProviderOutage):
            transport.fetch_json('https://example.org/data')
        self.assertFalse((self.root / 'responses').exists())

    def test_http200_api_error_is_not_cached_or_charged_to_a_candidate(self):
        self.response(b'{"error": {"code": "maxlag"}}')
        with self.assertRaises(transport.ProviderOutage):
            transport.fetch_json('https://example.org/data')
        self.assertFalse((self.root / 'responses').exists())
        with self.assertRaises(transport.ProviderOutage):
            transport.fetch_json('https://example.org/other')
        self.assertEqual(self.opener.open.call_count, 1)

    def test_credentialed_response_cannot_leak_key_into_cache(self):
        self.response(b'{"request": "secret-value"}', final='https://example.org/data?key=secret-value')
        transport.fetch_json('https://example.org/data?key=secret-value')
        self.assertFalse((self.root / 'responses').exists())
        self.assertNotIn('secret-value', ''.join(path.read_text() for path in self.root.rglob('*.json')))

    def test_api_error_exposes_known_code_but_not_private_message(self):
        with self.assertRaisesRegex(transport.ProviderOutage, 'maxlag'):
            transport._decode_json(b'{"error":{"code":"maxlag","info":"key=secret-value"}}')
        with self.assertRaises(transport.ProviderOutage) as raised:
            transport._decode_json(b'{"error":{"code":"secret-value","info":"secret-value"}}')
        self.assertNotIn('secret-value', str(raised.exception))

    def test_candidate_store_strips_nested_credentials_and_tracks_identity(self):
        store = transport.CandidateStore('fixture')
        item = {'id': 1, 'title': 'Book', 'authors': ['Writer'], 'ranked': False, 'priority': 1}
        store.put(item, [{'source': 'https://example.org/item?key=secret', 'image_url': 'https://example.org/image',
                         'metadata': {'url': 'https://example.org/item?token=other', 'api_key': 'key-value'}, 'blob': b'image'}])
        same = store.get({**item, 'priority': 9})
        self.assertEqual(same[0]['source'], 'https://example.org/item')
        self.assertNotIn('api_key', same[0]['metadata'])
        self.assertIsNone(store.get({**item, 'ranked': True}))
        self.assertIsNone(store.get({**item, 'authors': ['Namesake']}))
        content = ''.join(path.read_text() for path in self.root.rglob('*.json'))
        for credential in ('secret', 'other', 'key-value'):
            self.assertNotIn(credential, content)

    def test_retry_after_invalid_values_are_finite(self):
        with patch.object(transport.time, 'time', return_value=1000):
            for value in ('NaN', 'Infinity', 'invalid', None):
                self.assertEqual(transport._retry_after(value), 1900)
            self.assertEqual(transport._retry_after('Thu, 01 Jan 1970 01:00:00 GMT'), 3600)
            self.assertEqual(transport.ProviderOutage(retry_after=float('inf')).retry_after, 1900)
