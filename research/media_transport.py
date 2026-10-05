"""Bounded public-media HTTP with durable caching and provider-wide backoff.

This module never writes catalog records. Cache files contain public response
bytes and metadata only; credential-bearing URLs and headers are never stored.
"""
from __future__ import annotations

import contextlib
import hashlib
import http.client
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import socket
import tempfile
import time
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPHandler, HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener
from urllib.robotparser import RobotFileParser

from research.operational_state import atomic_state, read_state

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / 'data/enrichment/media-http'
MAX_BYTES = 10 * 1024 * 1024
USER_AGENT = 'Marginalia/1.0 (public catalogue metadata and credited images)'
SECRET_PARAMETERS = {'key', 'api_key', 'apikey', 'access_token', 'token', 'signature', 'sig'}
OPENLIBRARY_IMAGE_HOSTS = ('covers.openlibrary.org', 'archive.org', '@archive-image-storage')


def request_user_agent():
    """Use only an explicitly supplied public operator contact."""
    contact = os.environ.get('MARGINALIA_MEDIA_CONTACT', '').strip()
    if not contact:
        return USER_AGENT
    if len(contact) > 200 or any(ord(char) < 33 or ord(char) > 126 for char in contact):
        raise ValueError('MARGINALIA_MEDIA_CONTACT must be one public email or URL')
    if re.fullmatch(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', contact):
        return f'Marginalia/1.0 ({contact})'
    parts = validate_external_url(contact)
    if parts.query or parts.fragment:
        raise ValueError('Public contact URLs cannot include query strings or fragments')
    return f'Marginalia/1.0 ({contact})'


class CandidateRejected(ValueError):
    """A particular URL/response is unusable; other candidates may succeed."""


class ProviderOutage(RuntimeError):
    """Pause the provider, without using an individual record's retry budget."""
    def __init__(self, reason='Provider temporarily unavailable', *, retry_after=None, status=None,
                 outage_type='unavailable'):
        self.reason = reason
        until = retry_after if type(retry_after) in (float, int) and math.isfinite(retry_after) else time.time() + 900
        self.retry_after = max(time.time() + 1, until)
        self.status = status if type(status) is int and 100 <= status <= 599 else None
        self.outage_type = ('maxlag' if outage_type == 'maxlag' and self.status in {None, 200}
                            else 'transient' if outage_type == 'transient' and self.status in {None, 408, 500, 502, 503, 504}
                            else 'unavailable')
        super().__init__(reason)

    def state_fields(self):
        """Persist known diagnostics, never response text or request headers."""
        return {'reason': self.reason, 'outage_type': self.outage_type, 'http_status': self.status}


def public_url(url):
    """Strip query credentials before persisting provenance/cache keys."""
    parts = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
             if key.casefold() not in SECRET_PARAMETERS]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ''))


def public_text(text):
    """Also remove credential query fields from URLs embedded in credits."""
    return re.sub(r'https?://[^\s<>"\']+', lambda match: public_url(match.group()), str(text))


def public_candidate(value):
    if isinstance(value, dict):
        return {key: public_candidate(child) for key, child in value.items()
                if key.casefold() not in SECRET_PARAMETERS | {'blob', 'image', 'headers', 'authorization', 'cookie'}}
    if isinstance(value, list):
        return [public_candidate(child) for child in value]
    if isinstance(value, str):
        return public_text(value)
    return value


