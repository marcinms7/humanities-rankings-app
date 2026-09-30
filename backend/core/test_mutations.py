from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from .models import LibraryItem, MutationReceipt, ReadingAttempt, Work
from .mutations import mutation_guard


class MutationSafetyTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user('mutation-owner', is_staff=True)
        self.other = get_user_model().objects.create_user('mutation-other')
        self.work = Work.objects.create(title='Mutation fixture')
        self.item = LibraryItem.objects.create(user=self.owner, work=self.work, notes='Original')
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def key(self):
        return {'HTTP_IDEMPOTENCY_KEY': str(uuid4())}

    def test_stale_notes_rejected_with_typed_saved_values_and_no_overwrite(self):
        before = self.client.get(f'/api/library/{self.item.pk}/').data
        self.item.notes = 'Saved elsewhere'
        self.item.save()
        response = self.client.patch(f'/api/library/{self.item.pk}/',
            {'notes': 'Local draft', 'expected_version': before['edit_version']}, format='json', **self.key())
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['current']['notes'], 'Saved elsewhere')
        self.assertIsInstance(response.data['current']['id'], int)
        self.item.refresh_from_db()
        self.assertEqual(self.item.notes, 'Saved elsewhere')
        self.assertFalse(MutationReceipt.objects.exists())

    def test_same_key_replays_exact_success_and_does_not_apply_a_later_second_edit(self):
        path = f'/api/library/{self.item.pk}/'
        version = self.client.get(path).data['edit_version']
        headers = self.key()
        first = self.client.patch(path, {'notes': 'One save', 'expected_version': version}, format='json', **headers)
        self.assertEqual(first.status_code, 200)
        self.item.refresh_from_db()
        self.item.notes = 'A subsequent different edit'
        self.item.save()
        second = self.client.patch(path, {'notes': 'One save', 'expected_version': version}, format='json', **headers)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data, first.data)
        self.assertEqual(second['Idempotency-Replayed'], 'true')
        self.item.refresh_from_db()
        self.assertEqual(self.item.notes, 'A subsequent different edit')
        self.assertEqual(MutationReceipt.objects.count(), 1)

    def test_retry_delete_retains_one_history_record(self):
        headers = self.key()
        path = f'/api/library/{self.item.pk}/'
        for _ in range(2):
            self.assertEqual(self.client.delete(path, **headers).status_code, 204)
        self.assertEqual(ReadingAttempt.objects.filter(user=self.owner, work=self.work).count(), 1)

    def test_keys_are_account_scoped_and_never_grant_access(self):
        headers = self.key()
        path = f'/api/library/{self.item.pk}/'
        self.assertEqual(self.client.patch(path, {'notes': 'Owner secret'}, format='json', **headers).status_code, 200)
        self.client.force_authenticate(self.other)
        response = self.client.patch(path, {'notes': 'Owner secret'}, format='json', **headers)
        self.assertEqual(response.status_code, 404)
        self.assertNotIn('Owner secret', str(response.data))

    def test_reusing_key_for_different_payload_is_rejected(self):
        headers = self.key()
        path = f'/api/library/{self.item.pk}/'
        self.assertEqual(self.client.patch(path, {'notes': 'First'}, format='json', **headers).status_code, 200)
        self.assertEqual(self.client.patch(path, {'notes': 'Changed'}, format='json', **headers).status_code, 400)
        self.item.refresh_from_db()
        self.assertEqual(self.item.notes, 'First')

    def test_catalog_version_detects_changed_author_relationship(self):
        from .models import Person
        path = f'/api/works/{self.work.pk}/'
        version = self.client.get(path).data['edit_version']
        self.work.authors.add(Person.objects.create(name='Recorded contributor'))
        response = self.client.patch(path, {'title': 'Stale title', 'expected_version': version}, format='json', **self.key())
        self.assertEqual(response.status_code, 409)
        self.work.refresh_from_db()
        self.assertEqual(self.work.title, 'Mutation fixture')

    def test_non_object_catalog_edits_return_validation_error(self):
        path = f'/api/works/{self.work.pk}/'
        for data in (['Invalid fields'], 'Invalid fields'):
            with self.subTest(data=data):
                response = self.client.patch(path, data, format='json', **self.key())
                self.assertEqual(response.status_code, 400)
        self.work.refresh_from_db()
        self.assertEqual(self.work.title, 'Mutation fixture')
        self.assertFalse(MutationReceipt.objects.exists())

    def test_if_match_precondition_is_part_of_retry_identity(self):
        path = f'/api/library/{self.item.pk}/'
        version = self.client.get(path).data['edit_version']
        headers = {**self.key(), 'HTTP_IF_MATCH': f'"{version}"'}
        first = self.client.patch(path, {'notes': 'Header checked'}, format='json', **headers)
        self.assertEqual(first.status_code, 200)
        replay = self.client.patch(path, {'notes': 'Header checked'}, format='json', **headers)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.data, first.data)
        self.assertEqual(replay['Idempotency-Replayed'], 'true')
        changed = {**headers, 'HTTP_IF_MATCH': f'"{first.data["edit_version"]}"'}
        rejected = self.client.patch(path, {'notes': 'Header checked'}, format='json', **changed)
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(MutationReceipt.objects.count(), 1)
        self.item.refresh_from_db()
        self.assertEqual(self.item.notes, 'Header checked')

    def test_function_guard_rolls_back_returned_error_responses(self):
        @api_view(['POST'])
        @mutation_guard
        def failed_write(request):
            item = LibraryItem.objects.get(pk=self.item.pk)
            item.notes = 'This change must roll back'
            item.save()
            return Response({'detail': 'The change could not be completed.'}, status=422)

        for headers in ({}, self.key()):
            with self.subTest(keyed=bool(headers)):
                request = APIRequestFactory().post('/mutation-failure/', {}, format='json', **headers)
                force_authenticate(request, user=self.owner)
                response = failed_write(request)
                self.assertEqual(response.status_code, 422)
                self.item.refresh_from_db()
                self.assertEqual(self.item.notes, 'Original')
                self.assertFalse(MutationReceipt.objects.exists())
