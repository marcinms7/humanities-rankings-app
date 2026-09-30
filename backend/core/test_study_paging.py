from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from .classical_education import content
from .models import ClassicalStudyProfile
from .study_store import load_state, save_state, browser_state, record_key, records_page, StudyRecordsPageContract


class StudyPagingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('study-pages', password='test-only-pass')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.profile = ClassicalStudyProfile.objects.create(user=self.user)
        self.revision = content()['revision']
        self.state = {'modules': {'iliad': {'notes': 'module-private', self.revision: {'light': True}}},
            'companion': {'commonplaces': {f'n{i}': {'reference': f'Passage {i}', 'reflection': 'private-' + str(i), 'revisit': '2000-01-01'} for i in range(30)}},
            'learning': {'essays': {'essay-one': {'title': 'Current essay', 'revision': 2, 'history': [{'revision': i, 'draft': 'old-private'} for i in range(30)]}},
                'recall': {'iliad:question': {'due': '2000-01-01', 'attempts': [{'answer': 'private-recall', 'saved_at': '2000-01-01', 'interval': 3}]}},
                'sessions': [{'id': f's{i}', 'module': 'iliad', 'minutes': 30, 'reflection': 'private-session', 'passage': '', 'saved_at': '2000-01-01'} for i in range(30)]}}
        save_state(self.profile, self.state)

    def test_summary_omits_writing_but_preserves_progress_and_due_counts(self):
        response = self.client.get('/api/classical-education/?part=summary')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'private-', response.content)
        self.assertNotIn(b'module-private', response.content)
        self.assertIn('iliad', response.data['completed'])
        self.assertEqual(len(response.data['learning_summary']['commonplace_due']), 30)
        self.assertNotIn('commonplaces', response.data['state'].get('companion', {}))

    def test_family_reads_are_bounded_and_do_not_include_other_families(self):
        page = records_page(self.profile, 'companion')
        contract = StudyRecordsPageContract(data=page)
        self.assertTrue(contract.is_valid(), contract.errors)
        self.assertEqual(len(page['results']), 24)
        self.assertEqual(page['next_page'], 2)
        self.assertEqual(len(records_page(self.profile, 'companion', 2)['results']), 6)
        self.assertTrue(all(row['path'][:2] == ['companion', 'commonplaces'] for row in page['results']))

    def test_current_essay_body_omits_history_with_accurate_count(self):
        page = records_page(self.profile, 'essays')
        value = page['results'][0]['value']
        self.assertEqual(value['history'], [])
        self.assertEqual(value['_history_count'], 30)
        self.assertEqual(value['revision'], 2)
        history = records_page(self.profile, 'essays', history_key=value['_record_key'])
        self.assertEqual(history['count'], 30)
        self.assertEqual(len(history['results']), 12)
        self.assertEqual(history['results'][0]['revision'], 29)

    def test_recall_attempt_count_remains_available_without_attempt_text(self):
        value = records_page(self.profile, 'recall')['results'][0]['value']
        self.assertEqual(value['attempts'], [])
        self.assertEqual(value['_attempts_count'], 1)

    def test_snapshot_conflict_prevents_mixing_pages(self):
        response = self.client.get('/api/classical-education/', {'part': 'records', 'family': 'companion', 'snapshot': 'earlier'})
        self.assertEqual(response.status_code, 409)

    def test_other_account_cannot_read_owner_records(self):
        other = get_user_model().objects.create_user('other-study', password='test-only-pass')
        self.client.force_authenticate(other)
        response = self.client.get('/api/classical-education/?part=records&family=essays')
        self.assertEqual(response.status_code, 403)

    def test_full_export_adapter_retains_every_revision(self):
        self.assertEqual(load_state(self.profile), self.state)
        page = records_page(self.profile, 'sessions')
        self.assertEqual(page['count'], 30)
        self.assertEqual(len(page['results']), 24)
        self.assertEqual(page['results'][0]['path'], ['learning', 'sessions', '29'])
        self.assertEqual(load_state(self.profile), self.state)

    def test_browser_delta_projection_keeps_current_values_and_revision_counts(self):
        projected = browser_state(self.state)
        self.assertEqual(projected['learning']['essays']['essay-one']['_history_count'], 30)
        self.assertEqual(projected['learning']['essays']['essay-one']['history'], [])
        self.assertEqual(len(projected['learning']['sessions']), 30)
        self.assertEqual(record_key(['learning', 'essays', 'essay-one']), projected['learning']['essays']['essay-one']['_record_key'])
