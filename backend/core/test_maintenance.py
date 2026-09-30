"""Regression cases for future authorized suite runs; isolated Django test DB."""
from datetime import date
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from .models import Edition, LibraryItem, PlanItem, Ranking, RankingEntry, ReadingAdjustment, ReadingAttempt, Work


class MaintenanceBoundaries(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('maintenance-reader', is_staff=True)
        cls.work = Work.objects.create(title='Edition transition fixture')
        cls.first = Edition.objects.create(work=cls.work, pages=200)
        cls.second = Edition.objects.create(work=cls.work, pages=400)
        cls.work.default_edition = cls.first; cls.work.save()
        cls.shared = Ranking.objects.create(title='Shared fixture', slug='maintenance-shared', is_public=True)

    def setUp(self):
        self.client = APIClient(); self.client.force_authenticate(self.user)

    def test_staff_reader_cannot_modify_shared_but_can_edit_own_copy(self):
        entry = RankingEntry.objects.create(ranking=self.shared, work=self.work)
        url = f'/api/rankings/{self.shared.pk}/'
        for method, suffix, payload in [('patch', '', {'title': 'Forbidden'}),
                ('post', 'entries/', {'work': self.work.pk}),
                ('delete', 'entries/', {'entry_id': entry.pk}),
                ('post', 'reorder/', {'entry_ids': [entry.pk]}), ('delete', '', {})]:
            self.assertEqual(getattr(self.client, method)(url + suffix, payload, format='json').status_code, 403)
        copied = self.client.post(url + 'copy/', {}, format='json')
        self.assertEqual(copied.status_code, 201)
        self.assertEqual(self.client.patch(f"/api/rankings/{copied.data['id']}/", {'title': 'My order'}, format='json').status_code, 200)

    def test_edition_preview_is_stale_safe_and_keeps_history_and_locked_pages(self):
        item = LibraryItem.objects.create(user=self.user, work=self.work, current_page=50, status='reading')
        plan = PlanItem.objects.create(user=self.user, work=self.work, month=date(2027, 1, 1), pages=75, locked=True)
        url = f'/api/library/{item.pk}/edition-change/'
        payload = {'edition': self.second.pk, 'mode': 'proportional'}
        preview = self.client.post(url, payload, format='json')
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual(preview.data['page'], 100)
        self.assertEqual(self.client.patch(f'/api/library/{item.pk}/', {'edition': self.second.pk}, format='json').status_code, 400)
        item.current_page = 60; item.save()
        stale = self.client.post(url, {**payload, 'apply': True, 'token': preview.data['token']}, format='json')
        self.assertEqual(stale.status_code, 409)
        preview = self.client.post(url, payload, format='json')
        applied = self.client.post(url, {**payload, 'apply': True, 'token': preview.data['token']}, format='json')
        self.assertEqual(applied.status_code, 200, applied.data)
        item.refresh_from_db(); plan.refresh_from_db()
        self.assertEqual((item.current_page, item.status, plan.pages, plan.reading_basis['pages']), (120, 'reading', 75, 200))
        self.assertEqual(ReadingAttempt.objects.count(), 0)
        self.assertEqual(ReadingAdjustment.objects.count(), 1)

    def test_catalog_length_changes_do_not_rewrite_private_snapshot(self):
        item = LibraryItem.objects.create(user=self.user, work=self.work, current_page=50)
        self.first.pages = 500; self.first.save()
        row = self.client.get(f'/api/library/{item.pk}/').data
        self.assertEqual(row['selected_edition']['pages'], 200)
        self.assertTrue(row['basis_needs_review'])

    def test_duration_basis_keeps_word_count_separate_from_page_provenance(self):
        self.first.word_count = 60000
        self.first.pages_basis = 'estimated_across_editions'
        self.first.save()
        result = self.client.get(f'/api/works/{self.work.pk}/').data['reading_time']
        self.assertEqual(result['length_basis'], 'word_count')
        self.assertEqual(result['page_count_basis'], 'estimated_across_editions')

    def test_copy_and_share_keep_country_provenance_but_hide_private_data(self):
        self.shared.scope = {'group_by': 'country', 'source_record_count': 123}; self.shared.save()
        grouping = {'country': 'Example', 'local_rank': 1, 'section_index': 0}
        RankingEntry.objects.create(ranking=self.shared, work=self.work, groupings=[grouping])
        result = self.client.post(f'/api/rankings/{self.shared.pk}/copy/', {}, format='json')
        copy = Ranking.objects.get(pk=result.data['id'])
        self.assertEqual(copy.entries.get().groupings, [grouping])
        self.assertNotIn('source_record_count', copy.scope)
        self.client.post(f'/api/rankings/{copy.pk}/sharing/', {'enabled': True}, format='json')
        copy.refresh_from_db()
        self.client.force_authenticate(None)
        shared = self.client.get(f'/api/shared/{copy.share_token}/').data
        self.assertEqual(shared['scope']['group_by'], 'country')
        self.assertEqual(shared['entries'][0]['groupings'], [grouping])
        self.assertNotIn('rationale', shared['entries'][0])

    def test_archived_editions_cannot_be_selected_but_existing_library_remains_editable(self):
        self.second.is_archived = True
        self.second.save()
        response = self.client.post('/api/library/', {'work': self.work.pk, 'edition': self.second.pk}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(LibraryItem.objects.exists())
        item = LibraryItem.objects.create(user=self.user, work=self.work, edition=self.second)
        response = self.client.patch(f'/api/library/{item.pk}/', {'notes': 'Keep my saved edition'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['selected_edition']['id'], self.second.pk)

    def test_archived_works_cannot_be_added_but_private_references_are_retained(self):
        self.work.is_archived = True
        self.work.save()
        response = self.client.post('/api/library/', {'work': self.work.pk}, format='json')
        self.assertEqual(response.status_code, 400)
        personal = Ranking.objects.create(title='Personal', slug='archived-target-test', origin='personal', owner=self.user)
        response = self.client.post(f'/api/rankings/{personal.pk}/entries/', {'work': self.work.pk}, format='json')
        self.assertEqual(response.status_code, 400)
        item = LibraryItem.objects.create(user=self.user, work=self.work)
        response = self.client.patch(f'/api/library/{item.pk}/', {'current_page': 20}, format='json')
        self.assertEqual(response.status_code, 200, response.data)

    def test_archived_default_edition_cannot_be_selected_implicitly(self):
        self.first.is_archived = True
        self.first.save()
        response = self.client.post('/api/library/', {'work': self.work.pk}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(LibraryItem.objects.exists())
        response = self.client.post('/api/library/', {'work': self.work.pk, 'edition': self.second.pk}, format='json')
        self.assertEqual(response.status_code, 201, response.data)

    def test_archiving_shared_personal_list_hides_its_link(self):
        personal = Ranking.objects.create(title='Shared personal', slug='archived-share-test', origin='personal',
                                          owner=self.user, sharing_enabled=True)
        self.client.force_authenticate(None)
        url = f'/api/shared/{personal.share_token}/'
        self.assertEqual(self.client.get(url).status_code, 200)
        personal.is_archived = True
        personal.save()
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_changed_allocations_invalidate_preview_without_replacing_saved_plan(self):
        LibraryItem.objects.create(user=self.user, work=self.work)
        allocation = PlanItem.objects.create(user=self.user, work=self.work, month=date(2027, 1, 1), pages=25)
        payload = {'start_month': '2027-01-01', 'months': 1, 'work_ids': [self.work.pk]}
        preview = self.client.post('/api/plan/suggest/', payload, format='json')
        self.assertEqual(preview.status_code, 200, preview.data)
        allocation.pages = 30
        allocation.save()
        confirmation = {**payload, 'apply': True, 'confirm_replace': True, 'preview_token': preview.data['preview_token']}
        stale = self.client.post('/api/plan/suggest/', confirmation, format='json')
        self.assertEqual(stale.status_code, 409, stale.data)
        allocation.refresh_from_db()
        self.assertEqual(allocation.pages, 30)
        self.assertEqual(PlanItem.objects.count(), 1)

    def test_changed_library_progress_or_missing_token_requires_fresh_preview(self):
        item = LibraryItem.objects.create(user=self.user, work=self.work)
        payload = {'start_month': '2027-01-01', 'months': 1, 'work_ids': [self.work.pk]}
        preview = self.client.post('/api/plan/suggest/', payload, format='json')
        self.assertEqual(preview.status_code, 200, preview.data)
        item.current_page = 50
        item.save()
        confirmation = {**payload, 'apply': True, 'confirm_replace': True}
        for token in [None, preview.data['preview_token']]:
            stale = self.client.post('/api/plan/suggest/', {**confirmation, 'preview_token': token}, format='json')
            self.assertEqual(stale.status_code, 409, stale.data)
        self.assertFalse(PlanItem.objects.exists())
        fresh = self.client.post('/api/plan/suggest/', payload, format='json')
        applied = self.client.post('/api/plan/suggest/', {**confirmation, 'preview_token': fresh.data['preview_token']}, format='json')
        self.assertEqual(applied.status_code, 200, applied.data)
        self.assertEqual(applied.data['items'], fresh.data['items'])

    def test_plan_preview_tracks_each_books_effort_even_when_totals_do_not_change(self):
        self.user.reading_target_period = 'month'
        self.user.pages_per_month = 1000
        self.user.save()
        self.work.reading_effort_override = 1
        self.work.save()
        other = Work.objects.create(title='Second effort fixture', reading_effort_override=2)
        other.default_edition = Edition.objects.create(work=other, pages=200)
        other.save()
        for work in [self.work, other]:
            LibraryItem.objects.create(user=self.user, work=work)
        payload = {'start_month': '2027-01-01', 'months': 1, 'work_ids': [self.work.pk, other.pk]}
        before = self.client.post('/api/plan/suggest/', payload, format='json')
        Work.objects.filter(pk__in=payload['work_ids']).update(reading_effort_override=1.5)
        after = self.client.post('/api/plan/suggest/', payload, format='json')
        self.assertEqual(before.data['items'], after.data['items'])
        self.assertEqual(before.data['capacity_remaining'], after.data['capacity_remaining'])
        response = self.client.post('/api/plan/suggest/', {**payload, 'apply': True, 'confirm_replace': True,
                                  'preview_token': before.data['preview_token']}, format='json')
        self.assertEqual(response.status_code, 409, response.data)
        self.assertFalse(PlanItem.objects.exists())
