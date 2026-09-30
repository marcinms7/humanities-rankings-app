"""Bounded process-local request timings, with no SQL text or private payloads."""
from collections import defaultdict, deque
from contextlib import ExitStack
import json
import logging
import os
from threading import Lock
import time
import uuid

from django.conf import settings
from django.db import connections

_samples = deque(maxlen=300)
_logged = deque(maxlen=10)
_lock = Lock()
_started = time.time()
logger = logging.getLogger('marginalia.operations')


def telemetry_summary():
    with _lock:
        samples = list(_samples)
    grouped = defaultdict(list)
    for sample in samples:
        grouped[(sample['method'], sample['route'])].append(sample)
    routes = []
    for (method, route), rows in grouped.items():
        times = sorted(row['duration_ms'] for row in rows)
        routes.append({'method': method, 'route': route, 'requests': len(rows),
            'errors': sum(row['status'] >= 500 for row in rows), 'duration_ms_mean': round(sum(times) / len(times), 2),
            'duration_ms_p95': times[min(len(times) - 1, max(0, (len(times) * 95 + 99) // 100 - 1))],
            'sql_count_mean': round(sum(row['sql_count'] for row in rows) / len(rows), 1),
            'sql_ms_mean': round(sum(row['sql_ms'] for row in rows) / len(rows), 2),
            'response_bytes_mean': round(sum(row['response_bytes'] or 0 for row in rows) / len(rows)),
            'unknown_response_sizes': sum(row['response_bytes'] is None for row in rows)})
    routes.sort(key=lambda row: (-row['duration_ms_p95'], row['route']))
    return {'scope': 'This application process, last 300 API/health requests; resets on restart. Preparation time excludes streaming download transfer.',
            'started_at': _started, 'sample_count': len(samples), 'sample_limit': 300, 'routes': routes[:30],
            'slow_or_failed': sorted((row for row in samples if row['duration_ms'] >= 1000 or row['status'] >= 500),
                                     key=lambda row: row['at'], reverse=True)[:15]}


class OperationalTelemetryMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if os.getenv('MARGINALIA_TELEMETRY', '1') == '0' or not request.path.startswith(('/api/', '/health/')):
            return self.get_response(request)
        identifier, started = uuid.uuid4().hex, time.perf_counter()
        totals = {'count': 0, 'seconds': 0.0}
        def measured(execute, sql, params, many, context):
            began = time.perf_counter()
            try:
                return execute(sql, params, many, context)
            finally:
                totals['count'] += 1
                totals['seconds'] += time.perf_counter() - began
        with ExitStack() as stack:
            for database in connections.all():
                stack.enter_context(database.execute_wrapper(measured))
            response = self.get_response(request)
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        match = getattr(request, 'resolver_match', None)
        route = (getattr(match, 'route', None) or getattr(match, 'view_name', None) or 'unresolved')[:240]
        try:
            size = int(response.get('Content-Length')) if response.get('Content-Length') else None if response.streaming else len(response.content)
        except (TypeError, ValueError, AttributeError):
            size = None
        sample = {'at': time.time(), 'request_id': identifier, 'route': route, 'method': request.method[:12],
                  'status': response.status_code, 'duration_ms': elapsed, 'sql_count': totals['count'],
                  'sql_ms': round(totals['seconds'] * 1000, 2), 'response_bytes': size}
        should_log = False
        with _lock:
            _samples.append(sample)
            if elapsed >= 1000 or response.status_code >= 500:
                now = time.monotonic()
                while _logged and _logged[0] < now - 60:
                    _logged.popleft()
                if len(_logged) < 10:
                    _logged.append(now); should_log = True
        if should_log:
            logger.warning(json.dumps({'event': 'slow_or_failed_request', **sample}, separators=(',', ':')))
        response['X-Request-ID'] = identifier
        if settings.DEBUG or (getattr(request, 'user', None) and request.user.is_authenticated and request.user.is_staff):
            response['Server-Timing'] = f'app;dur={elapsed}, sql;dur={sample["sql_ms"]};desc="{totals["count"]} queries"'
        return response
