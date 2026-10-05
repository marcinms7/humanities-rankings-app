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

    def test_provider_outages_defer_without_spending_match_attempts(self):
        with patch.object(enrichment.time, 'time', return_value=1000):
            self.queue.due(self.item, 'v1')
            with self.ledger.open('a') as audit:
                self.queue.finish(self.item, {'work_id': 1, 'status': 'provider_error',
                    'provider_outage': True, 'retry_after': 4000}, audit)
            self.assertFalse(self.queue.due(self.item, 'v1'))
        with patch.object(enrichment.time, 'time', return_value=4000):
            self.assertTrue(self.queue.due(self.item, 'v1'))
        attempts, state = self.queue.db.execute('SELECT attempts,state FROM attempts').fetchone()
        self.assertEqual((attempts, state), (0, 'provider_wait'))
        self.assertEqual(self.queue.summary()['next_retry'], 4000)
        rebuilt = enrichment.Queue('outage-rebuild', self.ledger)
        try:
            self.assertEqual(rebuilt.db.execute('SELECT attempts,state FROM attempts').fetchone(), (0, 'provider_wait'))
        finally:
            rebuilt.close()

    def test_ranked_priority_never_starves_unattempted_records_behind_retries(self):
        ranked = {**self.item, 'priority': 3}
        other = {**self.item, 'id': 2}
        self.queue.due(ranked, 'v1')
        self.queue.due(other, 'v1')
        self.assertLess(self.queue.priority(ranked), self.queue.priority(other))
        self.finish('image_error')
        self.assertLess(self.queue.priority(other), self.queue.priority(ranked))

    def test_zero_cost_provider_retries_follow_fresh_items_and_rotate(self):
        first = {**self.item, 'priority': 10}
        older = {**self.item, 'id': 2}
        fresh = {**self.item, 'id': 3}
        for item in (first, older, fresh):
            self.queue.due(item, 'v1')
        with self.ledger.open('a') as audit:
            for item, attempted_at in ((older, 1000), (first, 2000)):
                with patch.object(enrichment.time, 'time', return_value=attempted_at):
                    self.queue.finish(item, {'work_id': item['id'], 'status': 'provider_deferred',
                                      'provider_outage': True, 'retry_after': 3000}, audit)
        self.assertEqual([item['id'] for item in sorted([first, older, fresh], key=self.queue.priority)], [3, 2, 1])
        self.assertEqual(self.queue.db.execute('SELECT SUM(attempts) FROM attempts').fetchone()[0], 0)

    def test_identity_and_edition_inputs_reopen_only_changed_lookup(self):
        item = {**self.item, 'edition_id': 3, 'provider_identifiers': {'openlibrary': ['/works/OL1W']}}
        self.queue.due(item, 'v1')
        self.finish('no_safe_match')
        self.assertFalse(self.queue.due(item, 'v1'))
        self.assertTrue(self.queue.due({**item, 'edition_id': 4}, 'v1'))

    def test_old_exhausted_http_outages_recover_but_ambiguous_matches_remain(self):
        old = self.root / 'legacy.jsonl'
        old.write_text(''.join(json.dumps({'work_id': identity, 'status': status, 'error': error}) + '\n'
            for identity, status, error in [(7, 'provider_error', 'HTTP Error 429: Too Many Requests'),
                                            (8, 'openlibrary_ambiguous', '')] for _ in range(3)))
        recovered = enrichment.Queue('legacy-outages', old)
        try:
            states = dict(recovered.db.execute('SELECT work_id,state FROM attempts'))
            self.assertEqual(states, {7: 'provider_wait', 8: 'unresolved'})
        finally:
            recovered.close()

    def test_summary_ignores_stale_rows_outside_current_worker_selection(self):
        from research.media_provider_health import outcome
        missing = {**self.item, 'id': 2}
        self.queue.due(self.item, 'v1')
        self.queue.due(missing, 'v1')
        self.queue.db.execute("UPDATE attempts SET state='retryable', attempts=1, next_retry=900 WHERE work_id=1")
        self.queue.db.execute("UPDATE attempts SET state='provider_wait', next_retry=4000 WHERE work_id=2")
        self.queue.db.commit()
        restarted = enrichment.Queue('test', self.ledger)
        try:
            with patch.object(enrichment.time, 'time', return_value=1000):
                self.assertFalse(restarted.due(missing, 'v1'))
                summary = restarted.summary()
                self.assertEqual(summary, {'states': {'provider_wait': 1}, 'next_retry': 4000})
                self.assertEqual(outcome({}, {'processed': 0, **summary}, now=1000)['status'], 'waiting')
            self.assertEqual(restarted.db.execute('SELECT count(*) FROM attempts').fetchone()[0], 2)
        finally:
            restarted.close()

    def test_empty_selection_has_no_retry_from_historical_rows(self):
        self.queue.due(self.item, 'v1')
        self.finish('provider_error')
        restarted = enrichment.Queue('test', self.ledger)
        try:
            self.assertEqual(restarted.summary(), {'states': {}, 'next_retry': None})
        finally:
            restarted.close()

    def test_publisher_and_portrait_evidence_changes_reopen_but_priority_does_not(self):
        item = {**self.item, 'publishers': ['Old Publisher'], 'ranked': True, 'priority': 3}
        self.queue.due(item, 'v1')
        self.finish('no_safe_match')
        self.assertFalse(self.queue.due({**item, 'priority': 17}, 'v1'))
        for key, value in [('publishers', ['New Publisher']), ('works', ['Another Book']),
                           ('work_aliases', {'Another Book': ['Reviewed Alternative Title']}),
                           ('biography', 'Corrected biography'), ('verified_identity_urls', ['https://example.org/author']),
                           ('birth_year', 1800), ('death_year', 1870)]:
            item = {**item, key: value}
            self.assertTrue(self.queue.due(item, 'v1'), key)
            self.finish('no_safe_match')
            self.assertFalse(self.queue.due(item, 'v1'), key)
