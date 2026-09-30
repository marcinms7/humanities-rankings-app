import contextlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from research import complete_catalog_media as runner


class MediaRunnerTests(unittest.TestCase):
    def run_runner(self, counts, worker_code=0):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            summary = root / 'summary.json'
            job = ('fake', ['worker'], summary, None)
            def child(command):
                if command[0] == 'worker':
                    summary.write_text(json.dumps({'processed': 0, 'next_retry': None}))
                    return worker_code
                return 0
            with patch.object(runner, 'RUN', root), patch.object(runner, 'STATE', root), patch.object(runner, 'STOP', root/'stop'), patch.object(runner, 'JOBS', [job]), patch.object(runner, 'exclusive', lambda _: contextlib.nullcontext()), patch.object(runner, 'run_child', side_effect=child), patch.object(runner, 'remaining_report', return_value=counts), patch.object(runner.signal, 'signal'), patch.object(runner.sys, 'argv', ['runner']), patch('builtins.print'):
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
