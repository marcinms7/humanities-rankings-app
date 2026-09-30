"""Deferred regressions; run only in an explicitly authorized isolated suite."""
from copy import deepcopy
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from PIL import Image

from .models import ClassicalStudyProfile, StudyRecord
from .study_store import load_state, save_state, state_changes
from .thumbnails import source_file, thumbnail_url


class StudyStorageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('study-storage-reader')
        self.profile = ClassicalStudyProfile.objects.create(user=self.user)

    def test_storage_round_trip_preserves_unknown_keys_and_every_revision(self):
        state = {'path': 'rigorous', 'modules': {'m1': {'notes': 'Saved note', 'v1': {'rigorous': True}}},
                 'activities': {'v1': {'a1': {'response': 'Answer'}}},
                 'learning': {'essays': {'e1': {'draft': 'Current', 'history': [{'draft': 'Earlier'}]}},
                              'sessions': [{'reflection': 'Yesterday'}]},
                 'companion': {'commonplaces': {'c1': {'reflection': 'Thought'}}, 'plans': {'42': {'done': False}}},
                 'reading_desk': {'note': {'p:t': {'notes': 'Close reading', 'history': [{'notes': 'Earlier'}]}}},
                 'unknown_future_field': {'preserve': True}}
        original = deepcopy(state)
        save_state(self.profile, state)
        self.profile.refresh_from_db()
        self.assertEqual(load_state(self.profile), original)
        self.assertEqual(state, original)
        self.assertEqual(self.profile.state['companion']['plans'], original['companion']['plans'])
        self.assertEqual(self.profile.state['learning']['essays'], {})
        self.assertEqual(StudyRecord.objects.filter(user=self.user).count(), 5)

    def test_edit_changes_only_one_record_and_keeps_other_reader_private(self):
        state = {'modules': {'a': {'notes': 'one'}, 'b': {'notes': 'two'}}}
        save_state(self.profile, state)
        original = {row.record_key: (row.updated_at, row.revision) for row in StudyRecord.objects.all()}
        state['modules']['a']['notes'] = 'updated'
        save_state(self.profile, state)
        for row in StudyRecord.objects.all():
            self.assertEqual(row.revision, 2 if row.path[-1] == 'a' else original[row.record_key][1])
            if row.path[-1] == 'b':
                self.assertEqual(row.updated_at, original[row.record_key][0])
        other = get_user_model().objects.create_user('other-study-storage-reader')
        self.assertEqual(load_state(ClassicalStudyProfile.objects.create(user=other)), {})

    def test_delta_contains_only_changed_note_without_unrelated_history(self):
        before = {'modules': {'a': {'notes': 'old'}}, 'learning': {'essays': {'e': {'draft': 'PRIVATE_UNRELATED'}}}}
        after = deepcopy(before)
        after['modules']['a']['notes'] = 'new'
        self.assertEqual(state_changes(before, after), [{'path': ['modules', 'a', 'notes'], 'value': 'new'}])

    def test_state_endpoint_omits_curriculum_and_stale_save_is_rejected(self):
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.get('/api/classical-education/?part=state')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('content', response.data)
        response = client.patch('/api/classical-education/?part=delta', {'pace': 6, 'expected_updated_at': None}, format='json')
        self.assertEqual(response.status_code, 409)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.state, {})


class ThumbnailTests(TestCase):
    def test_thumbnail_is_bounded_preserves_original_and_rejects_traversal(self):
        from pathlib import Path
        from django.http import Http404
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory, BASE_DIR=Path(directory)):
            root = Path(directory)
            (root / 'covers').mkdir()
            original = root / 'covers/book.png'
            Image.new('RGB', (600, 900), 'white').save(original)
            original_bytes = original.read_bytes()
            response = self.client.get(thumbnail_url('covers/book.png', 96))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'image/webp')
            response.close()
            self.assertEqual(original.read_bytes(), original_bytes)
            for name in ['/etc/passwd', 'covers/../../private.png', '../covers/book.png']:
                with self.assertRaises(Http404):
                    source_file(name)
            self.assertEqual(self.client.get('/media-preview/999/covers/book.png').status_code, 404)
