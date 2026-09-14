"""Portable fixture transfer, retaining application IDs and password hashes."""
import hashlib
import json
from pathlib import Path
from django.apps import apps
from django.core import serializers
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.migrations.recorder import MigrationRecorder


class Command(BaseCommand):
    help = 'Export a private transfer bundle, or import it into an empty migrated PostgreSQL database.'

    def add_arguments(self, parser):
        parser.add_argument('operation', choices=['export', 'import'])
        parser.add_argument('directory')

    def handle(self, *args, **options):
        directory = Path(options['directory']).resolve()
        models = [m for m in apps.get_app_config('core').get_models() if m.__name__ != 'AuthRateLimit']
        fixture = directory / 'records.json'
        manifest = directory / 'manifest.json'
        if options['operation'] == 'export':
            if directory.exists():
                raise CommandError('Choose a new private directory; exports never overwrite bundles.')
            directory.mkdir(parents=True, mode=0o700)
            # Caller exports a frozen backup, ensuring consistent rows and counts.
            with transaction.atomic(), fixture.open('x') as stream:
                call_command('dumpdata', 'core', 'auth.group', exclude=['core.authratelimit'], natural_foreign=True, stdout=stream)
                counts = {m._meta.label_lower: m.objects.count() for m in models}
            fixture.chmod(0o600)
            migrations = sorted(MigrationRecorder.Migration.objects.values_list('app', 'name'))
            manifest.write_text(json.dumps({'sha256': hashlib.sha256(fixture.read_bytes()).hexdigest(), 'counts': counts, 'migrations': migrations}, indent=2))
            manifest.chmod(0o600)
            self.stdout.write(f'Private transfer bundle saved to {directory}. Keep alongside its media backup.')
            return
        if connection.vendor != 'postgresql':
            raise CommandError('Import is allowed only into an empty PostgreSQL database.')
        if any(m.objects.exists() for m in models):
            raise CommandError('Destination contains application records. Refusing to overwrite them.')
        expected = json.loads(manifest.read_text())
        applied = sorted([list(row) for row in MigrationRecorder.Migration.objects.values_list('app', 'name')])
        if applied != expected['migrations']:
            raise CommandError('Source and destination migration versions differ. Use matching application versions.')
        if hashlib.sha256(fixture.read_bytes()).hexdigest() != expected['sha256']:
            raise CommandError('Fixture checksum mismatch.')
        with transaction.atomic():
            call_command('loaddata', str(fixture))
            for m in models:
                if m.objects.count() != expected['counts'][m._meta.label_lower]:
                    raise CommandError(f'Count mismatch for {m._meta.label_lower}; rolling back.')
            # Compare every application field and relationship after deserialization.
            for obj in serializers.deserialize('json', fixture.read_text()):
                actual = obj.object.__class__.objects.get(pk=obj.object.pk)
                for field in obj.object._meta.concrete_fields:
                    if getattr(actual, field.attname) != getattr(obj.object, field.attname):
                        raise CommandError(f'Field mismatch in {obj.object._meta.label}; rolling back.')
                for field, values in (obj.m2m_data or {}).items():
                    if set(getattr(actual, field).values_list('pk', flat=True)) != set(values):
                        raise CommandError('Relationship mismatch; rolling back.')
        self.stdout.write('PostgreSQL import committed; IDs, fields, relationships and counts verified. Media transfer remains separate.')
