"""Drain all media queues, rotate providers during cooldowns, and resume on restart."""
from __future__ import annotations
import argparse
import json
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.enrichment_queue import exclusive, rotate
from research.operational_state import atomic_state, read_state
from research.media_provider_health import outcome, eligible, timestamp
from research.media_source_scheduling import observe, normalize, due_at
RUN = ROOT / 'research/_runs/media-completion'
STATE = ROOT / 'data/enrichment'
STOP = STATE / 'media-completion.stop'
PYTHON = str(ROOT / '.venv/bin/python')
HEARTBEAT = None
JOBS = [
    ('catalog-covers', ['research/reuse_catalog_covers.py', '--apply', '--limit', '100'], RUN / 'catalog-covers-stats.json', None),
    ('reviewed-covers', ['research/enrich_media_alternatives.py', 'reviewed-covers', '--limit', '60'], RUN / 'reviewed-covers-stats.json', RUN / 'reviewed-covers-cooldown.json'),
    ('wolnelektury-covers', ['research/enrich_media_alternatives.py', 'wolnelektury-covers', '--limit', '30'], RUN / 'wolnelektury-covers-stats.json', RUN / 'wolnelektury-covers-cooldown.json'),
    ('google-covers', ['research/enrich_media_alternatives.py', 'google-covers', '--limit', '20'], RUN / 'google-covers-stats.json', RUN / 'google-covers-cooldown.json'),
    ('openlibrary-portraits', ['research/enrich_media_alternatives.py', 'openlibrary-portraits', '--limit', '60'], RUN / 'openlibrary-portraits-stats.json', RUN / 'openlibrary-portraits-cooldown.json'),
    ('cached-wikidata-portraits', ['research/enrich_media_alternatives.py', 'cached-wikidata-portraits', '--limit', '50'], RUN / 'cached-wikidata-portraits-stats.json', RUN / 'cached-wikidata-portraits-cooldown.json'),
    *[(name, ['research/enrich_media_alternatives.py', name, '--limit', str(limit)],
       RUN / f'{name}-stats.json', RUN / f'{name}-cooldown.json')
      for name, limit in (('dbpedia-portraits', 20), ('gnd-portraits', 10), ('rijksmuseum-portraits', 5))],
    ('linked-wikidata-portraits', ['research/enrich_media_alternatives.py', 'linked-wikidata-portraits', '--limit', '30'], RUN / 'linked-wikidata-portraits-stats.json', RUN / 'linked-wikidata-portraits-cooldown.json'),
    ('wellcome-portraits', ['research/enrich_media_alternatives.py', 'wellcome-portraits', '--limit', '10'], RUN / 'wellcome-portraits-stats.json', RUN / 'wellcome-portraits-cooldown.json'),
    ('nobel-portraits', ['research/enrich_media_alternatives.py', 'nobel-portraits', '--limit', '500'], RUN / 'nobel-portraits-stats.json', RUN / 'nobel-portraits-cooldown.json'),
    ('wikipedia-covers', ['research/enrich_media_alternatives.py', 'wikipedia-covers', '--limit', '20'], RUN / 'wikipedia-covers-stats.json', RUN / 'wikipedia-covers-cooldown.json'),
    ('covers', ['research/enrich_catalog_covers_public.py', '--limit', '15', '--workers', '1', '--summary-file', str(RUN / 'covers-stats.json')], RUN / 'covers-stats.json', None),
    ('portraits', ['research/enrich_catalog_portraits.py', '--limit', '40'], ROOT / 'research/_runs/2026-09-28/portraits/latest-stats.json', ROOT / 'research/_runs/2026-09-28/portraits/provider-cooldown.json'),
    *[(name, ['research/enrich_media_alternatives.py', name, '--limit', '5'],
       RUN / f'{name}-stats.json', RUN / f'{name}-cooldown.json')
      for name in ('loc-portraits', 'gallica-portraits', 'loc-covers', 'gallica-covers', 'publisher-covers')],
]
# Cover recovery is the owner's current priority. Finish a bounded cover
# rotation before portrait discovery; neither family bypasses source waits.
JOBS.sort(key=lambda job: not (job[0] == 'covers' or job[0].endswith('-covers')))


def read(path):
    return read_state(path, cooldown=bool(path and 'cooldown' in Path(path).name))


