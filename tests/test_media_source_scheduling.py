import json
import unittest

from research.media_source_scheduling import due_at, normalize, observe


class SourceSchedulingTests(unittest.TestCase):
    def test_both_empty_lookup_count_and_measured_runtime_are_required(self):
        self.assertEqual(observe({}, {'processed': 99}, 600, now=1000)['sample_after'], 0)
        cheap = observe({}, {'processed': 4035}, 9, now=1000)
        self.assertEqual(cheap['sample_after'], 0)
        measured = observe({}, {'processed': 100}, 60, now=1000)
        self.assertEqual(measured, {'empty_records': 100, 'empty_seconds': 60, 'sample_after': 1300})

    def test_empty_batches_accumulate_across_serialization_and_restarts(self):
        record = {}
        for _ in range(19):
            record = observe(record, {'processed': 5, 'covered': 0}, 3, now=1000)
            record = normalize(json.loads(json.dumps(record)))
        self.assertEqual(record['sample_after'], 0)
        record = observe(record, {'processed': 5, 'covered': 0}, 3, now=1000)
        self.assertEqual(record['sample_after'], 1300)

    def test_every_success_restores_ordinary_rotation_including_partial_outage(self):
        old = {'empty_records': 1000, 'empty_seconds': 500, 'sample_after': 1300}
        for stats in ({'processed': 1, 'covered': 1}, {'processed': 1, 'portraits': 1},
                      {'processed': 2, 'covered': 1, 'provider_outage': True, 'provider_errors': 1}):
            with self.subTest(stats=stats):
                self.assertEqual(observe(old, stats, 20, now=1000), normalize({}))
        self.assertEqual(old['sample_after'], 1300)

    def test_provider_errors_and_empty_queue_are_not_evidence_of_poor_yield(self):
        old = {'empty_records': 99, 'empty_seconds': 59, 'sample_after': 0}
        for stats in ({'processed': 20, 'provider_outage': True},
                      {'processed': 20, 'provider_errors': 1}, {'processed': 0},
                      {'processed': 20, 'image_deferred': 20},
                      {'processed': 1, 'provider_status': 'credential_required'}):
            with self.subTest(stats=stats):
                self.assertEqual(observe(old, stats, 500, now=1000), old)

    def test_sample_is_due_after_five_minutes_then_another_empty_sample_waits(self):
        record = observe({}, {'processed': 100}, 60, now=1000)
        self.assertGreater(due_at({'status': 'ready'}, record), 1299)
        self.assertEqual(due_at({'status': 'ready'}, record), 1300)
        record = observe(record, {'processed': 5}, 2, now=1305)
        self.assertEqual(record['sample_after'], 1605)

    def test_provider_cooldowns_and_sampling_waits_are_independent(self):
        record = {'sample_after': 1300}
        self.assertEqual(due_at({'retry_at': 1600}, record, 1500), 1600)
        self.assertEqual(due_at({'retry_at': 1200}, record, 1500), 1500)
        self.assertEqual(due_at({'retry_at': 1200}, record, 1100), 1300)

    def test_invalid_persisted_numbers_cannot_disable_a_source_indefinitely(self):
        self.assertEqual(normalize({'empty_records': '100', 'empty_seconds': float('inf'),
                                    'sample_after': float('nan')}), normalize({}))
        self.assertEqual(normalize(None), normalize({}))
