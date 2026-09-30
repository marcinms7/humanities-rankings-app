import json
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .api_contracts import contract_registry
from .management.commands.export_frontend_contracts import schema_object
from .models import Edition, LibraryItem, Work


def assert_shape(test, shape, value, path='response'):
    kind = shape['kind']
    if kind == 'unknown' or (value is None and shape.get('nullable')):
        return
    if kind in {'object', 'record'}:
        test.assertIsInstance(value, dict, path)
        for name in shape.get('required', []):
            test.assertIn(name, value, path)
        for name, item in value.items():
            child = shape['item'] if kind == 'record' else shape['fields'].get(name)
            if child:
                assert_shape(test, child, item, path+'.'+name)
    elif kind == 'array':
        test.assertIsInstance(value, list, path)
        for item in value:
            assert_shape(test, shape['item'], item, path+'[]')
    elif kind == 'enum':
        test.assertIn(value, shape['values'], path)
    else:
        test.assertTrue(type(value) in {'string': (str,), 'number': (int, float), 'boolean': (bool,)}[kind], path)


class APIContractTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('contract-reader', is_staff=True)
        self.work = Work.objects.create(title='Contract fixture')
        edition = Edition.objects.create(work=self.work, pages=180)
        self.work.default_edition = edition
        self.work.save()
        self.item = LibraryItem.objects.create(user=self.user, work=self.work)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def contract(self, name, response):
        self.assertEqual(response.status_code, 200, str(response.data))
        value = json.loads(response.content)
        assert_shape(self, schema_object(contract_registry()[name]()), value)

    def test_actual_detail_and_summary_read_types(self):
        self.contract('ApiWork', self.client.get(f'/api/works/{self.work.pk}/'))
        self.contract('ApiLibrary', self.client.get(f'/api/library/{self.item.pk}/'))
        row = self.client.get('/api/library/?compact=1').json()['results'][0]
        assert_shape(self, schema_object(contract_registry()['ApiLibrarySummary']()), row)

    def test_real_plan_preview_matches_generated_contract(self):
        response = self.client.post('/api/plan/suggest/', {'start_month': '2027-01-01', 'months': 1,
            'work_ids': [self.work.pk], 'apply': False}, format='json')
        self.contract('ApiPlanSuggestion', response)

    def test_book_allocation_preview_contract(self):
        response = self.client.post('/api/reading-allocation/', {'work': self.work.pk, 'month': '2027-01-01',
            'pages': 60, 'apply': False}, format='json')
        self.contract('ApiAllocationPreview', response)

    def test_recommendation_envelopes_match_runtime_contracts(self):
        self.contract('ApiRecommendationBundle', self.client.get('/api/recommendations/'))
        self.contract('ApiRecommendationPreferences', self.client.get('/api/recommendations/preferences/'))
        self.contract('ApiRecommendationFeedbackPage', self.client.get('/api/recommendations/feedback/'))

    def test_actual_study_delta_matches_generated_contract(self):
        response = self.client.patch('/api/classical-education/?part=delta', {'pace': 6, 'expected_updated_at': None}, format='json')
        self.contract('ApiStudyDelta', response)

    def test_calendar_preview_application_and_private_export_contracts(self):
        from .private_export import build_private_export
        path = '/api/reading-calendar/'
        self.contract('ApiCalendarState', self.client.get(path))
        command = {'revision': 0, 'start_month': '2028-02-01', 'months': 1,
                   'pauses': [{'start': '2028-02-28', 'end': '2028-02-29', 'label': 'Break'}],
                   'month_targets': [{'month': '2028-02-01', 'percent': 50}], 'apply': False}
        preview = self.client.post(path, command, format='json')
        self.contract('ApiCalendarPreview', preview)
        applied = self.client.post(path, {**command, 'apply': True, 'preview_token': preview.data['preview_token']}, format='json')
        self.contract('ApiCalendarPreview', applied)
        self.assertTrue(applied.data['applied'])
        exported = build_private_export(self.user)
        self.assertEqual(len(exported['reading_calendar']), 1)
        self.assertEqual(exported['reading_calendar'][0]['pauses'][0]['label'], 'Break')
        self.assertEqual(exported['reading_calendar'][0]['month_targets'][0]['percent'], 50)
