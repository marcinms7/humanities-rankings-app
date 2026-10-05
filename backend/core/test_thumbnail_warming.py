"""Isolated regressions for image ingestion, concurrent misses and cache backfill."""
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction
from django.http import Http404
from django.test import TestCase, override_settings
from PIL import Image

from .models import Edition, Person, Work
from .thumbnails import SIZES, prepare_thumbnails, source_file, thumbnail_url


class ThumbnailWarmingTests(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.override = override_settings(MEDIA_ROOT=self.root / 'media', BASE_DIR=self.root)
        self.override.enable()
        self.addCleanup(self.override.disable)

    def image(self, name='covers/book.png', colour='white'):
        source = self.root / 'media' / name
        source.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (600, 900), colour).save(source)
        return source

    def test_warm_variants_are_bounded_and_first_request_does_not_decode(self):
        source = self.image()
        original = source.read_bytes()
        version, targets, created = prepare_thumbnails('covers/book.png')
        self.assertEqual(created, 3)
        self.assertEqual(set(targets), SIZES)
        for size, path in targets.items():
            with Image.open(path) as preview:
                self.assertEqual(preview.format, 'WEBP')
                self.assertLessEqual(preview.width, size)
                self.assertLessEqual(preview.height, size * 2)
        with patch('backend.core.thumbnails.Image.open', side_effect=AssertionError('Unexpected decode')):
            self.assertEqual(prepare_thumbnails('covers/book.png')[2], 0)
            response = self.client.get(thumbnail_url('covers/book.png', 240))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['ETag'], f'"{version}-240"')
            self.assertIn('immutable', response['Cache-Control'])
            response.close()
        self.assertEqual(source.read_bytes(), original)

    def test_cover_and_portrait_saves_warm_only_after_commit(self):
        self.image()
        self.image('portraits/person.png')
        work = Work.objects.create(title='Warm cover')
        with self.captureOnCommitCallbacks(execute=True):
            Edition.objects.create(work=work, cover='covers/book.png')
            Person.objects.create(name='Warm portrait', portrait='portraits/person.png')
            self.assertFalse((self.root / 'data' / 'thumbnail-cache').exists())
        self.assertEqual(len(list((self.root / 'data' / 'thumbnail-cache').glob('*.webp'))), 6)

    def test_rollback_and_unrelated_or_raw_saves_do_not_warm(self):
        self.image('portraits/person.png')
        person = Person.objects.create(name='Portrait reader', portrait='portraits/person.png')
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            person.biography = 'Only text changed.'
            person.save(update_fields=['biography'])
            person.save_base(raw=True)
            try:
                with transaction.atomic():
                    person.save(update_fields=['portrait'])
                    raise ValueError('Roll back the image save.')
            except ValueError:
                pass
        self.assertEqual(callbacks, [])
        self.assertFalse((self.root / 'data' / 'thumbnail-cache').exists())

    def test_replaced_source_gets_new_variants_without_changing_original(self):
        self.image()
        first_version, first_targets, _ = prepare_thumbnails('covers/book.png')
        source = self.image(colour='blue')
        original = source.read_bytes()
        version, targets, created = prepare_thumbnails('covers/book.png')
        self.assertNotEqual(version, first_version)
        self.assertEqual(created, 3)
        self.assertNotEqual(targets[240].read_bytes(), first_targets[240].read_bytes())
        self.assertEqual(source.read_bytes(), original)

    def test_concurrent_warmers_share_one_decode(self):
        self.image()
        ready = Barrier(2)

        def warm():
            ready.wait(timeout=5)
            return prepare_thumbnails('covers/book.png')[2]

        with patch('backend.core.thumbnails.Image.open', wraps=Image.open) as opened:
            with ThreadPoolExecutor(max_workers=2) as workers:
                futures = [workers.submit(warm) for _ in range(2)]
                counts = [future.result(timeout=10) for future in futures]
        self.assertEqual(sorted(counts), [0, 3])
        self.assertEqual(opened.call_count, 1)

    def test_failed_encoding_leaves_no_partial_files_and_can_retry(self):
        self.image()
        with patch('backend.core.thumbnails.Image.Image.save', side_effect=OSError('Cache unavailable')):
            with self.assertRaises(Http404):
                prepare_thumbnails('covers/book.png')
        self.assertEqual(list((self.root / 'data' / 'thumbnail-cache').glob('*.webp')), [])
        self.assertEqual(prepare_thumbnails('covers/book.png')[2], 3)

    def test_missing_image_does_not_fail_catalog_save(self):
        with self.assertLogs('backend.core.thumbnails', level='WARNING'):
            with self.captureOnCommitCallbacks(execute=True):
                person = Person.objects.create(name='Missing source', portrait='portraits/missing.png')
        person.refresh_from_db()
        self.assertEqual(str(person.portrait), 'portraits/missing.png')
        for invalid in ['.', '', 'covers/../../secret.png', '/etc/passwd']:
            with self.assertRaises(Http404):
                source_file(invalid)

    def test_bounded_backfill_is_resumable_and_preserves_records(self):
        self.image()
        self.image('covers/second.png')
        work = Work.objects.create(title='Backfill')
        first = Edition.objects.create(work=work, cover='covers/book.png', image_attribution='Retain credit')
        second = Edition.objects.create(work=work, cover='covers/second.png')
        missing = Edition.objects.create(work=work, cover='covers/missing.png')
        before = list(Edition.objects.values())
        output = StringIO()
        call_command('warm_thumbnails', kind='covers', limit=1, stdout=output)
        report = json.loads(output.getvalue())
        self.assertEqual(report['inspected'], 1)
        self.assertEqual(report['derivatives_created'], 3)
        self.assertEqual(report['next_after_id'], first.pk)
        self.assertTrue(report['has_more'])
        output = StringIO()
        call_command('warm_thumbnails', kind='covers', limit=2, after_id=first.pk, stdout=output)
        report = json.loads(output.getvalue())
        self.assertEqual(report['generated_images'], 1)
        self.assertEqual(report['failed_ids'], [missing.pk])
        self.assertFalse(report['has_more'])
        self.assertEqual(list(Edition.objects.values()), before)
        self.assertTrue(second.cover)
        output = StringIO()
        call_command('warm_thumbnails', kind='covers', limit=1, stdout=output)
        self.assertEqual(json.loads(output.getvalue())['cached_images'], 1)
        with self.assertRaises(CommandError):
            call_command('warm_thumbnails', limit=501)
