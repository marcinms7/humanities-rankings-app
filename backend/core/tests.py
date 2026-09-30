from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as ModelValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from backend.domain.planning import month_range, suggest_plan
from backend.domain.scoring import weighted_score
from .models import (Edition, LibraryItem, Person, PlanItem, Ranking, RankingEntry,
                     RankingPreference, ResearchSource, Work)


class APITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user('reader', password='a-unique-reader-password', pages_per_day=10)
        cls.other = get_user_model().objects.create_user('other', password='another-test-password')
        cls.editor = get_user_model().objects.create_user('editor', password='editor-test-password', is_staff=True)
        cls.work = Work.objects.create(title='Test novel', reading_load='classic_literature')
        cls.edition = Edition.objects.create(work=cls.work, pages=500, language='English')
        cls.work.default_edition = cls.edition
        cls.work.save()
        cls.second = Work.objects.create(title='Test philosophy', reading_load='philosophy', field='philosophy')
        cls.short = Edition.objects.create(work=cls.second, pages=100, language='English')
        cls.second.default_edition = cls.short
        cls.second.save()
        cls.ranking = Ranking.objects.create(title='Public template', slug='public-test', is_public=True,
                                            criteria=[{'id': 'depth', 'label': 'Depth'}, {'id': 'clarity', 'label': 'Clarity'}])
        cls.private = Ranking.objects.create(title='Private list', slug='private-test', owner=cls.owner,
                                            origin='personal', status='personal')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_private_library_plan_preferences_and_lists_are_scoped_to_user(self):
        item = LibraryItem.objects.create(user=self.owner, work=self.work, notes='PRIVATE NOTES')
        planned = PlanItem.objects.create(user=self.owner, work=self.work, month=date(2027, 1, 1), pages=100)
        RankingPreference.objects.create(user=self.owner, ranking=self.ranking, weights={'depth': 10})
        self.client.force_authenticate(self.other)
        for url in [f'/api/library/{item.pk}/', f'/api/plan/{planned.pk}/', f'/api/rankings/{self.private.pk}/']:
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.patch(url, {'notes': 'changed'}, format='json').status_code, 404)
        self.assertEqual(self.client.get('/api/library/').data['results'], [])
        self.assertIsNone(self.client.get(f'/api/rankings/{self.ranking.pk}/').data['preference'])
        item.refresh_from_db()
        self.assertEqual(item.notes, 'PRIVATE NOTES')

    def test_anonymous_cannot_write_or_get_private_profile(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f'/api/rankings/{self.ranking.pk}/').status_code, 200)
        self.assertEqual(self.client.post('/api/rankings/', {'title': 'No'}, format='json').status_code, 403)
        self.assertEqual(self.client.get('/api/profile/').status_code, 403)
        self.assertEqual(self.client.get('/api/library/').status_code, 403)

    def test_only_editor_can_create_catalog_entries(self):
        self.assertEqual(self.client.post('/api/works/', {'title': 'New'}, format='json').status_code, 403)
        self.client.force_authenticate(self.editor)
        response = self.client.post('/api/works/', {'title': 'Owner-entered work', 'edition_input': {'pages': 125}}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['edition']['pages'], 125)
        self.assertEqual(response.data['reading_time']['status'], 'provisional')

    def test_invalid_ids_and_library_work_reassignment_are_validation_errors(self):
        for value in ['not-an-id', {}, True, None, -1]:
            response = self.client.post('/api/library/', {'work': value}, format='json')
            self.assertEqual(response.status_code, 400, response.data)
        response = self.client.post('/api/library/', {'work': self.work.pk}, format='json')
        item_id = response.data['id']
        response = self.client.patch(f'/api/library/{item_id}/', {'work': self.second.pk}, format='json')
        self.assertEqual(response.status_code, 400, response.data)

    def test_library_upsert_does_not_duplicate_and_rejects_wrong_edition(self):
        first = self.client.post('/api/library/', {'work': self.work.pk, 'rating': 8}, format='json')
        blocked = self.client.post('/api/library/', {'work': self.work.pk, 'status': 'reading'}, format='json')
        self.assertEqual(blocked.status_code, 400)
        second = self.client.post(f"/api/library/{first.data['id']}/reread/", {}, format='json')
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.data['rating'], 8)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data['id'], second.data['id'])
        for rating in [0, 11, 'excellent']:
            response = self.client.patch(f"/api/library/{first.data['id']}/", {'rating': rating}, format='json')
            self.assertEqual(response.status_code, 400, response.data)
        response = self.client.patch(f"/api/library/{first.data['id']}/", {'rating': None}, format='json')
        self.assertIsNone(response.data['rating'])
        response = self.client.patch(f"/api/library/{first.data['id']}/", {'edition': self.short.pk}, format='json')
        self.assertEqual(response.status_code, 400)
        response = self.client.patch(f"/api/library/{first.data['id']}/", {'current_page': 501}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_library_reading_time_uses_selected_edition_and_progress(self):
        edition = Edition.objects.create(work=self.work, pages=200)
        response = self.client.post('/api/library/', {'work': self.work.pk, 'edition': edition.pk, 'current_page': 100}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['selected_edition']['id'], edition.pk)
        self.assertAlmostEqual(response.data['reading_time']['estimated_hours'], 6)
        self.assertAlmostEqual(response.data['remaining_reading_time']['estimated_hours'], 3)
        response = self.client.patch(f"/api/library/{response.data['id']}/", {'status': 'finished'}, format='json')
        self.assertEqual(response.data['remaining_reading_time']['estimated_hours'], 0)

    def test_ambiguous_author_names_and_collection_cycles_are_rejected(self):
        self.client.force_authenticate(self.editor)
        Person.objects.create(name='Same Name')
        person = Person.objects.create(name='Same Name')
        result = self.client.post('/api/works/', {'title': 'Ambiguous', 'author_names': ['Same Name']}, format='json')
        self.assertEqual(result.status_code, 400)
        result = self.client.post('/api/works/', {'title': 'Explicit', 'author_ids': [person.pk]}, format='json')
        self.assertEqual(result.status_code, 201, result.data)
        self.second.contained_in = self.work
        self.second.save()
        result = self.client.patch(f'/api/works/{self.work.pk}/', {'contained_in': self.second.pk}, format='json')
        self.assertEqual(result.status_code, 400)

    def test_scores_use_personal_overrides_without_mutating_shared_evidence(self):
        entry = RankingEntry.objects.create(ranking=self.ranking, work=self.work, assessments={'depth': 5, 'clarity': 8})
        payload = {'weights': {'depth': 3, 'clarity': 1}, 'overrides': {str(entry.pk): {'depth': 9}}}
        response = self.client.patch(f'/api/rankings/{self.ranking.pk}/preference/', payload, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        response = self.client.post(f'/api/rankings/{self.ranking.pk}/preview/', {}, format='json')
        self.assertAlmostEqual(response.data[0]['score'], 87.5)
        entry.refresh_from_db()
        self.assertEqual(entry.assessments['depth'], 5)
        self.client.force_authenticate(self.other)
        result = self.client.post(f'/api/rankings/{self.ranking.pk}/preview/', {'weights': {'depth': 3, 'clarity': 1}}, format='json')
        self.assertAlmostEqual(result.data[0]['score'], 57.5)

    def test_preferences_reject_other_entries_unknown_criteria_and_non_numeric_scores(self):
        entry = RankingEntry.objects.create(ranking=self.private, work=self.work)
        for payload in [{'weights': {'other': 10}}, {'weights': {'depth': True}}, {'weights': {'depth': -1}},
                        {'overrides': {str(entry.pk): {'depth': 7}}}, {'weights': {'depth': 101}}]:
            result = self.client.patch(f'/api/rankings/{self.ranking.pk}/preference/', payload, format='json')
            self.assertEqual(result.status_code, 400, result.data)

    def test_reading_a_preference_does_not_create_private_records(self):
        before = RankingPreference.objects.count()
        result = self.client.get(f'/api/rankings/{self.ranking.pk}/preference/')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(RankingPreference.objects.count(), before)

    def test_criteria_used_in_personal_overrides_cannot_be_silently_removed(self):
        self.private.criteria = self.ranking.criteria
        self.private.save()
        RankingPreference.objects.create(user=self.owner, ranking=self.private, weights={'depth': 5})
        response = self.client.patch(f'/api/rankings/{self.private.pk}/', {'criteria': []}, format='json')
        self.assertEqual(response.status_code, 400, response.data)

    def test_revision_snapshots_preserve_original_and_reject_stale_edit(self):
        first = self.client.post('/api/rankings/', {'title': 'My new list'}, format='json')
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(first.data['revision'], 1)
        url = f"/api/rankings/{first.data['id']}/"
        result = self.client.patch(url, {'title': 'Updated list', 'expected_revision': 1}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data['revision'], 2)
        result = self.client.patch(url, {'title': 'Stale edit', 'expected_revision': 1}, format='json')
        self.assertEqual(result.status_code, 409)
        ranking = Ranking.objects.get(pk=first.data['id'])
        self.assertEqual(ranking.title, 'Updated list')
        self.assertEqual(ranking.revisions.get(number=1).snapshot['title'], 'My new list')
        self.assertEqual(ranking.revisions.get(number=2).snapshot['title'], 'Updated list')

    def test_list_entry_validation_removal_and_publisher_order(self):
        response = self.client.post(f'/api/rankings/{self.private.pk}/entries/', {'work': self.work.pk}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        entry_id = response.data[0]['id']
        duplicate = self.client.post(f'/api/rankings/{self.private.pk}/entries/', {'work': self.work.pk}, format='json')
        self.assertEqual(duplicate.status_code, 400)
        bad = self.client.delete(f'/api/rankings/{self.private.pk}/entries/', {'entry_id': 'bad'}, format='json')
        self.assertEqual(bad.status_code, 400)
        self.client.post(f'/api/rankings/{self.private.pk}/entries/', {'work': self.second.pk}, format='json')
        self.client.delete(f'/api/rankings/{self.private.pk}/entries/', {'entry_id': entry_id}, format='json')
        self.assertEqual(self.private.entries.get().position, 1)
        source = Ranking.objects.create(title='Publisher', slug='publisher', origin='external', is_public=True)
        published = RankingEntry.objects.create(ranking=source, work=self.work, source_rank=7)
        self.client.force_authenticate(self.editor)
        response = self.client.post(f'/api/rankings/{source.pk}/reorder/', {'entry_ids': [published.pk]}, format='json')
        self.assertEqual(response.status_code, 403)
        result = self.client.post(f'/api/rankings/{source.pk}/copy/', {}, format='json')
        self.assertEqual(result.status_code, 201)
        self.assertEqual(result.data['entry_count'], 1)
        self.assertEqual(Ranking.objects.get(pk=result.data['id']).entries.get().source_rank, 7)

    def test_shared_list_hides_private_assessments_preferences_and_library_notes(self):
        RankingEntry.objects.create(ranking=self.private, work=self.work, rationale='PRIVATE RATIONALE', assessments={'private': 9})
        LibraryItem.objects.create(user=self.owner, work=self.work, notes='PRIVATE LIBRARY NOTE')
        RankingPreference.objects.create(user=self.owner, ranking=self.private, overrides={'personal': 8})
        shared = self.client.post(f'/api/rankings/{self.private.pk}/sharing/', {'enabled': True}, format='json')
        token = shared.data['share_url'].rsplit('/', 1)[-1]
        self.client.force_authenticate(None)
        result = self.client.get(f'/api/shared/{token}/')
        self.assertEqual(result.status_code, 200)
        self.assertNotIn('assessments', result.data['entries'][0])
        self.assertNotIn('rationale', result.data['entries'][0])
        self.assertNotIn('owner', result.data)
        self.assertIsNone(result.data['preference'])
        self.assertNotIn('PRIVATE', str(result.data))
        self.client.force_authenticate(self.owner)
        self.client.post(f'/api/rankings/{self.private.pk}/sharing/', {'enabled': False}, format='json')
        self.assertEqual(self.client.get(f'/api/shared/{token}/').status_code, 404)

    def test_sources_are_attached_counted_and_exposed_per_target(self):
        ResearchSource.objects.create(ranking=self.ranking, source_id='one', underlying_source_id='work-one',
            title='Source fixture', url='https://example.com/source', family='academic', consulted_on=date(2026, 9, 12),
            evidence='Evidence relevant specifically to this test target.', eligible=True)
        ResearchSource.objects.create(ranking=self.private, source_id='two', underlying_source_id='work-two',
            title='Other fixture', url='https://example.com/other', family='review', eligible=False)
        self.assertEqual(self.client.get(f'/api/rankings/{self.ranking.pk}/').data['source_count'], 1)
        self.assertEqual(self.client.get(f'/api/rankings/{self.private.pk}/').data['source_count'], 0)
        source_rows = self.client.get(f'/api/rankings/{self.ranking.pk}/sources/').data['results']
        self.assertEqual([s['source_id'] for s in source_rows], ['one'])

    def test_metadata_edit_and_refresh_request_do_not_reset_research_age(self):
        old = timezone.now() - timedelta(days=200)
        self.ranking.last_researched_at = old
        self.ranking.save()
        self.client.force_authenticate(self.editor)
        response = self.client.patch(f'/api/rankings/{self.ranking.pk}/', {'title': 'New metadata title'}, format='json')
        self.assertEqual(response.status_code, 403, response.data)
        self.ranking.title = 'Editorial metadata correction'
        self.ranking.save()
        self.client.post(f'/api/rankings/{self.ranking.pk}/refresh/', {}, format='json')
        self.ranking.refresh_from_db()
        self.assertEqual(self.ranking.last_researched_at, old)
        self.assertIsNotNone(RankingPreference.objects.get(user=self.editor, ranking=self.ranking).refresh_requested_at)

    def test_refresh_can_be_requested_again_after_completed_research(self):
        RankingPreference.objects.create(user=self.owner, ranking=self.ranking, refresh_requested_at=timezone.now() - timedelta(days=10))
        self.ranking.last_researched_at = timezone.now() - timedelta(days=1)
        self.ranking.save()
        result = self.client.post(f'/api/rankings/{self.ranking.pk}/refresh/', {}, format='json')
        self.assertGreater(result.data['requested_at'], self.ranking.last_researched_at)

    def test_recommendations_require_scores_use_own_overrides_and_exclude_reading(self):
        self.assertEqual(self.client.get('/api/rankings/recommendations/').data['results'], [])
        self.ranking.status = 'published'
        self.ranking.save()
        entry = RankingEntry.objects.create(ranking=self.ranking, work=self.work, assessments={'depth': 5})
        RankingEntry.objects.create(ranking=self.ranking, work=self.second, assessments={'depth': 10})
        RankingPreference.objects.create(user=self.owner, ranking=self.ranking, weights={'depth': 1}, overrides={str(entry.pk): {'depth': 9}})
        LibraryItem.objects.create(user=self.owner, work=self.second, status='reading')
        results = self.client.get('/api/rankings/recommendations/').data['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['book']['id'], self.work.pk)
        self.assertEqual(results[0]['score'], 90)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get('/api/rankings/recommendations/').data['results'], [])

    def test_planner_preview_apply_spans_months_and_preserves_locks(self):
        self.owner.reading_target_period = 'day'
        self.owner.reading_days_per_week = 7
        self.owner.difficulty_aware_planning = False
        self.owner.save()
        LibraryItem.objects.create(user=self.owner, work=self.work)
        locked = PlanItem.objects.create(user=self.owner, work=self.work, month=date(2027, 2, 1), pages=100, locked=True)
        payload = {'start_month': '2027-01-01', 'months': 2, 'work_ids': [self.work.pk]}
        response = self.client.post('/api/plan/suggest/', payload, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['items'], [{'work': self.work.pk, 'month': '2027-01-01', 'pages': 310, 'locked': False}])
        self.assertIn('90 pages', response.data['unscheduled'][0]['reason'])
        preview_token = response.data['preview_token']
        self.assertEqual(PlanItem.objects.count(), 1)
        response = self.client.post('/api/plan/suggest/', {**payload, 'apply': True}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(PlanItem.objects.count(), 1)
        response = self.client.post('/api/plan/suggest/', {**payload, 'apply': True, 'confirm_replace': True,
                                                        'preview_token': preview_token}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        locked.refresh_from_db()
        self.assertEqual(locked.pages, 100)
        self.assertTrue(locked.locked)
        self.assertEqual(PlanItem.objects.count(), 2)

    def test_planner_missing_lengths_and_other_users_books_are_not_guessed(self):
        unknown = Work.objects.create(title='Unknown length')
        LibraryItem.objects.create(user=self.owner, work=unknown)
        response = self.client.post('/api/plan/suggest/', {'start_month': '2027-01-01', 'months': 1, 'work_ids': [unknown.pk]}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['items'], [])
        self.assertIn('page count', response.data['unscheduled'][0]['reason'])
        LibraryItem.objects.create(user=self.other, work=self.second)
        response = self.client.post('/api/plan/suggest/', {'start_month': '2027-01-01', 'months': 1, 'work_ids': [self.second.pk]}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_locked_manual_allocations_require_a_separate_unlock(self):
        LibraryItem.objects.create(user=self.owner, work=self.work)
        planned = PlanItem.objects.create(user=self.owner, work=self.work, month=date(2027, 1, 1), pages=100, locked=True)
        url = f'/api/plan/{planned.pk}/'
        self.assertEqual(self.client.patch(url, {'month': '2027-02-01', 'locked': False}, format='json').status_code, 400)
        self.assertEqual(self.client.delete(url).status_code, 400)
        self.assertEqual(self.client.patch(url, {'locked': False}, format='json').status_code, 200)
        self.assertEqual(self.client.patch(url, {'month': '2027-02-01'}, format='json').status_code, 200)

    def test_planner_validates_dates_allocations_and_explicit_apply_confirmation(self):
        LibraryItem.objects.create(user=self.owner, work=self.work)
        payload = {'start_month': '2027-01-01', 'months': 1, 'work_ids': [self.work.pk]}
        for change in [{'months': True}, {'months': 1.5}, {'months': '2'}, {'work_ids': [{}]},
                       {'start_month': '2027-01-02'}, {'apply': True, 'confirm_replace': 'false'}]:
            response = self.client.post('/api/plan/suggest/', {**payload, **change}, format='json')
            self.assertEqual(response.status_code, 400, response.data)
        for change in [{'month': '2027-01-02'}, {'pages': 0}, {'position': 0}]:
            response = self.client.post('/api/plan/', {'work': self.work.pk, 'month': '2027-01-01', 'pages': 100, **change}, format='json')
            self.assertEqual(response.status_code, 400, response.data)

    def test_export_does_not_include_other_users_data(self):
        LibraryItem.objects.create(user=self.other, work=self.work, notes='OTHER PRIVATE')
        LibraryItem.objects.create(user=self.owner, work=self.second, rating=9, notes='MY NOTE')
        result = self.client.get('/api/export/')
        self.assertEqual(result.status_code, 200)
        import json
        exported = json.loads(b''.join(result.streaming_content))
        self.assertEqual(len(exported['library']), 1)
        self.assertEqual(exported['library'][0]['notes'], 'MY NOTE')
        self.assertEqual(exported['library'][0]['rating'], 9)
        self.assertNotIn('OTHER PRIVATE', str(exported))


@override_settings(DEBUG=True)
class SessionTests(TestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)

    def test_initial_setup_login_and_mutations_require_csrf(self):
        session = self.client.get('/api/session/')
        self.assertTrue(session.json()['setup_required'])
        setup = {'action': 'setup', 'username': 'local-reader', 'password': 'a-unique-bookish-password'}
        self.assertEqual(self.client.post('/api/session/', setup, format='json').status_code, 403)
        token = self.client.cookies['csrftoken'].value
        result = self.client.post('/api/session/', setup, format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(result.status_code, 200, result.content)
        self.assertTrue(result.json()['user']['is_staff'])
        self.assertFalse(result.json()['setup_required'])
        self.assertEqual(self.client.patch('/api/profile/', {'display_name': 'Edited'}, format='json').status_code, 403)
        token = self.client.cookies['csrftoken'].value
        self.assertEqual(self.client.patch('/api/profile/', {'display_name': 'Edited'}, format='json', HTTP_X_CSRFTOKEN=token).status_code, 200)
        self.assertEqual(self.client.post('/api/session/', {'action': 'logout'}, format='json', HTTP_X_CSRFTOKEN=token).status_code, 200)
        login_payload = {'action': 'login', 'username': setup['username'], 'password': setup['password']}
        self.assertEqual(self.client.post('/api/session/', login_payload, format='json').status_code, 403)
        token = self.client.cookies['csrftoken'].value
        self.assertEqual(self.client.post('/api/session/', login_payload, format='json', HTTP_X_CSRFTOKEN=token).status_code, 200)
        token = self.client.cookies['csrftoken'].value
        self.assertEqual(self.client.post('/api/session/', {**setup, 'username': 'second-admin'}, format='json', HTTP_X_CSRFTOKEN=token).status_code, 403)


class DomainTests(SimpleTestCase):
    def test_missing_assessments_do_not_become_zero_or_change_denominator(self):
        self.assertIsNone(weighted_score({'depth': 8}, {'depth': 1, 'clarity': 1})['score'])
        self.assertEqual(weighted_score({'depth': 8}, {'depth': 1, 'clarity': 0})['score'], 80)
        self.assertIsNone(weighted_score({'depth': 8}, {})['score'])
        for weights in [{'depth': -1}, {'depth': float('nan')}, {'depth': True}]:
            with self.assertRaises(ValueError):
                weighted_score({'depth': 8}, weights)

    def test_later_locked_allocations_reserve_pages_and_overload_is_visible(self):
        months = month_range(date(2027, 1, 1), 2)
        result = suggest_plan([{'id': 1, 'remaining_pages': 500}], months, 10,
                              [{'work': 1, 'month': months[1], 'pages': 400}])
        self.assertEqual(result['items'][0]['pages'], 100)
        self.assertEqual(result['unscheduled'], [])
        self.assertIn('120 budget units', result['warnings'][0])
        self.assertEqual(result['capacity_remaining']['2027-02-01'], -120)

    def test_calendar_capacity_uses_actual_month_and_leap_year(self):
        months = month_range(date(2028, 2, 1), 2)
        result = suggest_plan([{'id': 1, 'remaining_pages': 400}], months, 10, [])
        self.assertEqual([row['pages'] for row in result['items']], [290, 110])


class IntegrityTests(TestCase):
    def test_invalid_private_visibility_and_plan_date_fail_in_database(self):
        user = get_user_model().objects.create_user('test')
        work = Work.objects.create(title='Fixture')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Ranking.objects.create(title='Leaky', slug='leaky', origin='personal', owner=user, is_public=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PlanItem.objects.create(user=user, work=work, month=date(2027, 1, 2), pages=50)

    def test_eligible_sources_need_actual_consultation_and_evidence(self):
        ranking = Ranking.objects.create(title='Template', slug='template')
        source = ResearchSource(ranking=ranking, source_id='x', underlying_source_id='x', title='Fixture',
                                url='https://example.com/x', family='academic', eligible=True)
        with self.assertRaises(ModelValidationError):
            source.full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            source.save()
        ranking.status = 'research_complete'
        with self.assertRaises(ModelValidationError):
            ranking.full_clean()
