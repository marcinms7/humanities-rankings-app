"""Drain all media queues, rotate providers during cooldowns, and resume on restart."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.enrichment_queue import exclusive, rotate
from research.operational_state import atomic_state, read_state
RUN = ROOT / 'research/_runs/media-completion'
STATE = ROOT / 'data/enrichment'
STOP = STATE / 'media-completion.stop'
PYTHON = str(ROOT / '.venv/bin/python')
HEARTBEAT = None
JOBS = [
    ('google-covers', ['research/enrich_media_alternatives.py', 'google-covers', '--limit', '20'], RUN / 'google-covers-stats.json', RUN / 'google-covers-cooldown.json'),
    ('openlibrary-portraits', ['research/enrich_media_alternatives.py', 'openlibrary-portraits', '--limit', '20'], RUN / 'openlibrary-portraits-stats.json', RUN / 'openlibrary-portraits-cooldown.json'),
    ('wikipedia-covers', ['research/enrich_media_alternatives.py', 'wikipedia-covers', '--limit', '20'], RUN / 'wikipedia-covers-stats.json', RUN / 'wikipedia-covers-cooldown.json'),
    ('covers', ['research/enrich_catalog_covers_public.py', '--limit', '30', '--workers', '1', '--summary-file', str(RUN / 'covers-stats.json')], RUN / 'covers-stats.json', None),
    ('portraits', ['research/enrich_catalog_portraits.py', '--limit', '40'], ROOT / 'research/_runs/2026-09-28/portraits/latest-stats.json', ROOT / 'research/_runs/2026-09-28/portraits/provider-cooldown.json'),
]


def read(path):
    return read_state(path, cooldown=bool(path and 'cooldown' in Path(path).name))


def remaining_report():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.config.settings')
    import django
    django.setup()
    from backend.core.models import Work, Person
    connections = {}
    for name, *_ in JOBS:
        path = STATE / f'{name}.sqlite3'
        if path.exists():
            connections[name] = sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True)
    def outcomes(names, pk):
        result = {}
        for name in names:
            row = connections[name].execute('SELECT state,result FROM attempts WHERE work_id=?', (pk,)).fetchone() if name in connections else None
            saved = json.loads(row[1]) if row else {}
            result[name] = {'state': row[0] if row else 'not_attempted', 'status': saved.get('status'), 'error': saved.get('error')}
        return result
    missing = []
    for work in Work.objects.filter(is_archived=False).select_related('default_edition').prefetch_related('authors'):
        if not work.default_edition or not work.default_edition.cover:
            missing.append({'kind': 'cover', 'id': work.pk, 'title': work.title, 'authors': [p.name for p in work.authors.all()], 'providers': outcomes(('covers', 'google-covers', 'wikipedia-covers'), work.pk)})
    for person in Person.objects.filter(is_archived=False, portrait=''):
        missing.append({'kind': 'portrait', 'id': person.pk, 'name': person.name, 'providers': outcomes(('portraits', 'openlibrary-portraits'), person.pk)})
    for connection in connections.values():
        connection.close()
    atomic_state(RUN / 'unresolved.json', missing)
    return {'missing_covers': sum(row['kind'] == 'cover' for row in missing), 'missing_portraits': sum(row['kind'] == 'portrait' for row in missing)}


def run_child(args):
    log = RUN / 'worker.log'
    rotate(log)
    with log.open('a') as output:
        process = subprocess.Popen([PYTHON, *args], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        while process.poll() is None:
            if HEARTBEAT:
                HEARTBEAT()
            if STOP.exists():
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                return -signal.SIGTERM
            time.sleep(0.5)
    return process.returncode


def main():
    global HEARTBEAT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--background', action='store_true')
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--stop', action='store_true')
    parser.add_argument('--max-batches', type=int, default=0, help='Optional validation bound; default drains all queues.')
    args = parser.parse_args()
    RUN.mkdir(parents=True, exist_ok=True)
    STATE.mkdir(parents=True, exist_ok=True)
    if args.status:
        print(json.dumps(read(RUN / 'status.json'), indent=2))
        return
    if args.stop:
        STOP.touch()
        print('Stop requested. Saved results are retained; rerun the same command to resume.')
        return
    if args.background:
        with exclusive('media-completion'):
            pass  # Reject an already-running instance before announcing a launch.
        rotate(RUN / 'runner.log')
        with (RUN / 'runner.log').open('a') as output:
            child = subprocess.Popen([PYTHON, str(Path(__file__).resolve()), *(['--max-batches', str(args.max_batches)] if args.max_batches else [])], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        print(f'Runner launched (PID {child.pid}). Use --status or --stop. Log: {RUN / "worker.log"}')
        return
    with exclusive('media-completion'), exclusive('supervisor'):
        STOP.unlink(missing_ok=True)
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: STOP.touch())
        state = {'pid': os.getpid(), 'started_at': time.time(), 'status': 'backing_up', 'batches': 0, 'added_this_run': 0, 'providers': {}}
        def save():
            state['updated_at'] = time.time()
            state['heartbeat_at'] = state['updated_at']
            atomic_state(RUN / 'status.json', state)
        def heartbeat():
            if time.time() - state.get('heartbeat_at', 0) >= 15:
                save()
        HEARTBEAT = heartbeat
        save()
        if run_child(['manage.py', 'backup_local', '--daily']):
            state['status'] = 'backup_failed' if not STOP.exists() else 'stopped'
            save()
            return 1
        state.update(remaining_report())
        # Provider outages are separate from individual no-match results. After
        # three failed probes, retain a blocked provider report instead of sending
        # thousands of records into the same quota failure.
        waiting, exhausted, failed_probes = {}, set(), {}
        while not STOP.exists():
            ran = False
            for name, command, summary, cooldown in JOBS:
                if STOP.exists() or name in exhausted:
                    continue
                until = max(waiting.get(name, 0), read(cooldown).get('until', 0))
                if until > time.time():
                    waiting[name] = until
                    continue
                summary.unlink(missing_ok=True)
                state.update(status='running', current_provider=name)
                save()
                code = run_child(command)
                if STOP.exists():
                    break
                stats = read(summary)
                state['batches'] += 1
                if code or not stats or stats.get('invalid_state'):
                    state['providers'][name] = {'status': 'worker_failed', 'exit_code': code}
                    exhausted.add(name)
                    save()
                    continue
                ran = True
                processed = stats.get('processed', 0)
                added = stats.get('covered', stats.get('portraits', 0))
                state['added_this_run'] += added
                state['providers'][name] = stats
                print(f'{name}: processed {processed}, added {added}; total added this run {state["added_this_run"]}', flush=True)
                until = max(read(cooldown).get('until', 0), stats.get('retry_after', 0) if isinstance(stats.get('retry_after'), (float, int)) else 0)
                errors = stats.get('provider_errors', 0)
                if until > time.time() or (processed and errors >= processed):
                    failed_probes[name] = 0 if added else failed_probes.get(name, 0) + 1
                    waiting[name] = max(until, time.time() + 900)
                    if failed_probes[name] >= 3:
                        exhausted.add(name)
                        state['providers'][name]['blocked'] = 'Repeated provider outage; rerun after service/quota recovers.'
                elif processed == 0:
                    retry = stats.get('next_retry') or 0
                    if retry > time.time():
                        waiting[name] = retry
                    else:
                        exhausted.add(name)
                else:
                    failed_probes[name] = 0
                    waiting.pop(name, None)
                if state['batches'] % 10 == 0:
                    state.update(remaining_report())
                save()
                if args.max_batches and state['batches'] >= args.max_batches:
                    state['status'] = 'batch_limit'
                    state.update(remaining_report())
                    save()
                    return 0
            if len(exhausted) == len(JOBS):
                state.update(remaining_report())
                state['status'] = 'complete' if state['missing_covers'] + state['missing_portraits'] == 0 else 'needs_review'
                state.pop('current_provider', None)
                save()
                print(json.dumps(state, indent=2), flush=True)
                return 0 if state['status'] == 'complete' else 2
            if not ran:
                state.update(status='waiting_for_provider', retry_at=min((value for name, value in waiting.items() if name not in exhausted), default=time.time() + 30))
                save()
                time.sleep(min(30, max(1, state['retry_at'] - time.time())))
        state.update(remaining_report())
        state['status'] = 'stopped'
        save()
        return 0


if __name__ == '__main__':
    sys.exit(main())