def validate_external_url(url, allowed_hosts=None):
    try:
        parts = urlsplit(url)
        host = (parts.hostname or '').rstrip('.').lower()
        port = parts.port
    except (TypeError, ValueError):
        raise CandidateRejected('Malformed external URL') from None
    if parts.scheme not in {'http', 'https'} or not host or parts.username or parts.password:
        raise CandidateRejected('Only public HTTP(S) URLs without credentials are allowed')
    if port is not None and port != (443 if parts.scheme == 'https' else 80):
        raise CandidateRejected('Nonstandard external port')
    if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
        raise CandidateRejected('Private host is not allowed')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address and not address.is_global:
        raise CandidateRejected('Private address is not allowed')
    if allowed_hosts is not None:
        allowed = {domain.lower().rstrip('.') for domain in allowed_hosts}
        archive_storage = ('@archive-image-storage' in allowed
                           and re.fullmatch(r'ia[0-9]+\.(?:us|eu)\.archive\.org', host))
        if host not in allowed and not archive_storage:
            raise CandidateRejected('External host is outside the provider allowlist')
    return parts


def _public_socket(host, port, timeout):
    """Connect to the checked IP, preventing a second DNS lookup/rebinding."""
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise CandidateRejected('DNS resolved to a non-public address')
    failure = None
    for family, kind, protocol, _, address in addresses:
        connection = socket.socket(family, kind, protocol)
        connection.settimeout(timeout)
        try:
            connection.connect(address)
            return connection
        except OSError as error:
            failure = error
            connection.close()
    raise failure or OSError('No usable public address')


class _PublicHTTPConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = _public_socket(self.host, self.port, self.timeout)


