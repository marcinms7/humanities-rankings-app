import unittest

from backend.domain.reading_time import (
    EstimationPolicy, ReaderProfile, ReadingLoad, ReadingMaterial, estimate_reading_time,
)


class ReadingTimeTests(unittest.TestCase):
    def test_equal_length_different_reading_load(self):
        hours = [estimate_reading_time(ReadingMaterial(page_count=200, load=load)).estimated_hours
                 for load in ReadingLoad]
        self.assertTrue(all(a < b for a, b in zip(hours, hours[1:])))

    def test_shorter_philosophy_can_take_longer_than_leisure(self):
        philosophy = estimate_reading_time(ReadingMaterial(page_count=150, load=ReadingLoad.PHILOSOPHY))
        leisure = estimate_reading_time(ReadingMaterial(page_count=300))
        self.assertGreater(philosophy.estimated_hours, leisure.estimated_hours)

    def test_verified_words_take_precedence_over_layout(self):
        compact = estimate_reading_time(ReadingMaterial(word_count=60000, page_count=150))
        spacious = estimate_reading_time(ReadingMaterial(word_count=60000, page_count=400))
        self.assertEqual(compact.estimated_hours, spacious.estimated_hours)
        self.assertEqual(compact.length_basis, "word_count")

    def test_missing_length_is_explicit(self):
        estimate = estimate_reading_time(ReadingMaterial())
        self.assertEqual(estimate.status, "unavailable")
        self.assertIsNone(estimate.estimated_hours)
        self.assertIsNone(estimate.low_hours)

    def test_personal_rate_and_study_time_change_estimate(self):
        material = ReadingMaterial(word_count=60000)
        baseline = estimate_reading_time(material)
        slower = estimate_reading_time(material, ReaderProfile(baseline_words_per_minute=125))
        study = estimate_reading_time(material, ReaderProfile(study_overhead_fraction=1))
        self.assertEqual(slower.estimated_hours, baseline.estimated_hours * 2)
        self.assertEqual(study.estimated_hours, baseline.estimated_hours * 2)

    def test_override_replaces_category_assumption(self):
        estimate = estimate_reading_time(ReadingMaterial(
            word_count=60000, load=ReadingLoad.PHILOSOPHY, load_multiplier_override=1,
        ))
        baseline = estimate_reading_time(ReadingMaterial(word_count=60000))
        self.assertEqual(estimate.estimated_hours, baseline.estimated_hours)

    def test_provenance_and_range_are_preserved(self):
        estimate = estimate_reading_time(ReadingMaterial(page_count=200))
        self.assertFalse(estimate.calibrated)
        self.assertIn("uncalibrated", estimate.algorithm_version)
        self.assertLess(estimate.low_hours, estimate.estimated_hours)
        self.assertGreater(estimate.high_hours, estimate.estimated_hours)

    def test_zero_length_is_zero(self):
        self.assertEqual(estimate_reading_time(ReadingMaterial(word_count=0)).estimated_hours, 0)

    def test_invalid_inputs_fail(self):
        for material in (ReadingMaterial(page_count=-1), ReadingMaterial(word_count=True),
                         ReadingMaterial(page_count=1.5), ReadingMaterial(load_multiplier_override=float("nan"))):
            with self.subTest(material=material), self.assertRaises(ValueError):
                estimate_reading_time(material)
        for rate in (0, -1, float("inf"), float("nan")):
            with self.subTest(rate=rate), self.assertRaises(ValueError):
                estimate_reading_time(ReadingMaterial(page_count=100), ReaderProfile(rate))
        with self.assertRaises(ValueError):
            estimate_reading_time(ReadingMaterial(page_count=100), policy=EstimationPolicy(range_low_multiplier=2))


if __name__ == "__main__":
    unittest.main()
