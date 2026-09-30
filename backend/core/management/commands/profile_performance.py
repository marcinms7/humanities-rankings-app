"""Measure allowlisted read-only screens without saving request bodies or responses."""
import json
from pathlib import Path
from statistics import median
from time import perf_counter

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.urls import resolve
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from backend.core.models import Ranking, User


class Command(BaseCommand):
    help = 'Profile allowlisted GET screens with SQLite writes disabled; output only costs and query plans.'

    def add_arguments(self, parser):
        parser.add_argument('--output')
        parser.add_argument('--repeats', type=int, default=3)
        parser.add_argument('--enforce', action='store_true', help='Fail when a measured screen exceeds its generous regression budget.')

    def handle(self, *args, **options):
        if connection.vendor != 'sqlite':
            raise CommandError('This local profiler requires SQLite query_only protection. Profile PostgreSQL on an isolated deployment.')
        repeats = options['repeats']
        if not 1 <= repeats <= 10:
            raise CommandError('Use 1 to 10 repeats.')
        factory = APIRequestFactory()
        with connection.cursor() as cursor:
            previous = cursor.execute('PRAGMA query_only').fetchone()[0]
            cursor.execute('PRAGMA query_only=ON')
        try:
            owner = User.objects.order_by('pk').first()
            ranking = Ranking.objects.filter(owner__isnull=True, is_archived=False, is_public=True).order_by('pk').first()
            paths = [('catalog', '/api/works/?compact=1'), ('catalog_search', '/api/works/?compact=1&search=Plato'),
                     ('authors_search', '/api/people/?search=Plato'), ('rankings', '/api/rankings/?summary=1'),
                     ('rankings_page', '/api/rankings/?summary=1&paged=1')]
            if ranking:
                paths.append(('ranking_entries', f'/api/ranking-browse/{ranking.pk}/'))
            country_ranking = Ranking.objects.filter(owner__isnull=True, is_archived=False, is_public=True,
                                                      scope__group_by='country').order_by('pk').first()
            if country_ranking:
                paths.append(('country_entries_page', f'/api/ranking-browse/{country_ranking.pk}/'))
            if owner:
                paths.extend([('library', '/api/library/?compact=1'), ('discovery', '/api/personal-discovery/'),
                              ('study_state', '/api/classical-education/?part=state'),
                              ('study_summary', '/api/classical-education/?part=summary'),
                              ('study_records', '/api/classical-education/?part=records&family=essays'),
                              ('recommendations', '/api/recommendations/')])
            results = []
            for label, path in paths:
                samples = []
                for _ in range(repeats):
                    queries = {'count': 0, 'ms': 0.0}
                    def measure(execute, sql, params, many, context):
                        began = perf_counter()
                        try:
                            return execute(sql, params, many, context)
                        finally:
                            queries['count'] += 1
                            queries['ms'] += (perf_counter() - began) * 1000
                    request = factory.get(path)
                    if owner:
                        force_authenticate(request, user=owner)
                    matched = resolve(request.path)
                    began = perf_counter()
                    with connection.execute_wrapper(measure):
                        response = matched.func(request, *matched.args, **matched.kwargs)
                        if hasattr(response, 'render'):
                            response.render()
                        size = len(response.content)
                    samples.append({'duration_ms': round((perf_counter() - began) * 1000, 2),
                                    'queries': queries['count'], 'sql_ms': round(queries['ms'], 2),
                                    'bytes': size, 'status': response.status_code})
                budget = {'warm_ms': 1500, 'queries': 60, 'bytes': 400_000}
                warm = samples[1:] or samples
                measured = {'warm_ms': round(median(row['duration_ms'] for row in warm), 2),
                            'queries': max(row['queries'] for row in warm), 'bytes': max(row['bytes'] for row in warm)}
                results.append({'screen': label, 'samples': samples, 'measured': measured, 'budget': budget,
                                'within_budget': all(measured[key] <= value for key, value in budget.items())
                                and all(row['status'] == 200 for row in samples)})
            from backend.core.library_queries import library_queryset
            plans = {'catalog_order': Ranking.objects.filter(is_public=True, is_archived=False).order_by('title', 'id').explain()}
            if owner:
                plans['library_order'] = library_queryset(owner, compact=True).explain()
            report = {'measured_at': timezone.now().isoformat(), 'repeats': repeats, 'read_only': True,
                      'scope': 'Local in-process GET preparation/render costs; no browser/network timing. First sample is cold; following samples warm. No private response contents saved.',
                      'screens': results, 'query_plans': plans}
        finally:
            with connection.cursor() as cursor:
                cursor.execute(f'PRAGMA query_only={int(previous)}')
        rendered = json.dumps(report, indent=2)
        if options['output']:
            output = Path(options['output'])
            output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            output.write_text(rendered + '\n')
            output.chmod(0o600)
            self.stdout.write(f'Measured {len(results)} screens; report saved to {output}.')
        else:
            self.stdout.write(rendered)
        failed = [row['screen'] for row in results if not row['within_budget']]
        if failed and options['enforce']:
            raise CommandError('Performance budget exceeded: ' + ', '.join(failed))
