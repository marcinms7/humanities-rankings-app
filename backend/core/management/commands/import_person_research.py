"""Import reviewed person identities with target-local provenance, preserving existing rows."""
import hashlib
import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from backend.core.models import Person, ResearchSource


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('path')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        path = Path(options['path'])
        raw = path.read_bytes()
        batch = json.loads(raw)
        results = []
        names = set()
        with transaction.atomic():
            for r in batch['people']:
                if r['name'].casefold() in names:
                    raise CommandError('Duplicate person identity in batch.')
                names.add(r['name'].casefold())
                sources = ResearchSource.objects.filter(ranking__slug=batch['target'], source_id__in=r['source_ids'], eligible=True, is_archived=False)
                if not r['source_ids'] or sources.count() != len(set(r['source_ids'])):
                    raise CommandError('Person evidence must resolve to target-local consulted sources.')
                matches = Person.objects.filter(name__iexact=r['name'])
                if matches.count() > 1 or matches.filter(is_archived=True).exists():
                    raise CommandError('Ambiguous or archived person; resolve manually.')
                obj = matches.first()
                created = obj is None
                if created:
                    obj = Person(name=r['name'], biography=r['biography'], source_url=r['source_url'])
                    obj.full_clean()
                    if not options['dry_run']:
                        obj.save()
                results.append(dict(key=r['key'], person_id=obj.pk, created=created))
        if options['dry_run']:
            self.stdout.write(f'Validated {len(results)} reviewed people; no writes.')
            return
        receipt = path.with_name(path.stem + '-import-receipt.json')
        if not receipt.exists():
            receipt.write_text(json.dumps(dict(input_sha256=hashlib.sha256(raw).hexdigest(), records=results), indent=2) + '\n')
        self.stdout.write(f'Imported {sum(r["created"] for r in results)} people; existing people preserved. Receipt: {receipt}')
