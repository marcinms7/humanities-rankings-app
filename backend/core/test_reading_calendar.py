"""Private calendar effects, confirmation boundaries, and preserved allocations."""
from datetime import date
from types import SimpleNamespace
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient
from backend.domain.reading_capacity import reading_budget
from .models import Edition, LibraryItem, PlanItem, ReadingCalendar, Work


class CalendarBudgetTests(SimpleTestCase):
    def test_overlap_union_cross_month_and_leap_year(self):
        user = SimpleNamespace(reading_target_period='month', pages_per_month=290,
                               reading_days_per_week=4, difficulty_aware_planning=True)
        adjustments = {'pauses': [{'start': '2028-01-30', 'end': '2028-02-03'},
                                  {'start': '2028-02-02', 'end': '2028-02-05'}],
                       'month_targets': [{'month': '2028-02-01', 'percent': 50}]}
        result = reading_budget(user, date(2028, 2, 1), adjustments)
        self.assertEqual((result['budget'], result['paused_days'], result['calendar_days']), (120, 5, 29))
        self.assertEqual(result['base_budget'], 290)
        self.assertEqual(user.pages_per_month, 290)

    def test_day_and_week_targets_with_full_pause_are_zero(self):
        user = SimpleNamespace(reading_target_period='week', pages_per_week=70, pages_per_day=20,
                               reading_days_per_week=4, difficulty_aware_planning=False)
        pause = {'pauses': [{'start': '2027-10-01', 'end': '2027-10-31'}]}
        for mode in ['week', 'day']:
            user.reading_target_period = mode
            result = reading_budget(user, date(2027, 10, 1), pause)
            self.assertEqual((result['budget'], result['per_reading_day']), (0, 0))


class CalendarAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('calendar-reader', reading_target_period='month',
                                                       pages_per_month=100, difficulty_aware_planning=False)
        cls.other = get_user_model().objects.create_user('other-calendar-reader')
        cls.work = Work.objects.create(title='Calendar fixture', reading_load='leisure')
        cls.edition = Edition.objects.create(work=cls.work, pages=200)
        cls.work.default_edition = cls.edition
        cls.work.save()
        cls.library = LibraryItem.objects.create(user=cls.user, work=cls.work, read_next_position=1)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.get(pk=self.user.pk))
        self.payload = {'revision': 0, 'pauses': [], 'month_targets': [{'month': '2027-10-01', 'percent': 50}],
                        'start_month': '2027-10-01', 'months': 1}

    def preview(self):
        response = self.client.post('/api/reading-calendar/', self.payload, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def save(self):
        preview = self.preview()
        response = self.client.post('/api/reading-calendar/', {**self.payload, 'apply': True,
                                   'preview_token': preview['preview_token']}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_preview_is_read_only_and_apply_preserves_locks_history_and_baseline(self):
        plan = PlanItem.objects.create(user=self.user, work=self.work, month=date(2027, 10, 1),
                                       pages=80, pages_read=20, locked=True)
        before = PlanItem.objects.values().get(pk=plan.pk)
        preview = self.preview()
        self.assertFalse(ReadingCalendar.objects.exists())
        month = preview['months'][0]
        self.assertEqual((month['before_budget'], month['after_budget'], month['over_capacity']), (100, 50, 30))
        self.assertTrue(month['allocations'][0]['has_history'])
        self.save()
        self.assertEqual(PlanItem.objects.values().get(pk=plan.pk), before)
        self.user.refresh_from_db()
        self.assertEqual(self.user.pages_per_month, 100)
        self.assertEqual(ReadingCalendar.objects.get(user=self.user).revision, 1)

    def test_confirms_only_previewed_revision_and_settings(self):
        preview = self.preview()
        self.user.pages_per_month = 200
        self.user.save(update_fields=['pages_per_month'])
        response = self.client.post('/api/reading-calendar/', {**self.payload, 'apply': True,
                                  'preview_token': preview['preview_token']}, format='json')
        self.assertEqual(response.status_code, 409)
        self.assertFalse(ReadingCalendar.objects.exists())
        self.save()
        self.assertEqual(self.client.post('/api/reading-calendar/', self.payload, format='json').status_code, 409)

    def test_changed_plan_invalidates_calendar_preview(self):
        preview = self.preview()
        PlanItem.objects.create(user=self.user, work=self.work, month=date(2027, 10, 1), pages=80)
        response = self.client.post('/api/reading-calendar/', {**self.payload, 'apply': True,
                                   'preview_token': preview['preview_token']}, format='json')
        self.assertEqual(response.status_code, 409)
        self.assertFalse(ReadingCalendar.objects.exists())

    def test_personal_calendar_is_owned(self):
        self.save()
        self.client.force_authenticate(self.other)
        result = self.client.get('/api/reading-calendar/')
        self.assertEqual(result.data, {'revision': 0, 'pauses': [], 'month_targets': []})
        self.client.force_authenticate(None)
        self.assertIn(self.client.get('/api/reading-calendar/').status_code, [401, 403])

    def test_zero_month_skips_new_suggestions_and_shortlist(self):
        self.payload['month_targets'][0]['percent'] = 0
        self.save()
        payload = {'start_month': '2027-10-01', 'months': 1, 'work_ids': [self.work.pk]}
        response = self.client.post('/api/plan/suggest/', payload, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['items'], [])
        self.assertEqual(response.data['capacity_remaining']['2027-10-01'], 0)
        self.client.force_authenticate(get_user_model().objects.get(pk=self.user.pk))
        shortlist = self.client.post('/api/read-next/plan/', {'month': '2027-10-01'}, format='json')
        self.assertEqual(shortlist.status_code, 200, shortlist.data)
        self.assertEqual(shortlist.data['items'], [])
        self.assertEqual(shortlist.data['capacity']['budget'], 0)

    def test_calendar_change_invalidates_existing_book_preview(self):
        payload = {'work': self.work.pk, 'month': '2027-10-01', 'pages': 25}
        preview = self.client.post('/api/reading-allocation/', payload, format='json')
        self.assertEqual(preview.status_code, 200, preview.data)
        self.save()
        stale = self.client.post('/api/reading-allocation/', {**payload, 'apply': True,
                                 'preview_token': preview.data['preview_token']}, format='json')
        self.assertEqual(stale.status_code, 409)
        self.assertFalse(PlanItem.objects.exists())

    def test_remove_exception_restores_target_and_duplicate_months_reject(self):
        self.save()
        self.payload.update(revision=1, month_targets=[])
        preview = self.preview()['months'][0]
        self.assertEqual((preview['before_budget'], preview['after_budget']), (50, 100))
        self.payload['month_targets'] = [{'month': '2027-10-01', 'percent': 0}] * 2
        self.assertEqual(self.client.post('/api/reading-calendar/', self.payload, format='json').status_code, 400)

    def test_cross_month_pause_previews_both_months_outside_display_range(self):
        self.payload['pauses'] = [{'start': '2027-11-29', 'end': '2027-12-03', 'label': 'Away'}]
        months = {row['month']: row for row in self.preview()['months']}
        self.assertEqual(months['2027-11-01']['paused_days'], 2)
        self.assertEqual(months['2027-12-01']['paused_days'], 3)

    def test_monthly_capacity_loads_calendar_only_once(self):
        from .reading_calendar import reading_budget as saved_budget
        user = get_user_model().objects.get(pk=self.user.pk)
        with self.assertNumQueries(1):
            for month in range(1, 13):
                self.assertEqual(saved_budget(user, date(2027, month, 1))['budget'], 100)

    def test_shortlist_and_classical_tokens_become_stale_after_calendar_change(self):
        from .classical_companion import plan_preview
        from .plan_previews import PlanPreviewConflict
        shortlist_payload = {'month': '2027-10-01'}
        shortlist = self.client.post('/api/read-next/plan/', shortlist_payload, format='json')
        classical_payload = {'action': 'plan-preview', 'work': self.work.pk, 'month': '2027-10-01',
                             'pages': 25, 'mode': 'selections', 'passages': 'Opening pages'}
        classical = plan_preview(classical_payload, get_user_model().objects.get(pk=self.user.pk))
        self.save()
        result = self.client.post('/api/read-next/plan/', {**shortlist_payload, 'apply': True,
                                  'preview_token': shortlist.data['preview_token']}, format='json')
        self.assertEqual(result.status_code, 409)
        with self.assertRaises(PlanPreviewConflict):
            plan_preview({**classical_payload, 'action': 'plan-add', 'confirmed': True,
                          'preview_token': classical['preview_token']}, get_user_model().objects.get(pk=self.user.pk))
        self.assertFalse(PlanItem.objects.exists())

    def test_zero_month_keeps_locked_reservations_and_reports_over_capacity(self):
        plan = PlanItem.objects.create(user=self.user, work=self.work, month=date(2027, 10, 1), pages=40, locked=True)
        self.payload['month_targets'][0]['percent'] = 0
        self.save()
        response = self.client.post('/api/plan/suggest/', {'start_month': '2027-10-01', 'months': 1,
                                  'work_ids': [self.work.pk]}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['items'], [])
        self.assertEqual(response.data['capacity_remaining']['2027-10-01'], -40)
        self.assertTrue(response.data['warnings'])
        plan.refresh_from_db()
        self.assertEqual((plan.pages, plan.locked), (40, True))

    def test_zero_target_stops_automatic_carryover_without_moving_source_history(self):
        plan = PlanItem.objects.create(user=self.user, work=self.work, month=date(2027, 9, 1), pages=80, pages_read=20)
        self.payload['month_targets'][0]['percent'] = 0
        self.save()
        response = self.client.post('/api/plan/carryover/', {'source_month': '2027-09-01'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['items'], [])
        self.assertEqual(response.data['left_in_source'][0]['pages'], 60)
        self.assertEqual(response.data['capacity']['budget'], 0)
        plan.refresh_from_db()
        self.assertEqual((plan.pages, plan.pages_read, plan.carried_pages), (80, 20, 0))