def count_additions(state, name, stats):
    added = stats.get('covered', stats.get('portraits', 0))
    state['added_this_run'] = state.get('added_this_run', 0) + added
    if name == 'covers' or name.endswith('-covers'):
        field = 'covers_saved_this_run'
    elif name == 'portraits' or name.endswith('-portraits'):
        field = 'portraits_saved_this_run'
    else:
        return
    state[field] = state.get(field, 0) + added


def wake_catalog_reuse(health, selected, source, added):
    if (added and source != 'catalog-covers' and (source == 'covers' or source.endswith('-covers'))
            and any(job[0] == 'catalog-covers' for job in selected)
            and health.get('catalog-covers', {}).get('status') == 'exhausted'):
        health['catalog-covers'] = {'status': 'ready'}


def remaining_report(save=True, health=None):
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.config.settings')
    import django
    django.setup()
    from research.media_inventory import inventory
    totals, missing = inventory(STATE, JOBS, health or read(RUN / 'provider-health.json'))
    if save:
        atomic_state(RUN / 'unresolved.json', missing)
    return totals


def running():
    path = STATE / 'media-completion.lock'
    if not path.exists():
        return False
    with path.open('r') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
    return False


def live_batch_progress(state):
    """Read only the current batch's summary; never count a previous batch twice."""
    started = timestamp(state.get('current_batch_started_at'))
    if not started:
        return {}
    for name, _, summary, _ in JOBS:
        if name != state.get('current_provider'):
            continue
        if state.get('current_stage') == 'cached_images':
            summary = RUN / f'{name}-cached-stats.json'
        try:
            if summary.stat().st_mtime < started:
                return {}
        except OSError:
            return {}
        stats = read(summary)
        return stats if not stats.get('invalid_state') else {}
    return {}


