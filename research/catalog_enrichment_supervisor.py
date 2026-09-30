"""Bounded enrichment coordinator; no progress inference from log length."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from enrichment_queue import ROOT, STATE, exclusive, rotate
from operational_state import atomic_state, read_state

RUN = ROOT / 'research/_runs/catalog-enrichment-supervisor'
STOP = STATE / 'stop'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', nargs='?', choices=['pages', 'covers', 'both'], default='both')
    parser.add_argument('--max-batches', type=int, default=10)
    parser.add_argument('--batch-size', type=int)
    parser.add_argument('--background', action='store_true')
    parser.add_argument('--stop', action='store_true')
    args = parser.parse_args()
    if args.max_batches < 1 or (args.batch_size is not None and args.batch_size < 1):
        parser.error('Batch counts and sizes must be positive.')
    STATE.mkdir(parents=True, exist_ok=True); RUN.mkdir(parents=True, exist_ok=True)
    if args.stop:
        STOP.touch(); print('Cooperative stop requested.'); return
    if args.background:
        with exclusive('supervisor'):
            rotate(RUN / 'supervisor.log')
        with (RUN / 'supervisor.log').open('a') as output:
            command = [sys.executable, __file__, args.mode, '--max-batches', str(args.max_batches)]
            if args.batch_size: command += ['--batch-size', str(args.batch_size)]
            process = subprocess.Popen(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        print(f'Start requested (PID {process.pid}); see {RUN / "supervisor.log"}. An exclusive lock prevents duplicate runs.')
        return
    with exclusive('supervisor'):
        status_file = RUN / 'status.json'
        previous = read_state(status_file)
        if previous.get('invalid_state'):
            print('Previous supervisor status is unreadable; inspect it before resuming provider requests.')
            return 1
        if previous.get('retry_after', 0) > time.time():
            print('Provider cooldown is active; restart after the recorded retry_after time.'); return 0
        STOP.unlink(missing_ok=True)
        pid_path = RUN / 'supervisor.pid'
        pid_path.write_text(str(os.getpid()))
        stopping = False
        def stop(signum, frame):
            nonlocal stopping
            stopping = True
        signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
        summary = {'status': 'running', 'pid': os.getpid(), 'batches': 0, 'started_at': time.time()}
        def save_status():
            summary['heartbeat_at'] = time.time()
            atomic_state(status_file, summary)
        save_status()
        try:
            for cycle in range(args.max_batches):
                completed = 0
                summaries = []
                for kind in (['pages', 'covers'] if args.mode == 'both' else [args.mode]):
                    if stopping or STOP.exists(): break
                    filename = 'enrich_catalog_page_counts.py' if kind == 'pages' else 'enrich_catalog_covers_public.py'
                    size = args.batch_size or int(os.getenv('PAGE_BATCH' if kind == 'pages' else 'COVER_BATCH', '120' if kind == 'pages' else '50'))
                    stats_file = STATE / f'{kind}-batch.json'
                    stats_file.unlink(missing_ok=True)
                    command = [sys.executable, str(ROOT / 'research' / filename), '--limit', str(size), '--workers', '2', '--summary-file', str(stats_file)]
                    if kind == 'covers': command += ['--clean-series-title', '--clean-subtitle']
                    else: command += ['--request-interval', '0.8']
                    print(json.dumps({'cycle': cycle + 1, 'kind': kind, 'status': 'starting'}), flush=True)
                    child = subprocess.Popen(command, cwd=ROOT, start_new_session=True)
                    while child.poll() is None:
                        if time.time() - summary['heartbeat_at'] >= 15:
                            save_status()
                        if stopping or STOP.exists():
                            child.terminate()
                            try: child.wait(timeout=20)
                            except subprocess.TimeoutExpired: child.kill(); child.wait()
                            break
                        time.sleep(0.5)
                    if stopping or STOP.exists(): break
                    if child.returncode != 0 or not stats_file.exists():
                        summary.update(status='error', kind=kind, returncode=child.returncode)
                        return 1
                    stats = read_state(stats_file)
                    if not stats or stats.get('invalid_state'):
                        summary.update(status='error', kind=kind, reason='unreadable_batch_summary')
                        return 1
                    summaries.append({'kind': kind, **stats})
                    completed += stats.get('processed', 0)
                summary.update(batches=cycle + 1, last_batch=summaries)
                if stopping or STOP.exists(): summary['status'] = 'stopped'; break
                save_status()
                if any(s.get('provider_errors', 0) >= max(3, s.get('processed', 0) // 2) for s in summaries):
                    summary['status'] = 'provider_cooldown'
                    summary['retry_after'] = time.time() + 900
                    break
                if not completed:
                    summary['status'] = 'waiting' if any(s.get('next_retry') for s in summaries) else 'exhausted'
                    break
            else:
                summary['status'] = 'batch_limit'
        finally:
            summary['finished_at'] = time.time()
            save_status()
            pid_path.unlink(missing_ok=True)
            print(json.dumps(summary), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
