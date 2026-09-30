"""Cross-workflow history safeguards; saved for an authorized isolated suite run."""
from datetime import date
from io import StringIO
import json
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import RequestFactory, TestCase
from rest_framework.test import APIClient

from .classical_companion import plan_preview, saved_plans
from .models import Edition, LibraryItem, PlanCarryover, PlanItem, Work
from .plan_previews import PlanPreviewConflict


class CarryoverIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('carryover-integration', is_staff=True)
        cls.work = Work.objects.create(title='History fixture')
        cls.edition = Edition.objects.create(work=cls.work, pages=300)
        cls.work.default_edition = cls.edition
        cls.work.save()

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_shortlist_can_schedule_a_later_reread_without_replacing_completed_history(self):
        LibraryItem.objects.create(user=self.user, work=self.work, status='reading', read_next_position=1)
        history = PlanItem.objects.create(user=self.user, work=self.work, month=date(2027, 1, 1), pages=100, pages_read=100)
        before = history.reading_basis.copy()
        payload = {'month': '2027-02-01'}
        preview = self.client.post('/api/read-next/plan/', payload, format='json')
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual(len(preview.data['items']), 1)
        result = self.client.post('/api/read-next/plan/', {**payload, 'apply': True,
            'preview_token': preview.data['preview_token']}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        history.refresh_from_db()
        self.assertEqual((history.pages, history.pages_read, history.reading_basis), (100, 100, before))
        self.assertEqual(PlanItem.objects.filter(work=self.work, user=self.user).count(), 2)

    def test_shortlist_preserves_same_month_uniqueness_even_for_completed_history(self):
        LibraryItem.objects.create(user=self.user, work=self.work, read_next_position=1)
        history = PlanItem.objects.create(user=self.user, work=self.work, month=date(2027, 1, 1), pages=100, pages_read=100)
        result = self.client.post('/api/read-next/plan/', {'month': '2027-01-01'}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data['items'], [])
        self.assertIn('this month', result.data['skipped'][0]['reason'])
        history.refresh_from_db()
        self.assertEqual((history.pages, history.pages_read), (100, 100))

    def test_shortlist_confirmation_covers_numeric_progress_even_without_timestamp_change(self):
        history = PlanItem.objects.create(user=self.user, work=self.work, month=date(2027, 1, 1), pages=100, pages_read=10)
        payload = {'month': '2027-02-01'}
        preview = self.client.post('/api/read-next/plan/', payload, format='json')
        PlanItem.objects.filter(pk=history.pk).update(pages_read=20)
        result = self.client.post('/api/read-next/plan/', {**payload, 'apply': True,
            'preview_token': preview.data['preview_token']}, format='json')
        self.assertEqual(result.status_code, 409)

    def test_classical_preview_and_saved_plan_keep_monthly_progress_distinct(self):
        history = PlanItem.objects.create(user=self.user, work=self.work, month=date(2027, 1, 1), pages=100, pages_read=20)
        other = Work.objects.create(title='New classical allocation fixture')
        data = {'action': 'plan-preview', 'work': other.pk, 'month': '2027-01-01', 'pages': 40,
                'mode': 'selections', 'passages': 'Recorded passage scope'}
        preview = plan_preview(data, self.user)
        PlanItem.objects.filter(pk=history.pk).update(pages_read=30)
        with self.assertRaises(PlanPreviewConflict):
            plan_preview({**data, 'action': 'plan-add', 'preview_token': preview['preview_token']}, self.user)
        state = {'companion': {'plans': {str(history.pk): {'work_id': self.work.pk, 'done': True, 'mode': 'selections'}}}}
        rows = saved_plans(state, self.user)
        self.assertEqual((rows[0]['pages_read'], rows[0]['carried_pages'], rows[0]['done']), (30, 0, True))

    def test_edition_transition_preserves_reading_and_incoming_carryover_receipts(self):
        item = LibraryItem.objects.create(user=self.user, work=self.work, current_page=40)
        source = PlanItem.objects.create(user=self.user, work=self.work, month=date(2027, 1, 1), pages=100,
                                         pages_read=40, carried_pages=60)
        target = PlanItem.objects.create(user=self.user, work=self.work, month=date(2027, 2, 1), pages=60)
        receipt = PlanCarryover.objects.create(user=self.user, work=self.work, source_plan=source, target_plan=target,
            source_month=source.month, target_month=target.month, pages=60, reading_basis=source.reading_basis.copy())
        before = (source.reading_basis.copy(), target.reading_basis.copy(), receipt.reading_basis.copy())
        next_edition = Edition.objects.create(work=self.work, pages=600)
        path = f'/api/library/{item.pk}/edition-change/'
        payload = {'edition': next_edition.pk, 'mode': 'proportional'}
        preview = self.client.post(path, payload, format='json')
        result = self.client.post(path, {**payload, 'apply': True, 'token': preview.data['token']}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        source.refresh_from_db(); target.refresh_from_db(); receipt.refresh_from_db()
        self.assertEqual((source.pages_read, source.carried_pages, target.pages, receipt.pages), (40, 60, 60, 60))
        self.assertEqual((source.reading_basis, target.reading_basis, receipt.reading_basis), before)

    def test_admin_cannot_bypass_history_rules_and_backfill_leaves_unknown_history_unresolved(self):
        request = RequestFactory().get('/admin/')
        request.user = self.user
        model_admin = admin.site._registry[PlanItem]
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))
        history = PlanItem.objects.create(user=self.user, work=self.work, month=date(2027, 1, 1), pages=100, pages_read=20)
        PlanItem.objects.filter(pk=history.pk).update(reading_basis={})
        stream = StringIO()
        with patch('backend.core.management.commands.reconcile_maintenance.records', return_value=[]):
            call_command('reconcile_maintenance', apply=True, stdout=stream)
        history.refresh_from_db()
        self.assertEqual(history.reading_basis, {})
        self.assertEqual(json.loads(stream.getvalue())['changes']['plan_history_basis_unresolved'], 1)
