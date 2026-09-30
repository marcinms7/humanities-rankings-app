"""Attach locally verified, attributed images without replacing existing media."""
import hashlib
import json
from pathlib import Path

from PIL import Image
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from backend.core.models import Edition, Person
from backend.core.management.receipts import save_import_receipt


class Command(BaseCommand):
    help = 'Import a reviewed local image manifest, preserving all existing images.'

    def add_arguments(self, parser):
        parser.add_argument('path')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        path = Path(options['path'])
        raw = path.read_bytes()
        batch = json.loads(raw)
        prepared = []
        seen = set()
        for r in batch['images']:
            if not r.get('identity_reviewed') or not r.get('sha256'):
                raise CommandError('Every image needs a saved identity review and content digest.')
            local = Path(r['local_path']).resolve()
            if not local.is_relative_to(Path('research/catalog').resolve()):
                raise CommandError('Image must be inside research/catalog.')
            data = local.read_bytes()
            if len(data) > 8_000_000 or hashlib.sha256(data).hexdigest() != r['sha256']:
                raise CommandError('Image size or digest validation failed.')
            with Image.open(local) as image:
                image.verify()
            if not r.get('source_url', '').startswith('https://') or not r.get('license') or not 0 < len(r.get('attribution', '')) <= 500:
                raise CommandError('Image provenance and a concise attribution are required.')
            if r['kind'] == 'portrait':
                qs, field = Person.objects.filter(name=r['person_name'], is_archived=False), 'portrait'
            elif r['kind'] == 'cover':
                qs, field = Edition.objects.filter(isbn=r['isbn'], is_archived=False), 'cover'
            else:
                raise CommandError('Unknown image kind.')
            if qs.count() != 1:
                raise CommandError(f'A unique catalog match is required: {r.get("person_name", r.get("isbn"))}')
            obj = qs.get()
            key = (field, obj.pk)
            if key in seen:
                raise CommandError('Duplicate image target.')
            seen.add(key)
            prepared.append((obj, field, r, data))
        if options['dry_run']:
            self.stdout.write(f'Validated {len(prepared)} reviewed images; no writes.')
            return
        results = []
        with transaction.atomic():
            for obj, field, r, data in prepared:
                obj = type(obj).objects.select_for_update().get(pk=obj.pk)
                if obj.is_archived:
                    raise CommandError('Catalog item was archived during image review.')
                saved = False
                if not getattr(obj, field):
                    getattr(obj, field).save(Path(r['local_path']).name, ContentFile(data), save=False)
                    obj.image_attribution = r['attribution']
                    updated_fields = [field, 'image_attribution', 'updated_at']
                    if field == 'cover':
                        obj.cover_source_url = r['source_url']
                        obj.cover_basis = r.get('cover_basis', 'manually_supplied')
                        updated_fields.extend(['cover_source_url', 'cover_basis'])
                    obj.full_clean()
                    obj.save(update_fields=updated_fields)
                    saved = True
                results.append(dict(kind=field, id=obj.pk, file=getattr(obj, field).name, created=saved, sha256=r['sha256']))
        receipt = save_import_receipt(path, dict(input_sha256=hashlib.sha256(raw).hexdigest(), images=results))
        self.stdout.write(f'Attached {sum(r["created"] for r in results)} images; existing images preserved. Receipt: {receipt}')
