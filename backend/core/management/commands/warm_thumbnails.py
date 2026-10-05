"""Prepare a bounded page of derived images without modifying catalog records."""
import json

from django.core.management.base import BaseCommand, CommandError
from django.http import Http404

from backend.core.models import Edition, Person
from backend.core.thumbnails import prepare_thumbnails


class Command(BaseCommand):
    help = 'Warm up to 500 existing cover or portrait previews; originals and database records are unchanged.'

    def add_arguments(self, parser):
        parser.add_argument('--kind', choices=['covers', 'portraits'], default='covers')
        parser.add_argument('--limit', type=int, default=100)
        parser.add_argument('--after-id', type=int, default=0)

    def handle(self, *args, **options):
        limit, after = options['limit'], options['after_id']
        if not 1 <= limit <= 500 or after < 0:
            raise CommandError('--limit must be between 1 and 500 and --after-id must be non-negative.')
        model, field = (Edition, 'cover') if options['kind'] == 'covers' else (Person, 'portrait')
        rows = list(model.objects.filter(pk__gt=after).exclude(**{field: ''})
                    .order_by('pk').values_list('pk', field)[:limit + 1])
        report = dict(kind=options['kind'], inspected=0, generated_images=0,
                      cached_images=0, failed_ids=[], derivatives_created=0,
                      next_after_id=after, has_more=len(rows) > limit)
        for record_id, filename in rows[:limit]:
            report['inspected'] += 1
            report['next_after_id'] = record_id
            try:
                _, _, created = prepare_thumbnails(filename)
            except (Http404, OSError, ValueError):
                report['failed_ids'].append(record_id)
                continue
            report['derivatives_created'] += created
            report['generated_images' if created else 'cached_images'] += 1
        self.stdout.write(json.dumps(report, sort_keys=True))
