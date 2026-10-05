import contextlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from research import complete_catalog_media as runner


class MediaRunnerTests(unittest.TestCase):
    def test_stop_clears_sampling_only_for_a_checkpointed_partial_success(self):
        old = {'empty_records': 100, 'empty_seconds': 60, 'sample_after': 900}
        for saved in (0, 1):
            with self.subTest(saved=saved), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                summary, stop = root / 'partial.json', root / 'stop'
                (root / 'source-scheduling.json').write_text(json.dumps({'source': old}))

                def child(command):
                    if command[0] == 'worker':
                        summary.write_text(json.dumps({'processed': 2, 'covered': saved}))
                        stop.touch()
                        return -15
                    return 0

                with patch.object(runner, 'RUN', root), patch.object(runner, 'STATE', root), \
                        patch.object(runner, 'STOP', stop), \
                        patch.object(runner, 'JOBS', [('source', ['worker'], summary, None)]), \
                        patch.object(runner, 'exclusive', lambda _: contextlib.nullcontext()), \
                        patch.object(runner, 'run_child', side_effect=child), \
                        patch.object(runner, 'remaining_report', return_value={'missing_covers': 1, 'missing_portraits': 1}), \
                        patch.object(runner.signal, 'signal'), \
                        patch.object(runner.time, 'time', return_value=1000), \
                        patch.object(runner.sys, 'argv', ['runner']), patch('builtins.print'):
                    self.assertEqual(runner.main(), 0)
                state = json.loads((root / 'status.json').read_text())
                self.assertEqual(state['status'], 'stopped')
                self.assertEqual(state['added_this_run'], saved)
                expected = {'empty_records': 0, 'empty_seconds': 0, 'sample_after': 0} if saved else old
                self.assertEqual(state['source_scheduling']['source'], expected)
                self.assertEqual(json.loads((root / 'source-scheduling.json').read_text())['source'], expected)

    def test_empty_source_waits_and_resamples_after_restart_without_becoming_exhausted(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            summary = root / 'slow-stats.json'
            schedule = root / 'source-scheduling.json'
            schedule.write_text(json.dumps({'slow': {
                'empty_records': 100, 'empty_seconds': 60, 'sample_after': 1300}}))
            now = [1000.0]
            calls, waits = [], []

            def child(command):
                if command[0] == 'worker':
                    calls.append(now[0])
                    now[0] += 4
                    summary.write_text(json.dumps({'processed': 5, 'covered': 0}))
                return 0

            def sleep(seconds):
                self.assertGreater(seconds, 0)
                self.assertLessEqual(seconds, 30)
                waits.append(seconds)
                now[0] += seconds

            with patch.object(runner, 'RUN', root), patch.object(runner, 'STATE', root), \
                    patch.object(runner, 'STOP', root / 'stop'), \
                    patch.object(runner, 'JOBS', [('slow', ['worker'], summary, None)]), \
                    patch.object(runner, 'exclusive', lambda _: contextlib.nullcontext()), \
                    patch.object(runner, 'run_child', side_effect=child), \
                    patch.object(runner, 'remaining_report', return_value={'missing_covers': 1, 'missing_portraits': 1}), \
                    patch.object(runner.signal, 'signal'), \
                    patch.object(runner.time, 'time', side_effect=lambda: now[0]), \
                    patch.object(runner.time, 'monotonic', side_effect=lambda: now[0]), \
                    patch.object(runner.time, 'sleep', side_effect=sleep), \
                    patch.object(runner.sys, 'argv', ['runner', '--max-batches', '1']), patch('builtins.print'):
                self.assertEqual(runner.main(), 0)
                state = json.loads((root / 'status.json').read_text())
                self.assertEqual(state['status'], 'batch_limit')
                self.assertEqual(state['provider_health']['slow']['status'], 'ready')
                self.assertEqual(state['source_scheduling']['slow'], {
                    'empty_records': 105, 'empty_seconds': 64, 'sample_after': 1604})
                self.assertEqual(runner.main(), 0)
            self.assertEqual(calls, [1300, 1604])
            self.assertEqual(waits, [30] * 20)
            self.assertEqual(json.loads(schedule.read_text())['slow'], {
                'empty_records': 110, 'empty_seconds': 68, 'sample_after': 1908})

    def test_sampling_status_is_exposed_separately_from_provider_health(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            saved = {'slow': {'empty_records': 100, 'empty_seconds': 60, 'sample_after': 1300}}
            (root / 'source-scheduling.json').write_text(json.dumps(saved))
            (root / 'provider-health.json').write_text(json.dumps({'slow': {'status': 'ready'}}))
            with patch.object(runner, 'RUN', root), patch.object(runner, 'running', return_value=False), \
                    patch.object(runner, 'remaining_report', return_value={}), \
                    patch.object(runner.sys, 'argv', ['runner', '--status']), patch('builtins.print') as output:
                runner.main()
            report = json.loads(output.call_args.args[0])
            self.assertEqual(report['source_scheduling'], saved)
            self.assertEqual(report['provider_health']['slow']['status'], 'ready')

    def test_status_reports_live_saves_without_mutating_completed_batch_total(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            summary = root / 'source-stats.json'
            summary.write_text(json.dumps({'processed': 4, 'covered': 3}))
            started = summary.stat().st_mtime - 1
            saved = {'status': 'running', 'current_provider': 'source',
                     'current_batch_started_at': started, 'added_this_run': 5}
            (root / 'status.json').write_text(json.dumps(saved))
            with patch.object(runner, 'RUN', root), \
                    patch.object(runner, 'JOBS', [('source', ['worker'], summary, None)]), \
                    patch.object(runner, 'running', return_value=True), \
                    patch.object(runner, 'remaining_report', return_value={}), \
                    patch.object(runner.sys, 'argv', ['runner', '--status']), patch('builtins.print') as output:
                runner.main()
                report = json.loads(output.call_args.args[0])
                self.assertEqual(report['added_this_run'], 8)
                self.assertEqual(report['current_batch']['processed'], 4)
                self.assertEqual(json.loads((root / 'status.json').read_text())['added_this_run'], 5)
                # An older summary is never attributed to a new batch.
                os.utime(summary, (started - 1, started - 1))
                runner.main()
                self.assertEqual(json.loads(output.call_args.args[0])['added_this_run'], 5)

    def test_completed_batch_summary_cannot_be_counted_again(self):
        with tempfile.TemporaryDirectory() as folder:
            summary = Path(folder) / 'stats.json'
            summary.write_text(json.dumps({'processed': 4, 'covered': 3}))
            with patch.object(runner, 'JOBS', [('source', ['worker'], summary, None)]):
                self.assertEqual(runner.live_batch_progress({'current_provider': 'source', 'added_this_run': 8}), {})

    def run_runner(self, counts, worker_code=0, *, initial_health=None, reports=None, worker_stats=None, cooling_job=False):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            summary = root / 'summary.json'
            job = ('fake', ['worker'], summary, None)
            jobs = [job]
            if cooling_job:
                jobs.append(('cooling', ['cooling-worker'], root / 'cooling.json', None))
            if initial_health:
                (root / 'provider-health.json').write_text(json.dumps(initial_health))
            def child(command):
                if command[0] == 'worker':
                    summary.write_text(json.dumps(worker_stats or {'processed': 0, 'next_retry': None}))
                    return worker_code
                return 0
            with patch.object(runner, 'RUN', root), patch.object(runner, 'STATE', root), patch.object(runner, 'STOP', root/'stop'), patch.object(runner, 'JOBS', jobs), patch.object(runner, 'exclusive', lambda _: contextlib.nullcontext()), patch.object(runner, 'run_child', side_effect=child), patch.object(runner, 'remaining_report', return_value=counts, side_effect=reports), patch.object(runner.signal, 'signal'), patch.object(runner.sys, 'argv', ['runner']), patch.object(runner.time, 'sleep', side_effect=AssertionError('Unexpected wait')), patch('builtins.print'):
                code = runner.main()
            return code, json.loads((root/'status.json').read_text())

    def test_empty_provider_queue_is_not_catalog_completion(self):
        code, state = self.run_runner({'missing_covers': 12, 'missing_portraits': 3})
        self.assertEqual(code, 2)
        self.assertEqual(state['status'], 'needs_review')

    def test_completion_requires_no_missing_media(self):
        code, state = self.run_runner({'missing_covers': 0, 'missing_portraits': 0})
        self.assertEqual(code, 0)
        self.assertEqual(state['status'], 'complete')

    def test_worker_failure_is_reported_and_never_spins(self):
        code, state = self.run_runner({'missing_covers': 1, 'missing_portraits': 0}, worker_code=1)
        self.assertEqual(code, 2)
        self.assertEqual(state['providers']['fake']['status'], 'worker_failed')
        self.assertEqual(state['batches'], 1)

    def test_already_complete_catalog_does_not_wait_for_cooling_provider(self):
        code, state = self.run_runner({'missing_covers': 0, 'missing_portraits': 0},
            initial_health={'fake': {'status': 'cooldown', 'retry_at': 999999999999}})
        self.assertEqual(code, 0)
        self.assertEqual(state['status'], 'complete')
        self.assertEqual(state['batches'], 0)

    def test_final_image_completes_without_waiting_for_other_provider(self):
        missing = {'missing_covers': 1, 'missing_portraits': 0}
        complete = {'missing_covers': 0, 'missing_portraits': 0}
        code, state = self.run_runner(missing, reports=[missing, complete],
            worker_stats={'processed': 1, 'covered': 1}, cooling_job=True,
            initial_health={'cooling': {'status': 'cooldown', 'retry_at': 999999999999}})
        self.assertEqual(code, 0)
        self.assertEqual(state['status'], 'complete')
        self.assertEqual(state['batches'], 1)
        self.assertNotIn('current_provider', state)

    def test_stop_handles_child_finishing_between_poll_and_signal(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            stop = root / 'stop'
            stop.touch()
            process = Mock(pid=12345)
            process.poll.return_value = None
            process.wait.return_value = 0
            with patch.object(runner, 'RUN', root), patch.object(runner, 'STOP', stop), \
                    patch.object(runner, 'HEARTBEAT', None), patch.object(runner.subprocess, 'Popen', return_value=process), \
                    patch.object(runner.os, 'killpg', side_effect=ProcessLookupError):
                self.assertEqual(runner.run_child(['fake-worker']), -runner.signal.SIGTERM)
            process.wait.assert_called_once_with(timeout=20)

    def test_live_status_does_not_repeat_stale_completion_after_catalog_grows(self):
        def saved(path):
            return {'status': 'complete'} if path.name == 'status.json' else {}
        with patch.object(runner, 'read', side_effect=saved), \
                patch.object(runner, 'remaining_report', return_value={'missing_covers': 1, 'missing_portraits': 0}), \
                patch.object(runner, 'running', return_value=False), \
                patch.object(runner.sys, 'argv', ['runner', '--status']), patch('builtins.print') as printed:
            runner.main()
        status = json.loads(printed.call_args.args[0])
        self.assertEqual(status['status'], 'needs_review')
        self.assertEqual(status['missing_covers'], 1)
