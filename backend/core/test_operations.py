"""Operational safeguards for a future authorized isolated regression run."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from .local_backups import backup_lock, backup_manifest, copy_snapshot, create_snapshot, restore_media
from .management.commands.backup_retention import retention_proposal
from . import telemetry
from research.operational_state import atomic_state, read_state


class IncrementalBackupTests(SimpleTestCase):
    def test_incremental_objects_restore_and_old_snapshots_are_retained(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); media = root / 'media'; media.mkdir()
            (media / 'cover.bin').write_bytes(b'original fixture image')
            database = root / 'source.sqlite3'
            with sqlite3.connect(database) as db:
                db.execute('CREATE TABLE core_edition (cover TEXT)')
                db.execute('INSERT INTO core_edition VALUES (?)', ('cover.bin',))
            directory = root / 'backups'
            with backup_lock(directory):
                first = create_snapshot(database, media, directory, 'manual-first')
                second = create_snapshot(database, media, directory, 'daily-second')
            self.assertEqual((first['new_objects'], second['new_objects']), (1, 0))
            self.assertEqual((media / 'cover.bin').read_bytes(), b'original fixture image')
            self.assertTrue((directory / 'manual-first.complete').exists())
            destination = root / 'external'; destination.mkdir()
            copied = copy_snapshot(directory / 'daily-second', destination)
            self.assertEqual(copied['status'], 'copied')
            self.assertEqual(restore_media(destination / 'daily-second', root / 'restored-media'), 1)
            self.assertEqual((root / 'restored-media/cover.bin').read_bytes(), b'original fixture image')
            manifest = backup_manifest(directory / 'manual-first')
            self.assertEqual(manifest['version'], 2)
            self.assertEqual(os.stat(directory / 'manual-first.sqlite3').st_mode & 0o777, 0o600)

    def test_missing_media_and_tampered_manifests_are_never_published_as_restorable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); database = root / 'source.sqlite3'; media = root / 'media'; media.mkdir()
            with sqlite3.connect(database) as db:
                db.execute('CREATE TABLE core_person (portrait TEXT)')
                db.execute('INSERT INTO core_person VALUES (?)', ('missing.png',))
            directory = root / 'backups'
            with backup_lock(directory), self.assertRaisesMessage(ValueError, 'missing media'):
                create_snapshot(database, media, directory, 'manual-missing')
            self.assertFalse((directory / 'manual-missing.complete').exists())
            (media / 'missing.png').write_bytes(b'now supplied')
            with backup_lock(directory):
                create_snapshot(database, media, directory, 'manual-present')
            manifest = directory / 'manual-present.media.json'
            manifest.write_text(manifest.read_text() + ' ')
            with self.assertRaisesMessage(ValueError, 'checksum'):
                restore_media(directory / 'manual-present', root / 'restore')

    def test_retention_is_dry_run_and_always_preserves_manual_and_latest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old = datetime.now(timezone.utc) - timedelta(days=1000)
            for name in ('manual-important', 'daily-20200101', 'daily-20200102'):
                marker = root / f'{name}.complete'; marker.touch()
                os.utime(marker, (old.timestamp(), old.timestamp()))
                old += timedelta(days=1)
            result = retention_proposal(root)
            self.assertTrue(result['dry_run'])
            self.assertEqual(result['deleted'], 0)
            self.assertIn('manual-important', {row['name'] for row in result['keep']})
            self.assertIn('daily-20200102', {row['name'] for row in result['keep']})
            self.assertTrue((root / 'daily-20200101.complete').exists())

    def test_atomic_worker_state_and_corrupt_cooldown_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'cooldown.json'
            atomic_state(path, {'until': 100, 'reason': 'fixture'})
            self.assertEqual(read_state(path)['until'], 100)
            self.assertFalse(list(path.parent.glob('*.partial')))
            path.write_text('{torn')
            self.assertTrue(read_state(path, cooldown=True)['invalid_state'])
            self.assertGreater(read_state(path, cooldown=True)['until'], datetime.now(timezone.utc).timestamp())


class TelemetryTests(SimpleTestCase):
    def setUp(self):
        telemetry._samples.clear()

    @override_settings(DEBUG=False)
    def test_timings_are_bounded_and_do_not_capture_querystrings_or_payloads(self):
        request = RequestFactory().post('/api/library/?search=PRIVATE-SEARCH', {'notes': 'PRIVATE NOTE'})
        request.resolver_match = SimpleNamespace(route='api/library/<int:pk>/')
        request.user = SimpleNamespace(is_authenticated=True, is_staff=False)
        middleware = telemetry.OperationalTelemetryMiddleware(lambda _: HttpResponse('ok'))
        for _ in range(305):
            response = middleware(request)
        self.assertIn('X-Request-ID', response)
        self.assertNotIn('Server-Timing', response)
        summary = telemetry.telemetry_summary()
        self.assertEqual(summary['sample_count'], 300)
        self.assertNotIn('PRIVATE', json.dumps(summary))
        request.user.is_staff = True
        self.assertIn('Server-Timing', middleware(request))


class OperationsPermissionsTests(TestCase):
    def test_only_staff_can_read_operational_summaries(self):
        client = APIClient()
        reader = get_user_model().objects.create_user('operations-reader')
        staff = get_user_model().objects.create_user('operations-staff', is_staff=True)
        for user in (None, reader):
            client.force_authenticate(user)
            self.assertEqual(client.get('/api/operations/').status_code, 403)
        client.force_authenticate(staff)
        with patch('backend.core.operations.storage_summary', return_value={}), patch('backend.core.operations.worker_summary', return_value={}):
            response = client.get('/api/operations/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
