"""Restore a completed backup into a fresh private directory, never over live data."""
import hashlib
import json
import shutil
import sqlite3
import tarfile
import tempfile
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.backends.sqlite3._functions import register
from backend.core.local_backups import restore_media


class Command(BaseCommand):
    help = 'Rehearse SQLite/media recovery in an isolated directory and verify integrity and media references.'

    def add_arguments(self, parser):
        parser.add_argument('backup', help='Completed backup stem, e.g. manual-20260913T...Z')

    def handle(self, *args, **options):
        name = options['backup']
        if Path(name).name != name:
            raise CommandError('Pass a backup name, not a path.')
        stem = settings.BASE_DIR / 'data/backups' / name
        if not stem.with_suffix('.complete').is_file():
            raise CommandError('Backup is not marked complete.')
        destination = Path(tempfile.mkdtemp(prefix='marginalia-restore-')).resolve()
        database = destination / 'restored.sqlite3'
        shutil.copy2(stem.with_suffix('.sqlite3'), database)
        archive_path = stem.with_suffix('.media.tar.gz')
        file_count = 0
        if stem.with_suffix('.media.json').exists():
            try:
                file_count = restore_media(stem, destination / 'media')
            except (OSError, ValueError) as error:
                raise CommandError(str(error)) from error
        elif archive_path.exists():
            with tarfile.open(archive_path) as archive:
                for member in archive:
                    target = (destination / member.name).resolve()
                    if not target.is_relative_to(destination) or not (member.isfile() or member.isdir()):
                        raise CommandError('Unsafe media archive member.')
                    if member.isdir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with archive.extractfile(member) as source, target.open('xb') as output:
                            shutil.copyfileobj(source, output)
                        file_count += 1
            # A second pass compares restored bytes to the archived bytes.
            with tarfile.open(archive_path) as archive:
                for member in archive:
                    if member.isfile():
                        with archive.extractfile(member) as source, (destination / member.name).open('rb') as restored:
                            if hashlib.file_digest(source, 'sha256').digest() != hashlib.file_digest(restored, 'sha256').digest():
                                raise CommandError('Restored media checksum mismatch.')
        with sqlite3.connect(database) as connection:
            # Existing planner constraints call Django's SQLite date functions.
            register(connection)
            if connection.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise CommandError('Database integrity check failed.')
            if connection.execute('PRAGMA foreign_key_check').fetchall():
                raise CommandError('Database foreign key check failed.')
            guards = connection.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'protect_%_deletion'").fetchall()
            if len(guards) != 8:
                raise CommandError('Expected eight shared deletion guards.')
            missing = []
            for table, field in [('core_edition', 'cover'), ('core_person', 'portrait')]:
                for (value,) in connection.execute(f'SELECT {field} FROM {table} WHERE {field} != ?', ('',)):
                    path = (destination / 'media' / value).resolve()
                    if not path.is_relative_to(destination / 'media') or not path.is_file():
                        missing.append(value)
            if missing:
                raise CommandError(f'{len(missing)} referenced media files missing in restored backup.')
            counts = {table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                      for (table,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'core_%'").fetchall()}
        report = {'backup': name, 'restored_directory': str(destination), 'integrity': 'ok',
                  'foreign_keys': 'ok', 'guards': len(guards), 'media_files_verified': file_count, 'table_counts': counts}
        (destination / 'report.json').write_text(json.dumps(report, indent=2))
        self.stdout.write(json.dumps(report, indent=2))
