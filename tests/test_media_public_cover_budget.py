import io
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from research import enrich_catalog_covers_public as media
from research import enrichment_queue


class PublicCoverBudgetTests(unittest.TestCase):
    def items(self, count=4):
        return [{'id': i, 'title': f'Book {i}', 'authors': ['A. Writer']}
                for i in range(1, count + 1)]

    def test_deadline_finishes_active_lookup_and_leaves_unstarted_attempts_at_zero(self):
        clock = SimpleNamespace(value=0)

        def lookup(item, skip_archive, skip_openlibrary):
            clock.value = 11
            return None, 'openlibrary_no_safe_cover'

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / 'outcomes.jsonl'
            with patch.object(enrichment_queue, 'STATE', root / 'queue'):
                queue = enrichment_queue.Queue('covers-budget-test', ledger)
            try:
                items = self.items()
                for item in items:
                    self.assertTrue(queue.due(item, 'test-policy'))
                with patch.object(media, 'time', SimpleNamespace(monotonic=lambda: clock.value)), \
                        patch.object(media, 'lookup', side_effect=lookup) as attempted, \
                        ledger.open('a') as output:
                    for item, future in media.completed_lookups(items, workers=1, deadline=10):
                        _, reason = future.result()
                        queue.finish(item, {'work_id': item['id'], 'status': reason}, output)
                self.assertEqual(attempted.call_count, 1)
                self.assertEqual(queue.db.execute(
                    'SELECT work_id,attempts,state FROM attempts ORDER BY work_id').fetchall(),
                    [(1, 1, 'unresolved'), (2, 0, 'pending'), (3, 0, 'pending'), (4, 0, 'pending')])
                self.assertEqual(queue.batch_errors, 0)
                self.assertEqual(len(ledger.read_text().splitlines()), 1)
            finally:
                queue.close()

    def test_multiple_active_workers_finish_without_starting_remaining_items(self):
        clock = SimpleNamespace(value=0)
        started = []
        lock = threading.Lock()
        barrier = threading.Barrier(2, action=lambda: setattr(clock, 'value', 11), timeout=5)

        def lookup(item, skip_archive, skip_openlibrary):
            with lock:
                started.append(item['id'])
            barrier.wait()
            return {'image': b'finished-after-deadline'}, None

        with patch.object(media, 'time', SimpleNamespace(monotonic=lambda: clock.value)), \
                patch.object(media, 'lookup', side_effect=lookup):
            outcomes = list(media.completed_lookups(self.items(6), workers=2, deadline=10))
        self.assertEqual(sorted(started), [1, 2])
        self.assertEqual(sorted(item['id'] for item, _ in outcomes), [1, 2])
        self.assertTrue(all(future.result()[0]['image'] for _, future in outcomes))

    def test_worker_rechecks_deadline_after_submission_before_lookup(self):
        clock = SimpleNamespace(value=0)

        class DelayedExecutor(ThreadPoolExecutor):
            def submit(self, function, *args, **kwargs):
                def delayed():
                    clock.value = 11
                    return function(*args, **kwargs)
                return super().submit(delayed)

        with patch.object(media, 'time', SimpleNamespace(monotonic=lambda: clock.value)), \
                patch.object(media, 'ThreadPoolExecutor', DelayedExecutor), \
                patch.object(media, 'lookup') as lookup:
            outcomes = list(media.completed_lookups(self.items(), workers=1, deadline=10))
        self.assertEqual(outcomes, [])
        lookup.assert_not_called()

    def test_expired_setup_budget_starts_no_lookup(self):
        with patch.object(media, 'time', SimpleNamespace(monotonic=lambda: 10)), \
                patch.object(media, 'lookup') as lookup:
            self.assertEqual(list(media.completed_lookups(self.items(), workers=2, deadline=10)), [])
        lookup.assert_not_called()

    def test_unlimited_budget_processes_every_item_and_preserves_provider_flags(self):
        with patch.object(media, 'time', SimpleNamespace(monotonic=lambda: 10**12)), \
                patch.object(media, 'lookup', return_value=(None, 'no_match')) as lookup:
            outcomes = list(media.completed_lookups(self.items(), workers=2,
                skip_internet_archive=True, skip_openlibrary=False, deadline=None))
        self.assertEqual(sorted(item['id'] for item, _ in outcomes), [1, 2, 3, 4])
        self.assertTrue(all(call.args[1:] == (True, False) for call in lookup.call_args_list))

    def test_real_worker_error_remains_visible_and_does_not_stop_other_items(self):
        with patch.object(media, 'lookup', side_effect=[ValueError('broken response'), (None, 'no_match')]):
            outcomes = list(media.completed_lookups(self.items(2), workers=1))
        self.assertEqual(len(outcomes), 2)
        with self.assertRaisesRegex(ValueError, 'broken response'):
            outcomes[0][1].result()
        self.assertEqual(outcomes[1][1].result(), (None, 'no_match'))

    def test_cancelled_future_is_not_an_attempt_or_worker_error(self):
        class CancelledExecutor:
            def __init__(self, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def submit(self, *args, **kwargs):
                future = Future()
                future.cancel()
                future.set_running_or_notify_cancel()
                return future

        with patch.object(media, 'ThreadPoolExecutor', CancelledExecutor), \
                patch.object(media, 'lookup') as lookup:
            self.assertEqual(list(media.completed_lookups(self.items(), workers=2)), [])
        lookup.assert_not_called()

    def test_negative_budget_is_rejected_before_database_setup(self):
        with patch.object(media.sys, 'argv', ['covers', '--max-seconds', '-1']), \
                patch.object(media.sys, 'stderr', io.StringIO()) as error, \
                patch.object(media, 'Queue') as queue:
            with self.assertRaises(SystemExit) as exit_error:
                media.main()
        self.assertEqual(exit_error.exception.code, 2)
        self.assertIn('--max-seconds must be zero or positive', error.getvalue())
        queue.assert_not_called()


if __name__ == '__main__':
    unittest.main()
