"""Sample persistently empty sources without changing their provider health.

Only completed clean batches count. No historical durations are inferred, and
the next sample never takes precedence over a provider's real cooldown.
"""
import math
import time

from research.media_provider_health import timestamp

EMPTY_LOOKUPS = 100
MIN_EMPTY_SECONDS = 60
SAMPLE_INTERVAL = 300


def _number(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else 0


def normalize(record):
    record = record if isinstance(record, dict) else {}
    return {'empty_records': int(_number(record.get('empty_records'))),
            'empty_seconds': _number(record.get('empty_seconds')),
            'sample_after': timestamp(record.get('sample_after'))}


def observe(previous, stats, elapsed, now=None):
    """Update measurements; success immediately restores normal rotation."""
    now = time.time() if now is None else now
    result = normalize(previous)
    added = _number(stats.get('covered', stats.get('portraits', 0)))
    if added:
        return normalize({})
    processed = int(_number(stats.get('processed')))
    if (not processed or stats.get('provider_outage') or _number(stats.get('provider_errors'))
            or _number(stats.get('image_deferred'))
            or stats.get('provider_status')):
        return result
    result['empty_records'] += processed
    result['empty_seconds'] += _number(elapsed)
    result['sample_after'] = (now + SAMPLE_INTERVAL
        if result['empty_records'] >= EMPTY_LOOKUPS and result['empty_seconds'] >= MIN_EMPTY_SECONDS else 0)
    return result


def due_at(health, scheduling, cooldown=0):
    """Every independent wait must have expired before another batch starts."""
    return max(timestamp(health.get('retry_at')), normalize(scheduling)['sample_after'], timestamp(cooldown))
