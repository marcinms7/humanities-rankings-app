"""Reading-workflow regressions for the next authorized isolated suite run."""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .classical_companion import apply_update, plan_preview
from .models import Edition, LibraryItem, PlanItem, Work
from .plan_previews import PlanPreviewConflict
from .reading_basis import capture_plan


class ReadingToolBoundaries(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('reading-tool-reader')
        cls.work = Work.objects.create(title='Reading tool fixture')
        cls.edition = Edition.objects.create(work=cls.work, pages=200)
        cls.work.default_edition = cls.edition
        cls.work.save()

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_shortlist_apply_requires_current_preview_and_cannot_replay_it(self):
        item = LibraryItem.objects.create(user=self.user, work=self.work, read_next_position=1)
        url = '/api/read-next/plan/'
        payload = {'month': '2027-01-01'}
        missing = self.client.post(url, {**payload, 'apply': True}, format='json')
        self.assertEqual(missing.status_code, 409)
        self.assertFalse(PlanItem.objects.exists())
        preview = self.client.post(url, payload, format='json')
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual(preview.data['items'][0]['pages'], 200)

        item.current_page = 50
        item.save()
        stale = self.client.post(url, {**payload, 'apply': True,
                                      'preview_token': preview.data['preview_token']}, format='json')
        self.assertEqual(stale.status_code, 409)
        self.assertFalse(PlanItem.objects.exists())
        preview = self.client.post(url, payload, format='json')
        confirmed = {**payload, 'apply': True, 'preview_token': preview.data['preview_token']}
        applied = self.client.post(url, confirmed, format='json')
        self.assertEqual(applied.status_code, 200, applied.data)
        self.assertEqual(PlanItem.objects.get().pages, 150)
        self.assertEqual(self.client.post(url, confirmed, format='json').status_code, 409)
        self.assertEqual(PlanItem.objects.count(), 1)

    def test_shortlist_preview_is_invalidated_by_a_new_plan_elsewhere(self):
        LibraryItem.objects.create(user=self.user, work=self.work, read_next_position=1)
        payload = {'month': '2027-01-01'}
        preview = self.client.post('/api/read-next/plan/', payload, format='json')
        saved = PlanItem.objects.create(user=self.user, work=self.work, month=date(2027, 2, 1), pages=80, locked=True)
        result = self.client.post('/api/read-next/plan/', {**payload, 'apply': True,
                                  'preview_token': preview.data['preview_token']}, format='json')
        self.assertEqual(result.status_code, 409)
        saved.refresh_from_db()
        self.assertEqual((PlanItem.objects.count(), saved.pages, saved.locked), (1, 80, True))

    def test_discovery_preserves_unknown_selected_length_and_frozen_pages(self):
        unknown = Edition.objects.create(work=self.work, pages=None)
        LibraryItem.objects.create(user=self.user, work=self.work, edition=unknown)
        response = self.client.get('/api/personal-discovery/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(response.data['results'][0]['pages'])
        short = self.client.get('/api/personal-discovery/?max_pages=250')
        self.assertEqual(short.data['count'], 0)

        other = Work.objects.create(title='Known frozen length')
        edition = Edition.objects.create(work=other, pages=120)
        other.default_edition = edition
        other.save()
        LibraryItem.objects.create(user=self.user, work=other)
        edition.pages = 500
        edition.save()
        short = self.client.get('/api/personal-discovery/?max_pages=250')
        self.assertEqual([(row['id'], row['pages']) for row in short.data['results']], [(other.pk, 120)])

    def test_plan_basis_uses_selected_edition_when_legacy_snapshot_is_empty(self):
        selected = Edition.objects.create(work=self.work, pages=80, word_count=48000)
        LibraryItem.objects.bulk_create([LibraryItem(user=self.user, work=self.work, edition=selected)])
        basis = capture_plan(self.work, self.user.pk)
        self.assertEqual((basis['edition_id'], basis['pages']), (selected.pk, 80))
        self.assertEqual(basis['effort_multiplier'], 3)

    def test_classical_plan_preview_rejects_changed_effort_and_preserves_scope(self):
        payload = {'action': 'plan-preview', 'work': self.work.pk, 'month': '2027-01-01',
                   'pages': 30, 'mode': 'selections', 'passages': 'Opening chapter in my edition'}
        preview = plan_preview(payload, self.user)
        self.work.reading_effort_override = 2
        self.work.save()
        state = {}
        with self.assertRaises(PlanPreviewConflict):
            apply_update({**payload, 'action': 'plan-add', 'confirmed': True,
                          'preview_token': preview['preview_token']}, {}, state, self.user)
        self.assertFalse(LibraryItem.objects.exists())
        self.assertFalse(PlanItem.objects.exists())

        preview = plan_preview(payload, self.user)
        apply_update({**payload, 'action': 'plan-add', 'confirmed': True,
                      'preview_token': preview['preview_token']}, {}, state, self.user)
        plan = PlanItem.objects.get()
        self.assertEqual((plan.pages, plan.locked, plan.reading_basis['effort_multiplier']), (30, True, 2))
        self.assertEqual(state['companion']['plans'][str(plan.pk)]['passages'], payload['passages'])
        self.assertEqual(LibraryItem.objects.get().status, 'want_to_read')
