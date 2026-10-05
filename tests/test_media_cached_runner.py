import contextlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research import complete_catalog_media as runner


class CachedRunnerTests(unittest.TestCase):
    def test_cached_cover_reactivates_local_reuse_during_metadata_cooldown(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            name = 'reviewed-covers'
            cooldown = {'status': 'cooldown', 'retry_at': 9000, 'consecutive_failures': 3}
            (root / 'provider-health.json').write_text(json.dumps({name: cooldown}))
            local_summary = root / 'catalog.json'
            jobs = [
                ('catalog-covers', ['research/reuse_catalog_covers.py'], local_summary, None),
                (name, ['research/enrich_media_alternatives.py', name], root / 'reviewed.json', None),
            ]
            stages = []

            def child(command):
                if command[0] == 'manage.py':
                    return 0
                if command[0] == 'research/reuse_catalog_covers.py':
                    # Initial local scan is empty. Downloading the source cover
                    # then unlocks one reviewed equivalent without restarting.
                    added = int('cached-cover' in stages)
                    stages.append('local-reuse')
                    local_summary.write_text(json.dumps({'processed': added, 'covered': added}))
                else:
                    self.assertIn('--cached-only', command)
                    stages.append('cached-cover')
                    (root / f'{name}-cached-stats.json').write_text(json.dumps(
                        {'queued': 1, 'processed': 1, 'covered': 1, 'cached_waiting': 0}))
                return 0

            with patch.object(runner, 'RUN', root), patch.object(runner, 'STATE', root), \
                    patch.object(runner, 'STOP', root / 'stop'), patch.object(runner, 'JOBS', jobs), \
                    patch.object(runner, 'exclusive', lambda _: contextlib.nullcontext()), \
                    patch.object(runner, 'run_child', side_effect=child), \
                    patch.object(runner, 'remaining_report', return_value={'missing_covers': 1, 'missing_portraits': 0}), \
                    patch.object(runner.signal, 'signal'), patch.object(runner.time, 'time', return_value=1000), \
                    patch.object(runner.time, 'sleep', side_effect=AssertionError('Local reuse remained exhausted')), \
                    patch.object(runner.sys, 'argv', ['runner', '--max-batches', '3']), patch('builtins.print'):
                self.assertEqual(runner.main(), 0)
            self.assertEqual(stages, ['local-reuse', 'cached-cover', 'local-reuse'])
            saved = json.loads((root / 'status.json').read_text())
            self.assertEqual(saved['added_this_run'], 2)
            self.assertEqual(saved['covers_saved_this_run'], 2)
            self.assertEqual(saved['provider_health'][name], cooldown)
            self.assertEqual(saved['provider_health']['catalog-covers']['status'], 'ready')

    def test_new_cover_does_not_clear_local_reuse_failure_or_cooldown(self):
        jobs = [('catalog-covers', ['research/reuse_catalog_covers.py'], None, None)]
        for state in ({'status': 'cooldown', 'retry_at': 9000, 'consecutive_failures': 3},
                      {'status': 'worker_failed', 'exit_code': 1}):
            with self.subTest(state=state):
                health = {'catalog-covers': dict(state)}
                runner.wake_catalog_reuse(health, jobs, 'reviewed-covers', 1)
                self.assertEqual(health, {'catalog-covers': state})

    def test_partial_discovery_hands_ready_images_to_cached_worker_at_queue_deadline(self):
        # An initial empty pass schedules another check at t=1300. A normal
        # batch then checkpoints images before metadata returns HTTP429.
        # Ready images should run at t=1001; genuinely deferred images must
        # instead retain their t=1400 queue deadline, beyond the old poll.
        for queue_retry, expected in ((1000, 1001), (1400, 1400)):
            with self.subTest(queue_retry=queue_retry), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                name = 'cached-wikidata-portraits'
                normal = root / 'normal.json'
                cached = root / f'{name}-cached-stats.json'
                jobs = [(name, ['research/enrich_media_alternatives.py', name], normal, None)]
                clock = [1000]
                stages = []
                def child(command):
                    if command[0] == 'manage.py':
                        return 0
                    if '--cached-only' in command:
                        stages.append(('cached', clock[0]))
                        if len(stages) == 1:
                            stats = {'queued': 0, 'processed': 0, 'covered': 0,
                                     'cached_waiting': 0, 'cached_next_retry': None}
                        else:
                            self.assertEqual(clock[0], expected)
                            stats = {'queued': 1, 'processed': 1, 'covered': 1,
                                     'cached_waiting': 0, 'cached_next_retry': None}
                        cached.write_text(json.dumps(stats))
                    else:
                        stages.append(('metadata', clock[0]))
                        self.assertEqual(len(stages), 2)
                        normal.write_text(json.dumps({
                            'queued': 2, 'processed': 1, 'covered': 0, 'provider_errors': 1,
                            'provider_outage': True, 'http_status': 429, 'outage_type': 'unavailable',
                            'retry_after': 9000, 'image_deferred': 0,
                            'cached_waiting': 1, 'cached_next_retry': queue_retry,
                        }))
                    return 0
                def sleep(seconds):
                    clock[0] += seconds
                    self.assertLessEqual(clock[0], expected, 'Ready image waited behind an unrelated deadline')
                with patch.object(runner, 'RUN', root), patch.object(runner, 'STATE', root), \
                        patch.object(runner, 'STOP', root / 'stop'), patch.object(runner, 'JOBS', jobs), \
                        patch.object(runner, 'exclusive', lambda _: contextlib.nullcontext()), \
                        patch.object(runner, 'run_child', side_effect=child), \
                        patch.object(runner, 'remaining_report', return_value={'missing_covers': 1, 'missing_portraits': 1}), \
                        patch.object(runner.signal, 'signal'), \
                        patch.object(runner.time, 'time', side_effect=lambda: clock[0]), \
                        patch.object(runner.time, 'sleep', side_effect=sleep), \
                        patch.object(runner.sys, 'argv', ['runner', '--max-batches', '3']), patch('builtins.print'):
                    self.assertEqual(runner.main(), 0)
                self.assertEqual(stages, [('cached', 1000), ('metadata', 1000), ('cached', expected)])
                saved = json.loads((root / 'status.json').read_text())
                self.assertEqual(saved['added_this_run'], 1)
                self.assertEqual(saved['provider_health'][name]['http_status'], 429)
                self.assertEqual(saved['provider_health'][name]['retry_at'], 9000)

    def test_cached_download_runs_during_metadata_pause_preserving_health(self):
        self.check_paused_metadata('openlibrary-portraits')

    def test_verified_covers_download_while_wikipedia_metadata_is_rate_limited(self):
        self.check_paused_metadata('wikipedia-covers')

    def check_paused_metadata(self, name):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            health = {'status': 'cooldown', 'retry_at': 9000, 'consecutive_failures': 3}
            (root / 'provider-health.json').write_text(json.dumps({name: health}))
            (root / 'source-scheduling.json').write_text(json.dumps({name: {'sample_after': 7000}}))
            jobs = [(name, ['research/enrich_media_alternatives.py', name], root / 'normal.json', None)]
            calls = []
            def child(command):
                calls.append(command)
                if command[0] == 'research/enrich_media_alternatives.py':
                    self.assertIn('--cached-only', command)
                    (root / f'{name}-cached-stats.json').write_text(json.dumps(
                        {'queued': 3, 'processed': 3, 'covered': 2, 'cached_waiting': 1, 'cached_next_retry': 2000}))
                return 0
            with patch.object(runner, 'RUN', root), patch.object(runner, 'STATE', root), \
                    patch.object(runner, 'STOP', root / 'stop'), patch.object(runner, 'JOBS', jobs), \
                    patch.object(runner, 'exclusive', lambda _: contextlib.nullcontext()), \
                    patch.object(runner, 'run_child', side_effect=child), \
                    patch.object(runner, 'remaining_report', return_value={'missing_covers': 1, 'missing_portraits': 1}), \
                    patch.object(runner.signal, 'signal'), patch.object(runner.time, 'time', return_value=1000), \
                    patch.object(runner.sys, 'argv', ['runner', '--max-batches', '1']), patch('builtins.print'):
                self.assertEqual(runner.main(), 0)
            saved = json.loads((root / 'status.json').read_text())
            self.assertEqual(saved['added_this_run'], 2)
            self.assertEqual(saved['provider_health'][name], health)
            self.assertEqual(saved['cached_downloads'][name]['cached_next_retry'], 2000)
            self.assertEqual(saved['source_scheduling'][name]['sample_after'], 0)
            self.assertEqual(len(calls), 2)

    def test_live_progress_uses_separate_cached_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cached = root / 'source-cached-stats.json'
            cached.write_text('{"covered": 4}')
            normal = root / 'normal.json'
            normal.write_text('{"covered": 99}')
            with patch.object(runner, 'RUN', root), patch.object(runner, 'JOBS', [('source', ['worker'], normal, None)]):
                state = {'current_provider': 'source', 'current_stage': 'cached_images',
                         'current_batch_started_at': cached.stat().st_mtime - 1}
                self.assertEqual(runner.live_batch_progress(state), {'covered': 4})
