"""Selected-book actions must remain additive, owned and atomic."""
from datetime import date
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from .api_contracts import contract_registry
from .management.commands.export_frontend_contracts import schema_object
from .models import Edition, LibraryItem, MutationReceipt, Ranking, RankingEntry, RankingRevision, ReadingAttempt, Work
from .mutations import edit_version
from .test_api_contracts import assert_shape


class BulkBookActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('bulk-reader')
        cls.other = get_user_model().objects.create_user('bulk-other')
        cls.works = [Work.objects.create(title=f'Bulk fixture {index}') for index in range(4)]
        cls.edition = Edition.objects.create(work=cls.works[0], pages=150)
        cls.works[0].default_edition = cls.edition
        cls.works[0].save()
        cls.saved = LibraryItem.objects.create(user=cls.user, work=cls.works[0], edition=cls.edition,
            status='finished', current_page=150, rating=8, notes='Preserve private notes',
            started_on=date(2026, 1, 1), finished_on=date(2026, 2, 1), shelves=['Owned'], personal_tags=['Keep'])
        cls.other_saved = LibraryItem.objects.create(user=cls.other, work=cls.works[1], notes='Other reader')
        cls.personal = Ranking.objects.create(title='Private list', slug='bulk-private', origin='personal',
            owner=cls.user, status='personal')
        cls.entry = RankingEntry.objects.create(ranking=cls.personal, work=cls.works[0], position=7,
            source_rank=3, rationale='Preserve rationale', assessments={'value': 4})
        cls.foreign = Ranking.objects.create(title='Other private list', slug='bulk-foreign', origin='personal',
            owner=cls.other, status='personal')
        cls.shared = Ranking.objects.create(title='Shared source', slug='bulk-shared', origin='external', is_public=True)
        cls.shared_entry = RankingEntry.objects.create(ranking=cls.shared, work=cls.works[1], position=1, source_rank=2)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def post(self, action='library', ids=None, headers=None, **values):
        return self.client.post('/api/library/bulk/', {
            'action': action, 'work_ids': ids if ids is not None else [work.pk for work in self.works], **values,
        }, format='json', **(headers or {}))

    def test_library_deduplicates_and_preserves_saved_private_fields(self):
        before = LibraryItem.objects.filter(pk=self.saved.pk).values().get()
        foreign = LibraryItem.objects.filter(pk=self.other_saved.pk).values().get()
        response = self.post(ids=[self.works[0].pk, self.works[1].pk, self.works[1].pk])
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['selected_count'], 2)
        self.assertEqual(response.data['added_to_library'], 1)
        self.assertEqual(response.data['unchanged_count'], 1)
        self.assertEqual(LibraryItem.objects.filter(pk=self.saved.pk).values().get(), before)
        self.assertEqual(LibraryItem.objects.filter(pk=self.other_saved.pk).values().get(), foreign)
        self.assertFalse(ReadingAttempt.objects.exists())
        added = LibraryItem.objects.get(user=self.user, work=self.works[1])
        self.assertEqual(added.status, 'want_to_read')
        self.assertEqual(added.current_page, 0)
        self.assertIn('captured_at', added.reading_basis)
        assert_shape(self, schema_object(contract_registry()['ApiBulkBookActionResult']()), response.json())

    def test_new_library_row_captures_current_default_edition(self):
        self.client.force_authenticate(self.other)
        response = self.post(ids=[self.works[0].pk])
        self.assertEqual(response.status_code, 200)
        row = LibraryItem.objects.get(user=self.other, work=self.works[0])
        self.assertEqual(row.reading_basis['edition_id'], self.edition.pk)
        self.assertEqual(row.reading_basis['pages'], 150)
        self.assertIsNone(row.edition_id)

    def test_read_next_appends_in_selection_order_without_reordering_existing_queue(self):
        LibraryItem.objects.filter(pk=self.saved.pk).update(read_next_position=9)
        before = LibraryItem.objects.filter(pk=self.saved.pk).values().get()
        ids = [self.works[3].pk, self.works[0].pk, self.works[2].pk, self.works[3].pk]
        response = self.post('read_next', ids)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['added_to_read_next'], 2)
        self.assertEqual(response.data['added_to_library'], 2)
        self.assertEqual(list(LibraryItem.objects.filter(user=self.user).order_by('read_next_position').values_list(
            'work_id', 'read_next_position')), [(self.works[0].pk, 9), (self.works[3].pk, 10), (self.works[2].pk, 11)])
        self.assertEqual(LibraryItem.objects.filter(pk=self.saved.pk).values().get(), before)

    def test_read_next_preserves_completed_attempt_without_implicitly_starting_reread(self):
        version = edit_version(self.saved)
        response = self.post('read_next', [self.works[0].pk])
        self.assertEqual(response.status_code, 200)
        self.saved.refresh_from_db()
        self.assertEqual(self.saved.status, 'finished')
        self.assertEqual(self.saved.rating, 8)
        self.assertEqual(self.saved.current_page, 150)
        self.assertEqual(self.saved.notes, 'Preserve private notes')
        self.assertNotEqual(edit_version(self.saved), version)
        self.assertFalse(ReadingAttempt.objects.exists())

    def test_private_list_keeps_positions_and_saves_both_revisions(self):
        before = RankingEntry.objects.filter(pk=self.entry.pk).values().get()
        shared = RankingEntry.objects.filter(pk=self.shared_entry.pk).values().get()
        response = self.post('personal_list', [self.works[2].pk, self.works[0].pk, self.works[1].pk],
            ranking_id=self.personal.pk, expected_revision=1)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['added_to_list'], 2)
        self.assertEqual(response.data['revision'], 2)
        self.assertEqual(list(self.personal.entries.values_list('work_id', 'position')),
            [(self.works[0].pk, 7), (self.works[2].pk, 8), (self.works[1].pk, 9)])
        self.assertEqual(RankingEntry.objects.filter(pk=self.entry.pk).values().get(), before)
        self.assertEqual(RankingEntry.objects.filter(pk=self.shared_entry.pk).values().get(), shared)
        versions = list(RankingRevision.objects.filter(ranking=self.personal).order_by('number'))
        self.assertEqual([len(row.snapshot['entries']) for row in versions], [1, 3])
        self.assertEqual(LibraryItem.objects.filter(user=self.user).count(), 1)

    def test_list_noop_creates_no_revision(self):
        response = self.post('personal_list', [self.works[0].pk], ranking_id=self.personal.pk, expected_revision=1)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['unchanged_count'], 1)
        self.assertEqual(response.data['revision'], 1)
        self.assertFalse(RankingRevision.objects.filter(ranking=self.personal).exists())

    def test_stale_list_revision_rolls_back_all_changes(self):
        response = self.post('personal_list', ranking_id=self.personal.pk, expected_revision=2)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.personal.entries.count(), 1)
        self.assertFalse(RankingRevision.objects.filter(ranking=self.personal).exists())

    def test_list_action_refuses_foreign_shared_archived_people_or_published_personal_lists(self):
        for ranking in [self.foreign, self.shared]:
            with self.subTest(ranking=ranking.pk):
                self.assertEqual(self.post('personal_list', ranking_id=ranking.pk).status_code, 400)
        for field, value in [('is_archived', True), ('sharing_enabled', True), ('item_type', 'person')]:
            with self.subTest(field=field):
                original = getattr(self.personal, field)
                Ranking.objects.filter(pk=self.personal.pk).update(**{field: value})
                self.assertEqual(self.post('personal_list', ranking_id=self.personal.pk).status_code, 400)
                Ranking.objects.filter(pk=self.personal.pk).update(**{field: original})
        self.assertEqual(self.personal.entries.count(), 1)
        self.assertFalse(RankingRevision.objects.exists())

    def test_list_form_scope_and_archived_entries_are_respected(self):
        Ranking.objects.filter(pk=self.personal.pk).update(scope={'forms': ['poetry']})
        self.assertEqual(self.post('personal_list', ranking_id=self.personal.pk).status_code, 400)
        Ranking.objects.filter(pk=self.personal.pk).update(scope={})
        RankingEntry.objects.filter(pk=self.entry.pk).update(is_archived=True)
        self.assertEqual(self.post('personal_list', ranking_id=self.personal.pk).status_code, 400)
        self.assertEqual(self.personal.entries.count(), 1)

    def test_labels_merge_without_replacing_existing_names_or_other_fields(self):
        before = LibraryItem.objects.filter(pk=self.saved.pk).values().get()
        for action, values in [('shelves', [' Owned ', 'Weekend', 'Weekend']), ('personal_tags', ['New tag'])]:
            response = self.post(action, [self.works[0].pk], values=values)
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data['updated_labels'], 1)
        self.saved.refresh_from_db()
        self.assertEqual(self.saved.shelves, ['Owned', 'Weekend'])
        self.assertEqual(self.saved.personal_tags, ['Keep', 'New tag'])
        after = LibraryItem.objects.filter(pk=self.saved.pk).values().get()
        for field in ['shelves', 'personal_tags', 'updated_at']:
            before.pop(field)
            after.pop(field)
        self.assertEqual(before, after)
        timestamp = self.saved.updated_at
        self.assertEqual(self.post('shelves', [self.works[0].pk], values=['Owned']).data['unchanged_count'], 1)
        self.saved.refresh_from_db()
        self.assertEqual(self.saved.updated_at, timestamp)

    def test_labels_require_all_selected_books_in_own_library(self):
        response = self.post('shelves', [self.works[0].pk, self.works[1].pk], values=['New'])
        self.assertEqual(response.status_code, 400)
        self.saved.refresh_from_db()
        self.assertEqual(self.saved.shelves, ['Owned'])
        self.other_saved.refresh_from_db()
        self.assertEqual(self.other_saved.shelves, [])

    def test_label_limit_rejects_entire_batch(self):
        full = LibraryItem.objects.create(user=self.user, work=self.works[1], shelves=[f'Shelf {i}' for i in range(50)])
        response = self.post('shelves', [self.works[0].pk, full.work_id], values=['Another'])
        self.assertEqual(response.status_code, 400)
        self.saved.refresh_from_db()
        self.assertEqual(self.saved.shelves, ['Owned'])
        full.refresh_from_db()
        self.assertEqual(len(full.shelves), 50)

    def test_invalid_or_archived_work_rejects_entire_batch(self):
        Work.objects.filter(pk=self.works[3].pk).update(is_archived=True)
        for ids in [[self.works[1].pk, self.works[3].pk], [self.works[1].pk, 99999999]]:
            with self.subTest(ids=ids):
                self.assertEqual(self.post(ids=ids).status_code, 400)
        self.assertEqual(LibraryItem.objects.filter(user=self.user).count(), 1)

    def test_archived_default_edition_requires_individual_edition_choice_for_new_saves(self):
        Edition.objects.filter(pk=self.edition.pk).update(is_archived=True)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.post(ids=[self.works[0].pk, self.works[2].pk]).status_code, 400)
        self.assertEqual(LibraryItem.objects.filter(user=self.other).count(), 1)

    def test_keyed_retries_replay_once_and_unkeyed_repeats_are_noops(self):
        headers = {'HTTP_IDEMPOTENCY_KEY': str(uuid4())}
        first = self.post('read_next', headers=headers)
        second = self.post('read_next', headers=headers)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data, second.data)
        self.assertEqual(second['Idempotency-Replayed'], 'true')
        self.assertEqual(MutationReceipt.objects.filter(user=self.user).count(), 1)
        again = self.post('read_next')
        self.assertEqual(again.data['added_to_library'], 0)
        self.assertEqual(again.data['added_to_read_next'], 0)
        self.assertEqual(again.data['unchanged_count'], 4)
        self.assertEqual(self.post('library', headers=headers).status_code, 400)

    def test_list_retry_replays_before_checking_the_now_advanced_revision(self):
        headers = {'HTTP_IDEMPOTENCY_KEY': str(uuid4())}
        first = self.post('personal_list', ranking_id=self.personal.pk, expected_revision=1, headers=headers)
        again = self.post('personal_list', ranking_id=self.personal.pk, expected_revision=1, headers=headers)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data, again.data)
        self.assertEqual(RankingRevision.objects.filter(ranking=self.personal).count(), 2)

    def test_failed_revision_write_rolls_back_membership_and_receipt(self):
        with patch('backend.core.views.save_revision', side_effect=RuntimeError('Simulated storage failure')):
            with self.assertRaises(RuntimeError):
                self.post('personal_list', ranking_id=self.personal.pk, headers={'HTTP_IDEMPOTENCY_KEY': str(uuid4())})
        self.assertEqual(self.personal.entries.count(), 1)
        self.assertFalse(RankingRevision.objects.exists())
        self.assertFalse(MutationReceipt.objects.exists())

    def test_strict_bounded_commands_reject_bad_ids_and_unrelated_fields(self):
        for ids in [[], [True], ['1'], [1.0], [-1], [2**63], [self.works[0].pk] * 201]:
            with self.subTest(ids=ids[:2]):
                self.assertEqual(self.post(ids=ids).status_code, 400)
        for command in [{'action': 'other'}, {'action': 'personal_list'}, {'ranking_id': self.personal.pk},
                        {'expected_revision': 1}, {'notes': 'replace'}, {'values': ['unused']},
                        {'action': 'shelves', 'values': [' ']}, {'action': 'shelves', 'values': [123]},
                        {'action': 'personal_tags', 'values': ['x' * 101]}]:
            with self.subTest(command=command):
                self.assertEqual(self.post(**command).status_code, 400)
        self.assertEqual(LibraryItem.objects.filter(user=self.user).count(), 1)

    def test_authentication_required(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.post().status_code, 403)

    def test_bulk_writes_invalidate_catalog_on_commit_but_noop_does_not(self):
        with patch('backend.core.bulk_books.invalidate_catalog') as invalidate:
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(self.post(ids=[self.works[1].pk]).status_code, 200)
            invalidate.assert_called_once_with()
            invalidate.reset_mock()
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(self.post(ids=[self.works[1].pk]).status_code, 200)
            invalidate.assert_not_called()

    def test_library_batch_uses_bounded_queries_instead_of_per_book_reads(self):
        works = Work.objects.bulk_create([Work(title=f'Batch query fixture {i}') for i in range(100)])
        with CaptureQueriesContext(connection) as queries:
            response = self.post(ids=[work.pk for work in works])
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['added_to_library'], 100)
        self.assertLessEqual(len(queries), 15)
