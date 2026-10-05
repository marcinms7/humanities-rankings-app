"""Persisted recovery schedule, distinct from candidate matching attempts."""
import math
import time


def timestamp(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value > 0 else 0


def outcome(previous, stats, cooldown=0, now=None):
    now = time.time() if now is None else now
    status = stats.get('provider_status')
    if status in {'credential_required', 'configuration_required', 'access_denied'}:
        return {'status': 'credential_required', 'reason': stats.get('reason', status), 'updated_at': now}
    until = max(timestamp(cooldown), timestamp(stats.get('retry_after')))
    processed, errors = stats.get('processed', 0), stats.get('provider_errors', 0)
    added = stats.get('covered', stats.get('portraits', 0))
    if stats.get('provider_outage') or until > now or (processed and errors >= processed):
        http_status = stats.get('http_status')
        http_status = http_status if type(http_status) is int and 100 <= http_status <= 599 else None
        outage_type = ('maxlag' if stats.get('outage_type') == 'maxlag' and http_status in {None, 200}
                       else 'transient' if stats.get('outage_type') == 'transient' and http_status in {None, 408, 500, 502, 503, 504}
                       else 'unavailable')
        changed = previous.get('outage_type', 'unavailable') != outage_type
        failures = 1 if added or changed else int(previous.get('consecutive_failures', 0)) + 1
        # One sparse recovery batch remains eligible after expiry; never burn
        # thousands of records or permanently disable a recovered provider.
        delay = (min(300, 5 * 2 ** min(failures - 1, 6)) if outage_type == 'maxlag'
                 else min(900, 60 * 2 ** min(failures - 1, 4)) if outage_type == 'transient'
                 else min(6 * 3600, 900 * 2 ** min(failures - 1, 5)))
        return {'status': 'cooldown', 'consecutive_failures': failures,
                'retry_at': max(until, now + delay), 'updated_at': now,
                'outage_type': outage_type, 'http_status': http_status,
                'reason': stats.get('reason', 'Provider unavailable; a recovery probe is scheduled.')}
    if not processed:
        retry = timestamp(stats.get('next_retry'))
        if retry > now:
            return {'status': 'waiting', 'retry_at': retry, 'updated_at': now, 'consecutive_failures': 0}
        return {'status': 'exhausted', 'updated_at': now, 'consecutive_failures': 0}
    return {'status': 'ready', 'updated_at': now, 'consecutive_failures': 0}


def eligible(record, now=None):
    now = time.time() if now is None else now
    return record.get('status') not in {'credential_required', 'worker_failed', 'exhausted'} and timestamp(record.get('retry_at')) <= now
