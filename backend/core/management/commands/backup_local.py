"""Consistent SQLite snapshot and incremental media; never prunes old copies."""
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import sqlite3

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from backend.core.local_backups import atomic_json, backup_lock, copy_snapshot, create_snapshot


class Command(BaseCommand):
    help = 'Back up SQLite and content-addressed media; optionally copy the complete snapshot to a configured directory.'

    def add_arguments(self, parser):
        parser.add_argument('--daily', action='store_true', help='Reuse today’s completed snapshot and retry any configured copy.')
        parser.add_argument('--copy-destination', help='Existing external/mounted destination; defaults to MARGINALIA_BACKUP_COPY_DIR.')

    def handle(self, *args, **options):
        config = settings.DATABASES['default']
        if config['ENGINE'] != 'django.db.backends.sqlite3':
            raise CommandError('For PostgreSQL use pg_dump and your hosting backup service.')
        source = Path(config['NAME'])
        if not source.is_file():
            raise CommandError('No local database exists yet.')
        now = datetime.now(timezone.utc)
        directory = settings.BASE_DIR / 'data/backups'
        stamp = now.strftime('%Y%m%d') if options['daily'] else now.strftime('%Y%m%dT%H%M%S%fZ')
        if options['daily'] and source.resolve() != (settings.BASE_DIR / 'data/db.sqlite3').resolve():
            stamp += '-' + hashlib.sha256(str(source.resolve()).encode()).hexdigest()[:16]
        name = f'{"daily" if options["daily"] else "manual"}-{stamp}'
        destination = options.get('copy_destination') or os.getenv('MARGINALIA_BACKUP_COPY_DIR', '')
        status = {'attempted_at': now.isoformat(), 'status': 'running', 'snapshot': name,
                  'copy': {'configured': bool(destination), 'status': 'pending' if destination else 'not_configured'}}
        try:
            with backup_lock(directory):
                atomic_json(directory / 'backup-status.json', status)
                result = create_snapshot(source, Path(settings.MEDIA_ROOT), directory, name)
                status.update(status='complete', local_complete=True, finished_at=datetime.now(timezone.utc).isoformat(), result=result)
                atomic_json(directory / 'backup-status.json', status)
                if destination:
                    if Path(destination).expanduser().resolve().is_relative_to(Path(settings.MEDIA_ROOT).resolve()):
                        raise ValueError('The backup copy destination must be outside the original media directory.')
                    status['copy'] = copy_snapshot(directory / name, destination)
                    atomic_json(directory / 'backup-status.json', status)
        except (OSError, ValueError, sqlite3.Error) as error:
            status.update(status='copy_failed' if status.get('local_complete') else 'failed', error_type=type(error).__name__,
                          finished_at=datetime.now(timezone.utc).isoformat())
            if status.get('local_complete'):
                status['copy']['status'] = 'failed'
            atomic_json(directory / 'backup-status.json', status)
            raise CommandError(str(error)) from error
        self.stdout.write(f'Local backup {"already complete" if result["skipped"] else "saved"}: {name}; {result["format"]}.')
        if destination:
            self.stdout.write('Configured backup copy completed and checksums verified.')