class _PublicHTTPSConnection(http.client.HTTPSConnection):
    def connect(self):
        raw = _public_socket(self.host, self.port, self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except Exception:
            raw.close()
            raise


class _HTTPHandler(HTTPHandler):
    def http_open(self, request):
        return self.do_open(_PublicHTTPConnection, request)


class _HTTPSHandler(HTTPSHandler):
    def https_open(self, request):
        return self.do_open(_PublicHTTPSConnection, request, context=self._context)


class _Redirects(HTTPRedirectHandler):
    def __init__(self, allowed_hosts, original_host, respect_robots, min_interval=0):
        self.allowed_hosts = allowed_hosts
        self.original_host = original_host
        self.respect_robots = respect_robots
        self.min_interval = min_interval

    def redirect_request(self, request, fp, code, message, headers, newurl):
        parts = validate_external_url(newurl, self.allowed_hosts)
        # API credentials must never follow a redirect to another origin.
        original = urlsplit(request.full_url)
        if (parts.scheme, parts.netloc) != (original.scheme, original.netloc):
            if any(key.casefold() in SECRET_PARAMETERS for key, _ in parse_qsl(parts.query)):
                raise CandidateRejected('Credential-bearing cross-origin redirect')
            if any(key.casefold() in SECRET_PARAMETERS for key, _ in parse_qsl(original.query)):
                raise CandidateRejected('Credential-bearing request redirected across origins')
        interval = max(self.min_interval, _check_robots(newurl, self.allowed_hosts) if self.respect_robots else 0)
        redirected = super().redirect_request(request, fp, code, message, headers, newurl)
        if redirected is not None:
            for header in ('Authorization', 'Cookie', 'Proxy-Authorization'):
                redirected.remove_header(header)
        _throttle(parts.hostname, interval)
        return redirected


@contextlib.contextmanager
def _host_lock(host):
    import fcntl
    folder = STATE / 'hosts'
    folder.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(host.encode()).hexdigest()
    with (folder / (digest + '.lock')).open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield folder / (digest + '.json')
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def _throttle(host, min_interval=0):
    with _host_lock(host) as path:
        state = read_state(path)
        until = state.get('until', 0)
        if until > time.time():
            outage_type = state.get('outage_type', 'unavailable')
            reason = 'Provider returned an API error: maxlag' if outage_type == 'maxlag' else 'Provider cooldown is active'
            raise ProviderOutage(reason, retry_after=until, status=state.get('status'), outage_type=outage_type)
        delay = max(0, state.get('requested_at', 0)
                    + max(1.25, min_interval, state.get('min_interval', 0)) - time.time())
        if delay:
            time.sleep(delay)
        atomic_state(path, {**state, 'requested_at': time.time(), 'min_interval': max(1.25, min_interval)})


def _cooldown(host, until, status, *, outage_type='unavailable', reason='Provider cooldown is active'):
    with _host_lock(host) as path:
        state = read_state(path)
        # A brief lag signal must never overwrite a longer existing HTTP
        # restriction, including its diagnostic category.
        if state.get('until', 0) > until:
            return
        failures = int(state.get('transient_failures', 0)) + 1 if outage_type == 'transient' else 0
        atomic_state(path, {**state, 'until': until, 'status': status,
                            'outage_type': outage_type, 'reason': reason, 'transient_failures': failures})


def _transient_retry_after(host, header=None):
    """Short recovery probes for server/network faults, with exponential backoff."""
    with _host_lock(host) as path:
        failures = read_state(path).get('transient_failures', 0)
        failures = failures if type(failures) is int and failures >= 0 else 0
    delay = min(900, 60 * 2 ** min(failures, 4))
    return _retry_after(header, minimum=delay, default=delay)


def _record_success(host):
    with _host_lock(host) as path:
        state = read_state(path)
        # A concurrent restriction must not be cancelled by an earlier success.
        if state.get('transient_failures') and state.get('until', 0) <= time.time():
            atomic_state(path, {**state, 'transient_failures': 0})


def _retry_after(value, *, minimum=900, default=900):
    try:
        delay = float(value)
    except (ValueError, TypeError):
        try:
            delay = parsedate_to_datetime(value).timestamp() - time.time()
        except (ValueError, TypeError, OverflowError):
            delay = default
    return time.time() + max(minimum, delay if math.isfinite(delay) else default)


def _write_bytes(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.', suffix='.partial', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _response_cache_path(url, allowed_hosts, respect_robots, json_response, reject_partial_sparql=False):
    policy = [public_url(url), sorted(allowed_hosts) if allowed_hosts is not None else None,
              respect_robots, json_response]
    if reject_partial_sparql:
        policy.append('complete-sparql-v1')
    digest = hashlib.sha256(json.dumps(policy).encode()).hexdigest()
    return STATE / 'responses' / digest[:2] / digest


def response_cache_timestamp(url, *, allowed_hosts=None, respect_robots=False,
                             json_response=True, reject_partial_sparql=False):
    """Original public-response age for derived caches; never refresh its TTL."""
    path = _response_cache_path(url, allowed_hosts, respect_robots, json_response, reject_partial_sparql)
    try:
        if path.is_file() and path.with_suffix('.json').is_file():
            return path.stat().st_mtime
    except OSError:
        pass
    return None


def fetch_bytes(url, *, provider='', headers=None, allowed_hosts=None, respect_robots=False,
                timeout=25, cache_ttl=86400, min_interval=0, reject_partial_sparql=False,
                _json=False, json_cacheable=None):
    if type(min_interval) not in (int, float) or not math.isfinite(min_interval) or min_interval < 0:
        raise ValueError('min_interval must be a finite nonnegative number')
    if json_cacheable is not None and (not _json or not callable(json_cacheable)):
        raise ValueError('json_cacheable must be callable and requires a JSON request')
    parts = validate_external_url(url, allowed_hosts)
    # Publisher HTML legitimately advertises non-ASCII paths. urllib's HTTP
    # request line is ASCII; encode path/query bytes without double-encoding
    # existing escapes or changing reserved URL separators. Identity and host
    # checks still use the original advertised URL.
    wire_url = urlunsplit((parts.scheme, parts.netloc,
                          quote(parts.path, safe="/%:@!$&'()*+,;=-._~"),
                          quote(parts.query, safe="/?%:@!$&'()*+,;=-._~"), ''))
    interval = max(min_interval, _check_robots(url, allowed_hosts) if respect_robots else 0)
    # The completeness policy keeps old unchecked SPARQL caches separate.
    cached = _response_cache_path(url, allowed_hosts, respect_robots, _json, reject_partial_sparql)
    metadata = cached.with_suffix('.json')
    if (any(key.casefold() in {'authorization', 'cookie', 'proxy-authorization'} for key in (headers or {}))
            or any(key.casefold() in SECRET_PARAMETERS for key, _ in parse_qsl(parts.query))):
        # Providers can echo a request in a response. Do not cache credentialed
        # response bodies; the separate verified candidate store is sufficient.
        cache_ttl = 0
    if cache_ttl and cached.exists() and metadata.exists() and time.time() - cached.stat().st_mtime < cache_ttl:
        if cached.stat().st_size <= MAX_BYTES:
            saved = read_state(metadata)
            if saved.get('final_url'):
                validate_external_url(saved['final_url'], allowed_hosts)
                if respect_robots and saved['final_url'] != public_url(url):
                    _check_robots(saved['final_url'], allowed_hosts)
                blob = cached.read_bytes()
                if _json:
                    try:
                        decoded = _decode_json(blob)
                    except ProviderOutage:
                        # Legacy caches may contain errors. Treat them as a
                        # miss; _throttle below still enforces any saved wait.
                        # Never replay a stale error forever or return it as a
                        # successful response. Only success replaces the file.
                        pass
                    else:
                        # Some APIs return usable per-record data alongside
                        # an incompleteness warning in HTTP200. Recheck old
                        # bodies without deleting them or bypassing host waits.
                        if json_cacheable is None or json_cacheable(decoded):
                            return blob
                else:
                    return blob
    _throttle(parts.hostname, interval)
    request_headers = {'User-Agent': request_user_agent(), 'Accept': '*/*', **(headers or {})}
    opener = build_opener(ProxyHandler({}), _HTTPHandler(), _HTTPSHandler(),
                          _Redirects(allowed_hosts, parts.hostname, respect_robots, min_interval))
    try:
        with opener.open(Request(wire_url, headers=request_headers), timeout=timeout) as response:
            validate_external_url(response.geturl(), allowed_hosts)
            final_url = public_url(response.geturl())
            blob = response.read(MAX_BYTES + 1)
            response_retry_after = response.headers.get('Retry-After')
            response_status = response.status
            if reject_partial_sparql:
                state = str(response.headers.get('X-SQL-State') or '').strip()
                message = str(response.headers.get('X-SQL-Message') or '').casefold()
                if (response.headers.get('X-SPARQL-MaxRows') is not None
                        or state not in {'', '00000'}
                        or any(term in message for term in ('incomplete', 'timeout', 'interrupted'))):
                    # DBpedia can return HTTP200 for truncated/time-limited
                    # results. A partial identity set is not safe evidence.
                    raise ProviderOutage('SPARQL provider returned incomplete results', status=response_status)
        if len(blob) > MAX_BYTES:
            raise CandidateRejected('Response exceeds 10 MB')
        cacheable = True
        if _json:
            decoded = _decode_json(blob, retry_after=response_retry_after, status=response_status)
            if json_cacheable is not None:
                cacheable = bool(json_cacheable(decoded))
    except HTTPError as error:
        host = urlsplit(error.url).hostname or parts.hostname
        if error.code in {401, 403, 408, 429, 500, 502, 503, 504}:
            transient = error.code in {408, 500, 502, 503, 504}
            header = error.headers.get('Retry-After') if error.headers is not None else None
            until = _transient_retry_after(host, header) if transient else _retry_after(header)
            kind = 'transient' if transient else 'unavailable'
            _cooldown(host, until, error.code, outage_type=kind)
            raise ProviderOutage(f'HTTP {error.code}', retry_after=until, status=error.code, outage_type=kind) from None
        raise CandidateRejected(f'HTTP {error.code}') from None
    except ProviderOutage as error:
        _cooldown(parts.hostname, error.retry_after, error.status,
                  outage_type=error.outage_type, reason=error.reason)
        raise
    except (URLError, OSError, http.client.HTTPException) as error:
        until = _transient_retry_after(parts.hostname)
        _cooldown(parts.hostname, until, None, outage_type='transient')
        raise ProviderOutage(type(error).__name__, retry_after=until, outage_type='transient') from None
    _record_success(parts.hostname)
    if urlsplit(final_url).hostname != parts.hostname:
        _record_success(urlsplit(final_url).hostname)
    if cache_ttl and cacheable:
        _write_bytes(cached, blob)
        atomic_state(metadata, {'final_url': final_url})
    return blob


def _decode_json(blob, *, retry_after=None, status=None):
    try:
        value = json.loads(blob)
        if not isinstance(value, (dict, list)):
            raise ValueError('Unexpected scalar')
        if isinstance(value, dict) and 'error' in value:
            error = value['error']
            code = error.get('code') if isinstance(error, dict) else None
            # Log known diagnostic codes, never free-form provider messages
            # that might echo credential-bearing URLs or request parameters.
            known = {'maxlag', 'ratelimited', 'readonly', 'badvalue', 'unknown_action',
                     'permissiondenied', 'no-such-entity', 'toomanyvalues', 'missingparam'}
            suffix = ': ' + code if isinstance(code, str) and code in known else ''
            if code == 'maxlag':
                # MediaWiki returns this temporary load signal with HTTP200.
                # Its documented minimum is five seconds, unlike HTTP429/403.
                # A larger server Retry-After remains authoritative.
                raise ProviderOutage('Provider returned an API error: maxlag',
                    retry_after=_retry_after(retry_after, minimum=5, default=5),
                    status=status if type(status) is int else 200, outage_type='maxlag')
            raise ProviderOutage('Provider returned an API error' + suffix)
        return value
    except (ValueError, UnicodeError):
        raise ProviderOutage('Provider returned invalid JSON') from None


def fetch_json(url, **kwargs):
    return _decode_json(fetch_bytes(url, _json=True, **kwargs))


def fetch_text(url, **kwargs):
    return fetch_bytes(url, **kwargs).decode('utf-8', errors='replace')


def _check_robots(url, allowed_hosts):
    parts = validate_external_url(url, allowed_hosts)
    robots_url = urlunsplit((parts.scheme, parts.netloc, '/robots.txt', '', ''))
    try:
        content = fetch_text(robots_url, allowed_hosts=allowed_hosts, cache_ttl=86400)
    except CandidateRejected as error:
        if str(error) == 'HTTP 404':
            return 0
        raise CandidateRejected('Publisher robots policy could not be verified') from None
    parser = RobotFileParser(robots_url)
    parser.parse(content.splitlines())
    if not parser.can_fetch('Marginalia', url):
        raise CandidateRejected('Publisher robots policy disallows this URL')
    delay = parser.crawl_delay('Marginalia') or 0
    rate = parser.request_rate('Marginalia')
    return max(delay, rate.seconds / rate.requests if rate and rate.requests else 0)


class CandidateStore:
    """Public verified candidates are durable across download failures/restarts."""
    def __init__(self, provider, *, version='1', ttl=30 * 86400):
        self.provider = provider
        self.version = version
        self.ttl = ttl

    def _path(self, item):
        identity = {key: value for key, value in item.items()
                    if not key.startswith('_') and key not in {'priority', 'shared_priority'}}
        key = hashlib.sha256(json.dumps([self.provider, self.version, identity], sort_keys=True,
                                       ensure_ascii=False).encode()).hexdigest()
        return STATE / 'candidates' / key[:2] / (key + '.json')

    def get(self, item):
        path = self._path(item)
        if not path.exists() or time.time() - path.stat().st_mtime > self.ttl:
            return None
        value = read_state(path)
        return value.get('candidates') if isinstance(value.get('candidates'), list) else None

    def put(self, item, candidates):
        # Never persist binary downloads or request credentials.
        cleaned = [public_candidate(candidate) for candidate in candidates]
        atomic_state(self._path(item), {'provider': self.provider, 'candidates': cleaned})
        return cleaned