def run_child(args):
    log = RUN / 'worker.log'
    rotate(log)
    with log.open('a') as output:
        process = subprocess.Popen([PYTHON, *args], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        while process.poll() is None:
            if HEARTBEAT:
                HEARTBEAT()
            if STOP.exists():
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass  # The child may finish between poll() and killpg().
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
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
    parser.add_argument('--batch-seconds', type=int, default=60,
                        help='Soft time budget per alternative-source batch; finish each active record before yielding. 0 disables it.')
    parser.add_argument('--providers', help='Optional comma-separated provider names for a bounded trial.')
    args = parser.parse_args()
    if args.max_batches < 0:
        parser.error('--max-batches must be zero or positive.')
    if args.batch_seconds < 0:
        parser.error('--batch-seconds must be zero or positive.')
    selected = [job for job in JOBS if not args.providers or job[0] in args.providers.split(',')]
    unknown = set(args.providers.split(',')) - {job[0] for job in JOBS} if args.providers else set()
    if unknown or not selected:
        parser.error('Unknown or empty provider selection: ' + ', '.join(sorted(unknown)))
    if args.status:
        state = read(RUN / 'status.json')
        state.update(remaining_report(save=False))
        state['process_active'] = running()
        if state['process_active']:
            progress = live_batch_progress(state)
            if progress:
                state['current_batch'] = progress
                state['completed_batch_additions'] = state.get('added_this_run', 0)
                count_additions(state, state['current_provider'], progress)
                state.setdefault('providers', {})[state['current_provider']] = progress
        if state.get('status') in {'running', 'backing_up', 'waiting_for_provider'} and not state['process_active']:
            state['status'] = 'not_running'
        if state.get('status') == 'complete' and state['missing_covers'] + state['missing_portraits'] > 0:
            state['status'] = 'needs_review'
        state['provider_health'] = read(RUN / 'provider-health.json')
        state['source_scheduling'] = read(RUN / 'source-scheduling.json')
        print(json.dumps(state, indent=2))
        return
    RUN.mkdir(parents=True, exist_ok=True)
    STATE.mkdir(parents=True, exist_ok=True)
    if args.stop:
        STOP.touch()
        print('Stop requested. Saved results are retained; rerun the same command to resume.')
        return
    if args.background:
        with exclusive('media-completion'):
            pass
        rotate(RUN / 'runner.log')
        options = (['--max-batches', str(args.max_batches)] if args.max_batches else [])
        options += ['--batch-seconds', str(args.batch_seconds)]
        if args.providers:
            options += ['--providers', args.providers]
        with (RUN / 'runner.log').open('a') as output:
            child = subprocess.Popen([PYTHON, str(Path(__file__).resolve()), *options], cwd=ROOT,
                                     stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        print(f'Runner launched (PID {child.pid}). Use --status or --stop. Log: {RUN / "worker.log"}')
        return
    with exclusive('media-completion'), exclusive('supervisor'):
        STOP.unlink(missing_ok=True)
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: STOP.touch())
        health = read(RUN / 'provider-health.json')
        scheduling = {name: normalize(value) for name, value in read(RUN / 'source-scheduling.json').items()
                      if isinstance(value, dict)}
        # Recheck exhausted/configured providers on a deliberate restart, while
        # retaining provider-wide cooldowns and failure counts across restarts.
        health = {name: value for name, value in health.items() if isinstance(value, dict)}
        for name, *_ in selected:
            if health.get(name, {}).get('status') != 'cooldown':
                health[name] = {'status': 'ready'}
        state = {'pid': os.getpid(), 'started_at': time.time(), 'status': 'backing_up',
                 'batches': 0, 'added_this_run': 0, 'covers_saved_this_run': 0,
                 'portraits_saved_this_run': 0, 'providers': {}, 'cached_downloads': {}}
        cached_due = {name: 0 for name, command, *_ in selected
                      if command[0] == 'research/enrich_media_alternatives.py'}
        def save():
            state['updated_at'] = time.time()
            state['heartbeat_at'] = state['updated_at']
            state['provider_health'] = health
            state['source_scheduling'] = scheduling
            atomic_state(RUN / 'provider-health.json', health)
            atomic_state(RUN / 'source-scheduling.json', scheduling)
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
        state['starting_covers_ready'] = state.get('covers_ready')
        state['starting_portraits_ready'] = state.get('portraits_ready')
        if state['missing_covers'] + state['missing_portraits'] == 0:
            state['status'] = 'complete'
            save()
            return 0

        def cached_downloads(name):
            """Download checkpoints independently of metadata source health."""
            summary = RUN / f'{name}-cached-stats.json'
            summary.unlink(missing_ok=True)
            state.update(status='running', current_provider=name, current_stage='cached_images',
                         current_batch_started_at=time.time())
            save()
            started = time.monotonic()
            code = run_child(['research/enrich_media_alternatives.py', name, '--cached-only',
                              '--limit', '60', '--max-seconds', str(args.batch_seconds)])
            stats = live_batch_progress(state)
            state.pop('current_batch_started_at', None)
            state.pop('current_stage', None)
            added = stats.get('covered', 0)
            count_additions(state, name, stats)
            state['batches'] += 1
            if added:
                scheduling[name] = observe(scheduling.get(name, {}), stats, time.monotonic() - started)
                wake_catalog_reuse(health, selected, name, added)
                state.update(remaining_report(health=health))
            if code and not STOP.exists():
                stats = {**stats, 'worker_failed': True, 'exit_code': code}
            state['cached_downloads'][name] = stats
            now = time.time()
            retry = timestamp(stats.get('cached_next_retry'))
            remaining = max(0, stats.get('queued', 0) - stats.get('processed', 0))
            cached_due[name] = (now + 1 if remaining and not code else
                                max(now + 1, retry) if retry else now + 300)
            # Metadata health/cooldown files are deliberately unchanged here.
            save()

        while not STOP.exists():
            ran = False
            for name, command, summary, cooldown in selected:
                if STOP.exists():
                    break
                now = time.time()
                if name in cached_due and cached_due[name] <= now:
                    cached_downloads(name)
                    ran = True
                    if STOP.exists():
                        break
                    if state['missing_covers'] + state['missing_portraits'] == 0:
                        state['status'] = 'complete'
                        state.pop('current_provider', None)
                        save()
                        return 0
                    if args.max_batches and state['batches'] >= args.max_batches:
                        state['status'] = 'batch_limit'
                        state.pop('current_provider', None)
                        save()
                        return 0
                    now = time.time()
                if not eligible(health.get(name, {}), now):
                    continue
                until = timestamp(read(cooldown).get('until'))
                if until > now:
                    health[name] = {**health.get(name, {}), 'status': 'cooldown', 'retry_at': until}
                    continue
                if due_at(health.get(name, {}), scheduling.get(name, {}), until) > now:
                    continue
                summary.unlink(missing_ok=True)
                state.update(status='running', current_provider=name, current_batch_started_at=time.time())
                save()
                # A recovering provider gets one record, not a full batch of
                # records that might all be charged for the same outage.
                actual_command = list(command)
                if actual_command[0] in {'research/enrich_media_alternatives.py', 'research/enrich_catalog_covers_public.py'}:
                    actual_command += ['--max-seconds', str(args.batch_seconds)]
                if health.get(name, {}).get('status') == 'cooldown' and '--limit' in actual_command:
                    actual_command[actual_command.index('--limit') + 1] = '1'
                child_started = time.monotonic()
                code = run_child(actual_command)
                child_seconds = max(0, time.monotonic() - child_started)
                if STOP.exists():
                    progress = live_batch_progress(state)
                    partial_added = progress.get('covered', progress.get('portraits', 0))
                    count_additions(state, name, progress)
                    if partial_added:
                        # A checkpointed success clears the empty streak even
                        # if stop interrupted the rest of the batch. Incomplete
                        # empty batches are not reliable yield measurements.
                        scheduling[name] = observe(scheduling.get(name, {}), progress, child_seconds)
                    state.pop('current_batch_started_at', None)
                    break
                stats = read(summary)
                state.pop('current_batch_started_at', None)
                state['batches'] += 1
                ran = True
                if code or not stats or stats.get('invalid_state'):
                    health[name] = {'status': 'worker_failed', 'exit_code': code, 'updated_at': time.time()}
                    state['providers'][name] = health[name]
                else:
                    processed = stats.get('processed', 0)
                    added = stats.get('covered', stats.get('portraits', 0))
                    count_additions(state, name, stats)
                    state['providers'][name] = stats
                    health[name] = outcome(health.get(name, {}), stats, read(cooldown).get('until', 0))
                    scheduling[name] = observe(scheduling.get(name, {}), stats, child_seconds)
                    wake_catalog_reuse(health, selected, name, added)
                    if name in cached_due and stats.get('cached_waiting'):
                        # A metadata batch can checkpoint ready images before
                        # a later request fails. Its fresh queue deadline
                        # supersedes the previous empty-cache polling time;
                        # the metadata cooldown must not delay these images.
                        cached_due[name] = max(time.time() + 1, timestamp(stats.get('cached_next_retry')))
                    elif name in cached_due and stats.get('image_deferred'):
                        cached_due[name] = min(cached_due[name], max(time.time() + 1, timestamp(stats.get('next_retry'))))
                    print(f'{name}: processed {processed}, added {added}; total added this run {state["added_this_run"]}', flush=True)
                # Counts are current after every batch; image decoding reuses
                # signatures until a file changes. --status also reads live data.
                state.update(remaining_report(health=health))
                if state['missing_covers'] + state['missing_portraits'] == 0:
                    state['status'] = 'complete'
                    state.pop('current_provider', None)
                    save()
                    return 0
                save()
                if args.max_batches and state['batches'] >= args.max_batches:
                    state['status'] = 'batch_limit'
                    state.pop('current_provider', None)
                    save()
                    return 0
            inactive = {'exhausted', 'worker_failed', 'credential_required'}
            cached_waiting = any(stats.get('cached_waiting') for stats in state['cached_downloads'].values())
            if all(health.get(name, {}).get('status') in inactive for name, *_ in selected) and not cached_waiting:
                state.update(remaining_report(health=health))
                state['status'] = 'complete' if state['missing_covers'] + state['missing_portraits'] == 0 else 'needs_review'
                state.pop('current_provider', None)
                save()
                print(json.dumps(state, indent=2), flush=True)
                return 0 if state['status'] == 'complete' else 2
            if not ran:
                retries = [due_at(health.get(name, {}), scheduling.get(name, {}), read(cooldown).get('until', 0))
                           for name, _, _, cooldown in selected
                           if health.get(name, {}).get('status') not in inactive]
                retries += list(cached_due.values())
                state.update(status='waiting_for_provider', retry_at=min(retries, default=time.time() + 30))
                state.pop('current_provider', None)
                save()
                time.sleep(min(30, max(1, state['retry_at'] - time.time())))
        state.update(remaining_report(health=health))
        state['status'] = 'stopped'
        state.pop('current_provider', None)
        save()
        return 0


if __name__ == '__main__':
    sys.exit(main())
