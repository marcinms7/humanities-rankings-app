"""Staff-only operational summaries without raw requests, paths or account data."""
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import shutil
import sqlite3
from threading import Lock
import time

from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from .local_backups import read_json
from .telemetry import telemetry_summary

_cache = {'at': 0, 'value': None}
_lock = Lock()


def _epoch(value):
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value) if math.isfinite(value) and value >= 0 else None
        return datetime.fromisoformat(value).timestamp()
    except (TypeError, ValueError, OverflowError):
        return None


def _size(directory):
    total = 0
    if directory.exists():
        for parent, _, files in os.walk(directory):
            for name in files:
                path = Path(parent) / name
                if not path.is_symlink():
                    try:
                        total += path.stat().st_size
                    except OSError:
                        pass
    return total


def storage_summary():
    now = time.time()
    with _lock:
        if _cache['value'] is not None and now - _cache['at'] < 60:
            return _cache['value']
        base = settings.BASE_DIR
        backup_dir = base / 'data/backups'
        markers = sorted(backup_dir.glob('*.complete'), key=lambda path: path.stat().st_mtime, reverse=True)
        latest = markers[0] if markers else None
        metadata = read_json(latest) if latest else {}
        completed = _epoch(metadata.get('created_at')) or (latest.stat().st_mtime if latest else None)
        status = read_json(backup_dir / 'backup-status.json')
        copy = status.get('copy') if isinstance(status.get('copy'), dict) else {}
        usage = shutil.disk_usage(base)
        value = {'sampled_at': now, 'backup': {'latest_name': latest.stem if latest else None,
            'completed_at': completed, 'age_hours': round((now - completed) / 3600, 1) if completed else None,
            'completed_snapshots': len(markers), 'stored_bytes': _size(backup_dir), 'media_bytes': _size(Path(settings.MEDIA_ROOT)),
            'last_attempt_status': status.get('status', 'not_recorded'), 'last_attempt_at': status.get('attempted_at'),
            'copy': {key: copy.get(key) for key in ('configured', 'status', 'finished_at', 'separate_device')},
            'schedule_installed': (Path.home() / 'Library/LaunchAgents/org.marginalia.daily-backup.plist').is_file(),
            'schedule_prepared': (base / 'data/operations/org.marginalia.daily-backup.plist').is_file()},
            'disk': {'total_bytes': usage.total, 'free_bytes': usage.free, 'used_percent': round(usage.used / usage.total * 100, 1)}}
        _cache.update(at=now, value=value)
        return value


def worker_summary():
    base, now = settings.BASE_DIR, time.time()
    workers = []
    for key, relative in [('media_completion', 'research/_runs/media-completion/status.json'),
                          ('catalog_supervisor', 'research/_runs/catalog-enrichment-supervisor/status.json')]:
        path = base / relative
        state = read_json(path)
        heartbeat = _epoch(state.get('heartbeat_at'))
        timestamp = _epoch(state.get('updated_at')) or (path.stat().st_mtime if path.exists() else None)
        status = state.get('status', 'not_started' if not path.exists() else 'unreadable_state')
        pid_alive = None
        if type(state.get('pid')) is int and state['pid'] > 0:
            try:
                os.kill(state['pid'], 0); pid_alive = True
            except ProcessLookupError:
                pid_alive = False
            except (PermissionError, OSError):
                pass
        workers.append({'name': key, 'status': status, 'updated_at': timestamp, 'heartbeat_at': heartbeat,
            'heartbeat_age_seconds': round(now - heartbeat) if heartbeat else None,
            'heartbeat_supported': heartbeat is not None, 'process_present': pid_alive,
            'batches': state.get('batches', 0), 'current_provider': state.get('current_provider'),
            'added_this_run': state.get('added_this_run'), 'missing_covers': state.get('missing_covers'),
            'missing_portraits': state.get('missing_portraits'), 'retry_at': _epoch(state.get('retry_at') or state.get('retry_after'))})
    providers = []
    for name, relative in [('google-covers', 'research/_runs/media-completion/google-covers-cooldown.json'),
                           ('openlibrary-portraits', 'research/_runs/media-completion/openlibrary-portraits-cooldown.json'),
                           ('wikipedia-covers', 'research/_runs/media-completion/wikipedia-covers-cooldown.json'),
                           ('portraits', 'research/_runs/2026-09-28/portraits/provider-cooldown.json')]:
        state = read_json(base / relative)
        until = _epoch(state.get('until'))
        providers.append({'name': name, 'cooldown_until': until, 'cooldown_active': bool(until and until > now),
                          'state_unreadable': (base / relative).exists() and not bool(state)})
    queues = []
    for name in ['pages', 'covers', 'portraits', 'google-covers', 'openlibrary-portraits', 'wikipedia-covers']:
        path = base / 'data/enrichment' / f'{name}.sqlite3'
        if path.is_file():
            try:
                with sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro', uri=True, timeout=1) as db:
                    states = dict(db.execute('SELECT state,COUNT(*) FROM attempts GROUP BY state'))
                queues.append({'name': name, 'states': states})
            except sqlite3.Error:
                queues.append({'name': name, 'states': {}, 'unavailable': True})
    return {'workers': workers, 'providers': providers, 'queues': queues}


@api_view(['GET'])
@permission_classes([IsAdminUser])
def operations_status(request):
    response = Response({'checked_at': datetime.now(timezone.utc).isoformat(), **storage_summary(),
                         **worker_summary(), 'requests': telemetry_summary()})
    response['Cache-Control'] = 'private, no-store'
    return response
