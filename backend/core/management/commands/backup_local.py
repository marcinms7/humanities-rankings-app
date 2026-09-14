"""Consistent SQLite backup, with local uploaded images; never rotates old copies."""
import sqlite3
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Back up the local SQLite database and uploaded media to data/backups.'

    def add_arguments(self, parser):
        parser.add_argument('--daily', action='store_true', help='Skip if today already has a completed daily backup.')

    def handle(self, *args, **options):
        config = settings.DATABASES['default']
        if config['ENGINE'] != 'django.db.backends.sqlite3':
            raise CommandError('For PostgreSQL use pg_dump and your hosting backup service.')
        source = Path(config['NAME'])
        if not source.is_file():
            raise CommandError('No local database exists yet.')
        now = datetime.now(timezone.utc)
        directory = settings.BASE_DIR / 'data' / 'backups'
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        stamp = now.strftime('%Y%m%d') if options['daily'] else now.strftime('%Y%m%dT%H%M%S%fZ')
        target = directory / f'{"daily" if options["daily"] else "manual"}-{stamp}'
        complete = target.with_suffix('.complete')
        if complete.exists():
            return
        with sqlite3.connect(f'{source.resolve().as_uri()}?mode=ro', uri=True) as src, sqlite3.connect(target.with_suffix('.sqlite3')) as dst:
            src.backup(dst)
        target.with_suffix('.sqlite3').chmod(0o600)
        media = Path(settings.MEDIA_ROOT)
        if media.is_dir():
            with tarfile.open(target.with_suffix('.media.tar.gz'), 'w:gz') as archive:
                archive.add(media, arcname='media')
            target.with_suffix('.media.tar.gz').chmod(0o600)
        complete.touch(mode=0o600)
        self.stdout.write(f'Local backup saved: {target.name}')
