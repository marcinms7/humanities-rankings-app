"""Search regressions use Django's isolated test database and disposable indexes."""
import json
import sqlite3
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase, override_settings

from .models import LibraryItem, Person, Tag, Work
from . import search
from .search import fold, fts_query, index_status, rebuild_index, search_catalog, sync_index


class CatalogSearchTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.aliases = Path(self.directory.name) / 'aliases.json'
        self.aliases.write_text('{"works": {}, "people": {}}')
        self.settings = override_settings(CATALOG_SEARCH_INDEX=Path(self.directory.name) / 'search.sqlite3', CATALOG_SEARCH_ALIASES=self.aliases)
        self.settings.enable()
        self.addCleanup(self.settings.disable)
        self.person = Person.objects.create(name='José Łukasz')
        self.work = Work.objects.create(title='Éducation sentimentale')
        self.work.authors.add(self.person)
        self.other = Work.objects.create(title='Studies of Éducation')

    def matches(self, query, queryset=None):
        return list(search_catalog(queryset if queryset is not None else Work.objects.all(), query).values_list('id', flat=True))

    def test_normalization_and_literal_safe_query(self):
        self.assertEqual(fold('Łódź STRAẞE Æsir'), 'lodz strasse aesir')
        self.assertEqual(fts_query('"education" OR (Jose*)'), '"education"* AND "or"* AND "jose"*')
        self.assertEqual(self.matches('"*()'), [])

    def test_indexed_title_author_and_accent_search(self):
        rebuild_index()
        self.assertEqual(self.matches('education jose'), [self.work.pk])
        self.assertEqual(list(search_catalog(Person.objects.all(), 'lukasz', kind='person').values_list('id', flat=True)), [self.person.pk])
        self.assertEqual(self.matches('education')[0], self.work.pk)

    def test_explicit_aliases_without_changing_catalog(self):
        self.aliases.write_text(json.dumps({'works': {str(self.work.pk): ['Sentimental Education']}, 'people': {str(self.person.pk): ['J. Luke']}}))
        rebuild_index()
        self.assertEqual(self.matches('sentimental luke'), [self.work.pk])
        self.work.refresh_from_db()
        self.assertEqual(self.work.title, 'Éducation sentimentale')

    def test_portable_fallback_matches_normalized_queries(self):
        with patch('backend.core.search._indexed_ids', return_value=None):
            self.assertEqual(self.matches('edu jose'), [self.work.pk])

    def test_candidate_index_never_overrides_visibility_filter(self):
        self.work.is_archived = True
        self.work.save(update_fields=['is_archived'])
        rebuild_index()
        self.assertEqual(self.matches('jose', Work.objects.filter(is_archived=False)), [])
        # An archived book remains searchable in its owner's existing library.
        self.assertEqual(self.matches('jose', Work.objects.filter(pk=self.work.pk)), [self.work.pk])

    def test_changed_alias_file_invalidates_generation(self):
        rebuild_index()
        self.assertFalse(index_status()['stale'])
        self.aliases.write_text(json.dumps({'works': {str(self.work.pk): ['Alternative']}}))
        self.assertTrue(index_status()['stale'])

    def test_failed_rebuild_keeps_previous_index(self):
        rebuild_index()
        self.aliases.write_text('{"works": {"oops": ["Invalid"]}}')
        with self.assertRaises(ValueError):
            rebuild_index()
        self.assertFalse(index_status().get('missing', False))

    def test_invalidated_rows_still_apply_live_queryset(self):
        rebuild_index()
        self.work.is_archived = True
        self.work.save(update_fields=['is_archived'])
        self.assertEqual(self.matches('jose', Work.objects.filter(is_archived=False)), [])

    def save_committed(self, instance, **kwargs):
        with self.captureOnCommitCallbacks(execute=True):
            instance.save(**kwargs)

    def test_title_edit_updates_one_document_and_keeps_index_identity(self):
        original = rebuild_index()
        self.work.title = 'A changed title'
        self.save_committed(self.work, update_fields=['title'])
        self.assertEqual(index_status()['pending'], 1)
        result = sync_index()
        self.assertEqual(result['last_update'], {'mode': 'incremental', 'scanned': 1, 'updated': 1, 'deleted': 0})
        self.assertEqual(result['built_at'], original['built_at'])
        self.assertEqual(index_status()['pending'], 0)
        self.assertEqual(self.matches('changed'), [self.work.pk])
        self.assertEqual(self.matches('education'), [self.other.pk])

    def test_author_rename_updates_author_and_related_books_only(self):
        rebuild_index()
        self.person.name = 'Renée Cooper'
        self.save_committed(self.person)
        result = sync_index()
        self.assertEqual(result['last_update']['scanned'], 2)
        self.assertEqual(result['last_update']['updated'], 2)
        self.assertEqual(self.matches('renee'), [self.work.pk])
        self.assertEqual(self.matches('jose'), [])
        self.assertEqual(list(search_catalog(Person.objects.all(), 'renee', kind='person').values_list('id', flat=True)), [self.person.pk])

    def test_tag_rename_and_archive_refresh_related_work(self):
        tag = Tag.objects.create(name='Original category')
        self.work.tags.add(tag)
        rebuild_index()
        tag.name = 'Changed category'
        self.save_committed(tag, update_fields=['name'])
        self.assertEqual(sync_index()['last_update']['updated'], 1)
        self.assertEqual(self.matches('changed'), [self.work.pk])
        tag.is_archived = True
        self.save_committed(tag, update_fields=['is_archived'])
        self.assertEqual(sync_index()['last_update']['updated'], 1)
        self.assertEqual(self.matches('changed'), [])

    def test_reverse_clear_preserves_affected_book_ids(self):
        self.other.authors.add(self.person)
        rebuild_index()
        with self.captureOnCommitCallbacks(execute=True):
            self.person.works.clear()
        self.assertEqual(sync_index()['last_update']['updated'], 2)
        self.assertEqual(self.matches('jose'), [])
        tag = Tag.objects.create(name='Rare category')
        self.work.tags.add(tag)
        rebuild_index()
        with self.captureOnCommitCallbacks(execute=True):
            tag.work_set.clear()
        self.assertEqual(sync_index()['last_update']['updated'], 1)
        self.assertEqual(self.matches('rare'), [])

    def test_add_remove_and_forward_clear_refresh_only_changed_memberships(self):
        rebuild_index()
        with self.captureOnCommitCallbacks(execute=True):
            self.other.authors.add(self.person)
        self.assertEqual(sync_index()['last_update']['scanned'], 1)
        self.assertEqual(set(self.matches('jose')), {self.work.pk, self.other.pk})
        with self.captureOnCommitCallbacks(execute=True):
            self.other.authors.remove(self.person)
        self.assertEqual(sync_index()['last_update']['updated'], 1)
        with self.captureOnCommitCallbacks(execute=True):
            self.work.authors.clear()
        self.assertEqual(sync_index()['last_update']['updated'], 1)
        self.assertEqual(self.matches('jose'), [])

    def test_unsearchable_catalog_and_private_edits_enqueue_nothing(self):
        rebuild_index()
        self.person.image_attribution = 'Changed image credit'
        self.save_committed(self.person)
        self.person.portrait = 'portraits/example.jpg'
        self.save_committed(self.person, update_fields=['portrait'])
        self.work.description = 'Changed description'
        self.save_committed(self.work)
        self.work.is_archived = True
        self.save_committed(self.work, update_fields=['is_archived'])
        with self.captureOnCommitCallbacks(execute=True):
            user = get_user_model().objects.create(username='isolated-search-reader')
            LibraryItem.objects.create(user=user, work=self.work, notes='Private words never indexed')
        self.assertEqual(index_status()['pending'], 0)
        self.assertEqual(sync_index()['last_update']['scanned'], 0)

    def test_unrelated_source_changes_reconcile_without_rebuilding_fts(self):
        original = rebuild_index()
        with patch('backend.core.search._source_stamp', return_value=['changed externally']), patch('backend.core.search.time.time', return_value=time.time() + 61):
            self.assertTrue(index_status()['needs_reconcile'])
            result = sync_index()
        self.assertEqual(result['built_at'], original['built_at'])
        self.assertEqual(result['last_update']['scanned'], 0)
        self.assertEqual(result['last_update']['updated'], 0)
        self.assertGreaterEqual(result['last_update']['checked_catalog_rows'], 4)

    def test_bulk_sql_update_is_reconciled_without_full_rebuild(self):
        original = rebuild_index()
        Work.objects.filter(pk=self.work.pk).update(title='Bulk revised title')
        result = sync_index(reconcile=True)
        self.assertEqual(result['built_at'], original['built_at'])
        self.assertEqual(result['last_update']['updated'], 1)
        self.assertEqual(self.matches('bulk'), [self.work.pk])

    def test_bulk_revert_after_incremental_edit_does_not_match_an_outdated_digest(self):
        rebuild_index()
        original = self.work.title
        self.work.title = 'Temporary rename'
        self.save_committed(self.work)
        sync_index()
        Work.objects.filter(pk=self.work.pk).update(title=original)
        self.assertEqual(sync_index(reconcile=True)['last_update']['updated'], 1)
        self.assertEqual(self.matches('temporary'), [])
        self.assertEqual(self.matches('education')[0], self.work.pk)

    def test_changed_aliases_reconcile_only_affected_documents(self):
        original = rebuild_index()
        self.aliases.write_text(json.dumps({'works': {str(self.work.pk): ['Another title']}}))
        result = sync_index()
        self.assertEqual(result['built_at'], original['built_at'])
        self.assertEqual(result['last_update']['updated'], 1)
        self.assertEqual(self.matches('another'), [self.work.pk])

    def test_new_generation_of_same_identity_survives_worker_acknowledgement(self):
        rebuild_index()
        self.work.title = 'First change'
        self.save_committed(self.work)
        documents = search._documents

        def concurrent_documents(*args, **kwargs):
            for row in documents(*args, **kwargs):
                yield row
                Work.objects.filter(pk=self.work.pk).update(title='Second change')
                search._enqueue([('work', self.work.pk)])

        with patch('backend.core.search._documents', side_effect=concurrent_documents):
            sync_index()
        self.assertEqual(index_status()['pending'], 1)
        self.assertEqual(sync_index()['last_update']['updated'], 1)
        self.assertEqual(index_status()['pending'], 0)
        self.assertEqual(self.matches('second'), [self.work.pk])

    def test_rolled_back_save_never_queues_change(self):
        rebuild_index()
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(ValueError), transaction.atomic():
                self.work.title = 'Rolled back'
                self.work.save()
                raise ValueError('rollback')
        self.assertEqual(index_status()['pending'], 0)
        self.assertEqual(self.matches('education')[0], self.work.pk)

    def test_failed_sync_keeps_previous_fts_and_pending_change(self):
        original = rebuild_index()
        self.work.title = 'Changed title'
        self.save_committed(self.work)
        documents = search._documents

        def failed_documents(*args, **kwargs):
            yield from documents(*args, **kwargs)
            raise ValueError('interrupted update')

        with patch('backend.core.search._documents', side_effect=failed_documents):
            with self.assertRaises(ValueError):
                sync_index()
        self.assertEqual(index_status()['pending'], 1)
        with sqlite3.connect(search.index_path()) as source:
            info = json.loads(source.execute('SELECT value FROM metadata').fetchone()[0])
            self.assertEqual(info['updated_at'], original['updated_at'])
            self.assertEqual(source.execute('SELECT title FROM documents WHERE kind = ? AND object_id = ?', ['work', self.work.pk]).fetchone()[0], 'education sentimentale')
        self.assertEqual(sync_index()['last_update']['updated'], 1)

    def test_repeated_changes_preserve_first_pending_time_and_bound_staleness(self):
        rebuild_index()
        with patch('backend.core.search.time.time', return_value=time.time() - 121):
            search._enqueue([('work', self.work.pk)])
        search._enqueue([('work', self.work.pk)])
        self.assertIsNone(search._indexed_ids('education', 'work', 'default'))

    def test_newly_detected_source_change_after_long_idle_keeps_valid_index_temporarily(self):
        rebuild_index()
        future = time.time() + 3600
        with patch('backend.core.search._source_stamp', return_value=['changed externally']), patch('backend.core.search.time.time', return_value=future):
            self.assertEqual(index_status()['stale_since'], future)
            self.assertIsNotNone(search._indexed_ids('education', 'work', 'default'))
        with patch('backend.core.search._source_stamp', return_value=['changed again']), patch('backend.core.search.time.time', return_value=future + 121):
            self.assertEqual(index_status()['stale_since'], future)
            self.assertIsNone(search._indexed_ids('education', 'work', 'default'))

    def test_invalid_alias_change_keeps_previous_index_and_pending_changes(self):
        rebuild_index()
        self.work.title = 'Changed title'
        self.save_committed(self.work)
        self.aliases.write_text('{"works": {"oops": ["Invalid"]}}')
        with self.assertRaises(ValueError):
            sync_index()
        self.assertFalse(index_status().get('missing', False))
        self.assertEqual(index_status()['pending'], 1)
