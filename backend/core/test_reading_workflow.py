"""Saved regressions for a future authorized, isolated test-suite run."""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Edition, LibraryItem, PlanCarryover, PlanItem, Work
from .reading_workflow import allocation_has_history


class DailyReadingAndCarryoverTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            'daily-reading-reader', reading_target_period='month', pages_per_month=100,
            difficulty_aware_planning=False)
        cls.work = Work.objects.create(title='Daily reading fixture', reading_load='leisure')
        cls.edition = Edition.objects.create(work=cls.work, pages=300)
        cls.work.default_edition = cls.edition
        cls.work.save()

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.library = LibraryItem.objects.create(user=self.user, work=self.work, status='reading', current_page=90)

    def allocation(self, **kwargs):
        return PlanItem.objects.create(user=self.user, work=self.work, month=date(2027, 1, 1), pages=100, **kwargs)

    def preview(self, **kwargs):
        return self.client.post('/api/plan/carryover/', {'source_month': '2027-01-01', **kwargs}, format='json')

    def apply(self, result, **kwargs):
        return self.preview(apply=True, preview_token=result.data['preview_token'], **kwargs)

    def test_monthly_reading_is_not_inferred_from_book_page(self):
        allocation = self.allocation()
        result = self.preview()
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data['items'], [])
        self.assertIn('Record pages read', result.data['skipped'][0]['reason'])
        result = self.client.post(f'/api/plan/{allocation.pk}/progress/', {
            'pages_read': 25, 'expected_updated_at': allocation.updated_at.isoformat()}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        self.library.refresh_from_db()
        self.assertEqual(self.library.current_page, 90)
        self.assertEqual(self.preview().data['items'][0]['pages'], 75)

    def test_carryover_preserves_history_and_rejects_replay(self):
        source = self.allocation(pages_read=30)
        result = self.preview()
        applied = self.apply(result)
        self.assertEqual(applied.status_code, 200, applied.data)
        source.refresh_from_db()
        destination = PlanItem.objects.get(user=self.user, month=date(2027, 2, 1))
        self.assertEqual((source.pages, source.pages_read, source.carried_pages), (100, 30, 70))
        self.assertEqual(destination.pages, 70)
        self.assertEqual(destination.reading_basis, source.reading_basis)
        self.assertTrue(allocation_has_history(destination))
        self.assertEqual(PlanCarryover.objects.get().pages, 70)
        self.assertEqual(self.apply(result).status_code, 409)
        self.assertEqual(PlanCarryover.objects.count(), 1)

    def test_preview_is_invalidated_by_changed_progress_or_settings(self):
        source = self.allocation(pages_read=10)
        result = self.preview()
        source.pages_read = 20
        source.save()
        self.assertEqual(self.apply(result).status_code, 409)
        result = self.preview()
        self.user.pages_per_month = 200
        self.user.save()
        self.assertEqual(self.apply(result).status_code, 409)
        self.assertFalse(PlanCarryover.objects.exists())

    def test_capacity_limits_carryover_and_preserves_destination(self):
        source = self.allocation(pages_read=20)
        target = PlanItem.objects.create(user=self.user, work=self.work, month=date(2027, 2, 1),
                                        pages=70, reading_basis=dict(source.reading_basis))
        result = self.preview()
        self.assertEqual(result.data['items'][0]['pages'], 30)
        self.assertEqual(result.data['left_in_source'][0]['pages'], 50)
        self.assertEqual(self.apply(result).status_code, 200)
        target.refresh_from_db()
        source.refresh_from_db()
        self.assertEqual(target.pages, 100)
        self.assertEqual((source.pages, source.carried_pages), (100, 30))

    def test_locks_and_different_editions_are_conflicts(self):
        source = self.allocation(pages_read=0, locked=True)
        self.assertIn('Locked allocation', self.preview().data['skipped'][0]['reason'])
        source.locked = False
        source.save()
        target = PlanItem.objects.create(user=self.user, work=self.work, month=date(2027, 2, 1), pages=20,
                                        reading_basis={**source.reading_basis, 'pages': 400})
        self.assertIn('different saved edition', self.preview().data['skipped'][0]['reason'])
        target.locked = True
        target.save()
        self.assertIn('locked allocation', self.preview().data['skipped'][0]['reason'])
        self.assertFalse(PlanCarryover.objects.exists())

    def test_progress_can_be_corrected_but_cannot_double_count_carried_pages(self):
        source = self.allocation(pages_read=0)
        response = self.client.post(f'/api/plan/{source.pk}/progress/', {
            'pages_read': None, 'expected_updated_at': source.updated_at.isoformat()}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        source.refresh_from_db()
        self.assertFalse(allocation_has_history(source))
        source.pages_read = 40
        source.save()
        self.assertEqual(self.apply(self.preview()).status_code, 200)
        source.refresh_from_db()
        response = self.client.post(f'/api/plan/{source.pk}/progress/', {
            'pages_read': 41, 'expected_updated_at': source.updated_at.isoformat()}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.delete(f'/api/plan/{source.pk}/').status_code, 400)

    def test_other_readers_cannot_read_or_change_private_progress(self):
        source = self.allocation(pages_read=0)
        other = get_user_model().objects.create_user('other-daily-reader')
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get('/api/today/?month=2027-01-01').data['plan_count'], 0)
        response = self.client.post(f'/api/plan/{source.pk}/progress/', {
            'pages_read': 0, 'expected_updated_at': source.updated_at.isoformat()}, format='json')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.preview(plan_ids=[source.pk]).status_code, 400)

    def test_daily_quick_progress_is_stale_safe_and_does_not_change_monthly_totals(self):
        source = self.allocation(pages_read=10)
        payload = {'item': self.library.pk, 'current_page': 100,
                   'expected_updated_at': self.library.updated_at.isoformat()}
        response = self.client.post('/api/today/progress/', payload, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        source.refresh_from_db()
        self.assertEqual(source.pages_read, 10)
        self.assertEqual(self.client.post('/api/today/progress/', payload, format='json').status_code, 409)

    def test_suggestions_preserve_both_carryover_ends_and_original_reading(self):
        source = self.allocation(pages_read=30)
        self.assertEqual(self.apply(self.preview()).status_code, 200)
        destination = PlanItem.objects.get(user=self.user, month=date(2027, 2, 1))
        payload = {'start_month': '2027-01-01', 'months': 3, 'work_ids': [self.work.pk]}
        preview = self.client.post('/api/plan/suggest/', payload, format='json')
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual([row['month'] for row in preview.data['items']], ['2027-03-01'])
        applied = self.client.post('/api/plan/suggest/', {**payload, 'apply': True, 'confirm_replace': True,
            'preview_token': preview.data['preview_token']}, format='json')
        self.assertEqual(applied.status_code, 200, applied.data)
        source.refresh_from_db()
        destination.refresh_from_db()
        self.assertEqual((source.pages, source.pages_read, source.carried_pages), (100, 30, 70))
        self.assertEqual(destination.pages, 70)
        self.assertEqual(PlanCarryover.objects.get().target_plan_id, destination.pk)
        self.assertEqual(PlanItem.objects.count(), 3)

    def test_capacity_and_range_keep_scheduled_read_and_carried_pages_distinct(self):
        source = self.allocation(pages_read=30)
        self.assertEqual(self.apply(self.preview()).status_code, 200)
        capacity = self.client.get('/api/plan/capacity/?start_month=2027-01-01&months=1')
        self.assertEqual(capacity.status_code, 200, capacity.data)
        row = capacity.data[0]
        self.assertEqual((row['physical_pages'], row['pages_read'], row['carried_pages'],
                          row['remaining_pages'], row['used']), (100, 30, 70, 0, 30))
        response = self.client.get('/api/plan/?start_month=2027-01-01&months=1')
        self.assertEqual(response.status_code, 200, response.data)
        rows = response.data['results'] if isinstance(response.data, dict) else response.data
        self.assertEqual([item['id'] for item in rows], [source.pk])
