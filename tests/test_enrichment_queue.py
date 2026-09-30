import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research import enrichment_queue as enrichment


class EnrichmentQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state_patch = patch.object(enrichment, 'STATE', self.root / 'state')
        self.state_patch.start()
        self.addCleanup(self.state_patch.stop)
        self.ledger = self.root / 'outcomes.jsonl'
        self.queue = enrichment.Queue('test', self.ledger)
        self.addCleanup(lambda: self.queue.close())
        self.item = {'id': 1, 'title': 'A Book', 'authors': ['A. Writer']}

    def finish(self, status):
        with self.ledger.open('a') as audit:
            self.queue.finish(self.item, {'work_id': 1, 'status': status}, audit)

    def test_unresolved_rows_do_not_starve_new_records(self):
        self.assertTrue(self.queue.due(self.item, 'v1'))
        self.finish('no_safe_cover')
        self.assertFalse(self.queue.due(self.item, 'v1'))
        new = {**self.item, 'id': 2}
        self.assertTrue(self.queue.due(new, 'v1'))
        self.assertLess(self.queue.priority(new), self.queue.priority(self.item))
        self.assertTrue(self.queue.due({**self.item, 'title': 'Corrected title'}, 'v1'))

    def test_transient_failures_back_off_and_stop_after_three(self):
        with patch.object(enrichment.time, 'time', return_value=1000):
            self.assertTrue(self.queue.due(self.item, 'v1'))
            self.finish('provider_error')
            self.assertFalse(self.queue.due(self.item, 'v1'))
        with patch.object(enrichment.time, 'time', return_value=1060):
            self.assertTrue(self.queue.due(self.item, 'v1'))
            self.finish('provider_error')
        with patch.object(enrichment.time, 'time', return_value=1180):
            self.assertTrue(self.queue.due(self.item, 'v1'))
            self.finish('provider_error')
        with patch.object(enrichment.time, 'time', return_value=999999):
            self.assertFalse(self.queue.due(self.item, 'v1'))
        self.assertEqual(self.queue.summary()['states'], {'retry_exhausted': 1})

    def test_rotation_preserves_audit_bytes_and_rebuild_state(self):
        self.queue.due(self.item, 'v1')
        self.finish('covered')
        original = self.ledger.read_bytes()
        enrichment.rotate(self.ledger, threshold=1)
        manifest = json.loads((self.root / 'archives/manifest.jsonl').read_text())
        self.assertEqual(manifest['sha256'], hashlib.sha256(original).hexdigest())
        with gzip.open(self.root / 'archives' / manifest['archive'], 'rb') as saved:
            self.assertEqual(saved.read(), original)
        rebuilt = enrichment.Queue('rebuilt', self.ledger)
        try:
            self.assertFalse(rebuilt.due(self.item, 'v1'))
            self.assertEqual(rebuilt.summary()['states'], {'complete': 1})
        finally:
            rebuilt.close()

    def test_overlapping_worker_lock_is_rejected(self):
        with enrichment.exclusive('worker'):
            with self.assertRaises(SystemExit):
                with enrichment.exclusive('worker'):
                    self.fail('Duplicate worker acquired the same lock')
