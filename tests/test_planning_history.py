"""Reserved reading history cases saved for the next authorized suite run."""
from datetime import date
from unittest import TestCase

from backend.domain.planning import suggest_plan


class PreservedPlanningHistoryTests(TestCase):
    def setUp(self):
        self.january = date(2027, 1, 1)
        self.february = date(2027, 2, 1)
        self.months = [self.january, self.february]
        self.budgets = {month: 100 for month in self.months}

    def test_read_pages_use_capacity_but_only_unread_pages_reserve_book_remainder(self):
        result = suggest_plan([{'id': 1, 'remaining_pages': 90}], self.months, 25,
            [{'work': 1, 'month': self.january, 'pages': 30, 'remaining_pages': 10}],
            month_budgets=self.budgets)
        self.assertEqual(result['items'], [{'work': 1, 'month': '2027-02-01', 'pages': 80, 'locked': False}])
        self.assertEqual(result['capacity_remaining']['2027-01-01'], 70)
        self.assertEqual(result['unscheduled'], [])

    def test_fully_carried_source_preserves_slot_without_consuming_capacity(self):
        result = suggest_plan([{'id': 1, 'remaining_pages': 50}, {'id': 2, 'remaining_pages': 80}],
            self.months, 25, [], month_budgets=self.budgets,
            blocked_pairs={(1, self.january)})
        self.assertEqual(result['items'], [
            {'work': 1, 'month': '2027-02-01', 'pages': 50, 'locked': False},
            {'work': 2, 'month': '2027-01-01', 'pages': 80, 'locked': False},
        ])
        self.assertEqual(result['capacity_remaining']['2027-01-01'], 20)

    def test_remaining_and_committed_pages_both_preserve_effort_units(self):
        result = suggest_plan([{'id': 1, 'remaining_pages': 50, 'effort_per_page': 2}],
            self.months, 25, [{'work': 1, 'month': self.january, 'pages': 40,
                              'remaining_pages': 15, 'effort_per_page': 2}], month_budgets=self.budgets)
        self.assertEqual(result['items'][0]['pages'], 35)
        self.assertEqual(result['capacity_remaining'], {'2027-01-01': 20, '2027-02-01': 30})

    def test_invalid_unread_reservation_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unread reserved pages'):
            suggest_plan([], self.months, 25,
                         [{'work': 1, 'month': self.january, 'pages': 20, 'remaining_pages': 21}],
                         month_budgets=self.budgets)
