"""Private export and book allocation cases; saved for an authorized suite run."""
import io
import json
import zipfile
from datetime import date

from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django.test import TestCase
from rest_framework.test import APIClient

from .models import (ClassicalStudyProfile, Edition, LibraryItem, Person, PlanItem, StudyRecord,
                     Ranking, RankingEntry, RankingRevision, ReadingAdjustment,
                     SavedDiscoveryFilter, Work)
from .private_export import build_private_export


class PrivateWorkflowBoundaries(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('complete-export-reader', reading_target_period='month', pages_per_month=1000)
        cls.other = get_user_model().objects.create_user('unrelated-export-reader')
        cls.author = Person.objects.create(name='Export author', portrait='portraits/export-reference.png')
        cls.work = Work.objects.create(title='Exported reading', reading_effort_override=2)
        cls.work.authors.add(cls.author)
        cls.first = Edition.objects.create(work=cls.work, pages=200, cover='covers/export-reference.png', image_attribution='Fixture credit')
        cls.second = Edition.objects.create(work=cls.work, pages=400)
        cls.work.default_edition = cls.first
        cls.work.save()

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_export_includes_study_and_revisions_but_excludes_other_accounts_and_secrets(self):
        LibraryItem.objects.create(user=self.user, work=self.work, notes='My current note', shelves=['Owned'])
        LibraryItem.objects.create(user=self.other, work=self.work, notes='UNRELATED PRIVATE NOTE')
        study = {'modules': {'module-id': {'notes': 'My module note'}},
                 'learning': {'essays': {'essay-id': {'draft': 'Current essay', 'history': [{'draft': 'Earlier essay'}]}}},
                 'companion': {'commonplaces': {'note-id': {'work': self.work.pk, 'reflection': 'My commonplace'}}},
                 'reading_desk': {'note': {'passage:translation': {'notes': 'My passage note', 'history': [{'notes': 'Earlier passage note'}]}}}}
        ClassicalStudyProfile.objects.create(user=self.user, state=study)
        ClassicalStudyProfile.objects.create(user=self.other, state={'notes': 'UNRELATED STUDY NOTE'})
        SavedDiscoveryFilter.objects.create(user=self.user, name='My saved combination', filters={'max_pages': 250})
        personal = Ranking.objects.create(owner=self.user, origin='personal', title='My personal list', slug='complete-export-personal', sharing_enabled=True)
        RankingEntry.objects.create(ranking=personal, work=self.work)
        RankingRevision.objects.create(ranking=personal, number=1, snapshot={'entries': [{'work_id': self.work.pk, 'rationale': 'Prior rationale'}]})
        result = self.client.get('/api/export/')
        self.assertEqual(result.status_code, 200)
        text = b''.join(result.streaming_content).decode()
        for expected in ['My current note', 'My module note', 'Earlier essay', 'My commonplace', 'Earlier passage note', 'My saved combination', 'Prior rationale']:
            self.assertIn(expected, text)
        for forbidden in ['UNRELATED PRIVATE NOTE', 'UNRELATED STUDY NOTE', str(personal.share_token), '"password"']:
            self.assertNotIn(forbidden, text)
        self.assertEqual(result['Cache-Control'], 'private, no-store')

    def test_export_resolves_historical_edition_snapshots_and_serializes_media_paths(self):
        LibraryItem.objects.create(user=self.user, work=self.work, edition=self.second)
        historical = Edition.objects.create(work=self.work, pages=180, cover='covers/historical.png', is_archived=True)
        ReadingAdjustment.objects.create(user=self.user, work=self.work, method='manual',
            before={'reading_basis': {'edition_id': historical.pk, 'pages': 180}},
            after={'reading_basis': {'edition_id': self.second.pk, 'pages': 400}})
        data = build_private_export(self.user)
        exported = json.loads(json.dumps(data, cls=DjangoJSONEncoder))
        self.assertEqual({row['id'] for row in exported['references']['editions']}, {self.first.pk, self.second.pk, historical.pk})
        self.assertEqual(exported['references']['people'][0]['portrait'], 'portraits/export-reference.png')
        row = next(row for row in exported['references']['editions'] if row['id'] == self.first.pk)
        self.assertEqual(row['cover'], 'covers/export-reference.png')

    def test_export_reconstructs_normalized_study_and_retains_individual_records(self):
        ClassicalStudyProfile.objects.create(user=self.user, state={'companion': {'commonplaces': {}}})
        StudyRecord.objects.create(user=self.user, record_key='f' * 64,
            path=['companion', 'commonplaces', 'saved-note'], value={'work': self.work.pk, 'reflection': 'Preserved normalized note'})
        data = build_private_export(self.user)
        self.assertEqual(data['study_profiles'][0]['state']['companion']['commonplaces']['saved-note']['reflection'], 'Preserved normalized note')
        self.assertEqual(data['study_records'][0]['value']['reflection'], 'Preserved normalized note')
        self.assertIn(self.work.pk, {row['id'] for row in data['references']['works']})

    def test_zip_is_downloadable_and_contains_the_complete_structured_export(self):
        LibraryItem.objects.create(user=self.user, work=self.work, notes='A portable note')
        result = self.client.get('/api/export/?download=zip')
        self.assertEqual(result.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(b''.join(result.streaming_content))) as archive:
            self.assertTrue({'private-data.json', 'study-state.json', 'reading-notes.md', 'README.md'}.issubset(archive.namelist()))
            exported = json.loads(archive.read('private-data.json'))
            self.assertEqual(exported['library'][0]['notes'], 'A portable note')
            self.assertIn('A portable note', archive.read('reading-notes.md').decode())
            self.assertIn('automatic restore', archive.read('README.md').decode())
        self.assertEqual(self.client.get('/api/export/?download=unknown').status_code, 400)

    def test_allocation_uses_frozen_edition_and_requires_a_current_preview(self):
        item = LibraryItem.objects.create(user=self.user, work=self.work, current_page=20, status='reading')
        self.first.pages = 500
        self.first.save()
        payload = {'work': self.work.pk, 'month': '2027-02-01', 'pages': 50, 'locked': True}
        missing = self.client.post('/api/reading-allocation/', {**payload, 'apply': True}, format='json')
        self.assertEqual(missing.status_code, 409)
        self.assertFalse(PlanItem.objects.exists())
        preview = self.client.post('/api/reading-allocation/', payload, format='json')
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual((preview.data['remaining_pages'], preview.data['effort_pages']), (180, 100))
        item.current_page = 30
        item.save()
        stale = self.client.post('/api/reading-allocation/', {**payload, 'apply': True, 'preview_token': preview.data['preview_token']}, format='json')
        self.assertEqual(stale.status_code, 409)
        preview = self.client.post('/api/reading-allocation/', payload, format='json')
        applied = self.client.post('/api/reading-allocation/', {**payload, 'apply': True, 'preview_token': preview.data['preview_token']}, format='json')
        self.assertEqual(applied.status_code, 200, applied.data)
        plan = PlanItem.objects.get()
        self.assertEqual((plan.pages, plan.locked, plan.reading_basis['pages']), (50, True, 200))

    def test_allocation_previews_include_other_months_and_detect_their_changes(self):
        LibraryItem.objects.create(user=self.user, work=self.work)
        other = PlanItem.objects.create(user=self.user, work=self.work, month=date(2027, 3, 1), pages=50, locked=True)
        payload = {'work': self.work.pk, 'month': '2027-02-01', 'pages': 50}
        preview = self.client.post('/api/reading-allocation/', payload, format='json')
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertTrue(preview.data['warnings'])
        self.assertEqual(preview.data['other_allocations'][0]['remaining_pages'], 50)
        other.pages = 60
        other.save()
        stale = self.client.post('/api/reading-allocation/', {**payload, 'apply': True, 'preview_token': preview.data['preview_token']}, format='json')
        self.assertEqual(stale.status_code, 409)
        other.refresh_from_db()
        self.assertEqual((PlanItem.objects.count(), other.pages, other.locked), (1, 60, True))

    def test_cannot_schedule_another_users_book_or_an_exhausted_attempt(self):
        item = LibraryItem.objects.create(user=self.other, work=self.work)
        payload = {'work': self.work.pk, 'month': '2027-02-01', 'pages': None}
        self.assertEqual(self.client.post('/api/reading-allocation/', payload, format='json').status_code, 404)
        self.client.force_authenticate(self.other)
        item.current_page = 200
        item.save()
        self.assertEqual(self.client.post('/api/reading-allocation/', payload, format='json').status_code, 400)
        self.assertFalse(PlanItem.objects.exists())
