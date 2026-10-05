"""Manifest export uses disposable catalog/media only, with no network."""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from PIL import Image

from .management.commands import export_catalog_media_manifest as command
from research import media_image_quality
from .models import Edition, LibraryItem, Person, Work


class CatalogMediaManifestTests(TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.media = self.directory / 'media'
        self.output = self.media / 'catalog-manifest.json'
        configured = override_settings(MEDIA_ROOT=self.media, BASE_DIR=self.directory)
        configured.enable()
        self.addCleanup(configured.disable)
        self.person = Person.objects.create(name='Public Writer', biography='DO-NOT-EXPORT-BIOGRAPHY')
        self.work = Work.objects.create(title='Public Work', description='DO-NOT-EXPORT-DESCRIPTION')
        self.work.authors.add(self.person)
        self.path = 'covers/2026/10/original.png'
        self.blob = self.image(self.path)
        self.edition = Edition.objects.create(work=self.work, cover=self.path, language='French',
            publisher='Public Publisher', isbn='9780141439518', cover_basis='unknown',
            source_url='https://example.org/edition', cover_source_url='',
            image_attribution='Original credited image', translation_notes='DO-NOT-EXPORT-EDITION-NOTES')
        self.work.default_edition = self.edition
        self.work.save(update_fields=['default_edition'])

    def image(self, relative, format='PNG'):
        path = self.media / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        blob = io.BytesIO()
        Image.new('RGB', (100, 150), '#556677').save(blob, format=format)
        path.write_bytes(blob.getvalue())
        return blob.getvalue()

    def export(self, **options):
        call_command('export_catalog_media_manifest', output=self.output, stdout=io.StringIO(), **options)
        return json.loads(self.output.read_text())

    def test_covers_snapshot_preserves_public_associations_orphans_archives_and_database(self):
        archived = Edition.objects.create(work=self.work, cover=self.path, is_archived=True)
        self.image('covers/older-orphan.gif', format='GIF')
        self.image('portraits/not-selected.png')
        self.image('classical-education/private-upload.png')
        self.image('thumbnails/cache.png')
        user = get_user_model().objects.create_user('isolated-manifest-test', email='DO-NOT-EXPORT-EMAIL')
        LibraryItem.objects.create(user=user, work=self.work, notes='DO-NOT-EXPORT-PRIVATE-NOTES')
        before = list(Edition.objects.values())
        with CaptureQueriesContext(connection) as queries:
            manifest = self.export()
        self.assertFalse(any(sql['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for sql in queries))
        self.assertEqual(list(Edition.objects.values()), before)
        self.assertTrue(manifest['complete'])
        self.assertEqual(manifest['summary']['file_count'], 2)
        files = {row['path']: row for row in manifest['files']}
        original = files[self.path]
        self.assertEqual(original['sha256'], hashlib.sha256(self.blob).hexdigest())
        self.assertEqual(original['size'], len(self.blob))
        self.assertEqual(original['associations'][0]['authors'], [{'id': self.person.pk, 'name': self.person.name, 'is_archived': False}])
        first, second = original['associations']
        self.assertTrue(first['is_default_edition'])
        self.assertEqual(first['cover_basis'], 'unknown')
        self.assertEqual(first['cover_source_url'], '')
        self.assertEqual(first['source_url'], 'https://example.org/edition')
        self.assertEqual(second['edition_id'], archived.pk)
        self.assertTrue(second['edition_is_archived'])
        self.assertFalse(second['is_default_edition'])
        self.assertEqual(files['covers/older-orphan.gif']['association_status'], 'unreferenced')
        self.assertEqual(files['covers/older-orphan.gif']['associations'], [])
        self.assertEqual(files['covers/older-orphan.gif']['format'], 'GIF')
        text = self.output.read_text()
        self.assertNotIn('DO-NOT-EXPORT', text)
        self.assertNotIn('private-upload', text)
        self.assertNotIn('thumbnails', text)
        self.assertNotIn('not-selected', text)
        self.assertEqual((self.media / self.path).read_bytes(), self.blob)

    def test_portraits_require_explicit_option_and_preserve_attribution(self):
        self.image('portraits/person.png')
        Person.objects.filter(pk=self.person.pk).update(portrait='portraits/person.png', is_archived=True,
            source_url='', image_attribution='Photographer https://example.org/photo')
        manifest = self.export(include_portraits=True)
        portrait = next(row for row in manifest['files'] if row['kind'] == 'portrait')
        self.assertEqual(portrait['associations'][0]['person_id'], self.person.pk)
        self.assertEqual(portrait['associations'][0]['source_url'], '')
        self.assertIn('https://example.org/photo', portrait['associations'][0]['image_attribution'])
        self.assertTrue(portrait['associations'][0]['is_archived'])
        self.assertNotIn('DO-NOT-EXPORT', self.output.read_text())

    def test_missing_reference_writes_incomplete_manifest_and_fails(self):
        (self.media / self.path).unlink()
        with self.assertRaisesMessage(CommandError, 'Incomplete media manifest'):
            self.export()
        manifest = json.loads(self.output.read_text())
        self.assertFalse(manifest['complete'])
        self.assertEqual(manifest['errors'][0]['reason'], 'missing_file')
        self.assertEqual(manifest['files'], [])

    def test_invalid_referenced_image_fails_and_nonimage_junk_is_counted(self):
        (self.media / self.path).write_bytes(b'<html>not a cover</html>')
        (self.media / 'covers/.DS_Store').write_bytes(b'junk')
        with self.assertRaises(CommandError):
            self.export()
        manifest = json.loads(self.output.read_text())
        self.assertEqual(manifest['summary']['skipped_nonimage_count'], 1)
        self.assertEqual(manifest['errors'][0]['reason'], 'invalid_raster')
        self.assertEqual(manifest['files'], [])

    def test_symlink_file_and_directory_never_escape_media_root(self):
        outside = self.directory / 'outside'
        outside.mkdir()
        (outside / 'secret.png').write_bytes(self.blob)
        (self.media / self.path).unlink()
        (self.media / self.path).symlink_to(outside / 'secret.png')
        (self.media / 'covers/linked-directory').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(CommandError):
            self.export()
        manifest = json.loads(self.output.read_text())
        self.assertEqual(manifest['files'], [])
        self.assertEqual(manifest['summary']['excluded_symlink_count'], 2)
        self.assertEqual(manifest['errors'][0]['reason'], 'unreadable_or_unsafe_file')
        self.assertNotIn(str(outside), self.output.read_text())

    def test_unsafe_catalog_paths_are_reported_without_disclosing_absolute_paths(self):
        for reference in ('../private.png', '/private/secret.png', 'classical-education/private.png'):
            with self.subTest(reference=reference):
                Edition.objects.filter(pk=self.edition.pk).update(cover=reference)
                with self.assertRaises(CommandError):
                    self.export()
                manifest = json.loads(self.output.read_text())
                self.assertEqual(manifest['errors'][0]['reason'], 'unsafe_or_out_of_scope_reference')
                self.assertIsNone(manifest['errors'][0]['path'])
                self.assertNotIn(reference, self.output.read_text())

    def test_unreadable_reference_fails_instead_of_silently_omitting_it(self):
        actual_open = os.open
        def restricted(path, flags, *args, **kwargs):
            if path == 'original.png':
                raise PermissionError('fixture unreadable')
            return actual_open(path, flags, *args, **kwargs)
        with patch.object(command.os, 'open', side_effect=restricted), self.assertRaises(CommandError):
            self.export()
        self.assertEqual(json.loads(self.output.read_text())['errors'][0]['reason'], 'unreadable_or_unsafe_file')

    def test_known_placeholder_is_retained_and_excluded_from_usable_cover_count(self):
        digest = hashlib.sha256(self.blob).hexdigest()
        with patch.object(media_image_quality, 'KNOWN_PLACEHOLDERS', {digest: len(self.blob)}):
            manifest = self.export()
        self.assertTrue(manifest['complete'])
        self.assertEqual(manifest['summary']['cover_count'], 1)
        self.assertEqual(manifest['summary']['usable_cover_count'], 0)
        self.assertEqual(manifest['summary']['known_placeholder_count'], 1)
        self.assertFalse(manifest['files'][0]['usable'])
        self.assertEqual(manifest['files'][0]['quality'], 'known_placeholder')
        self.assertEqual(manifest['files'][0]['associations'][0]['edition_id'], self.edition.pk)
        self.assertEqual((self.media / self.path).read_bytes(), self.blob)

    def test_output_cannot_overwrite_an_original(self):
        with self.assertRaisesMessage(CommandError, 'must not overwrite original'):
            call_command('export_catalog_media_manifest', output=self.media / self.path, stdout=io.StringIO())
        self.assertEqual((self.media / self.path).read_bytes(), self.blob)
