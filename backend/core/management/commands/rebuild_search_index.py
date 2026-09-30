from django.core.management.base import BaseCommand, CommandError
from backend.core.search import index_path, index_status, rebuild_index, sync_index


class Command(BaseCommand):
    help = 'Rebuild the disposable catalog search index, reconcile changed documents, or inspect freshness.'

    def add_arguments(self, parser):
        parser.add_argument('--database', default='default')
        action = parser.add_mutually_exclusive_group()
        action.add_argument('--check', action='store_true')
        action.add_argument('--sync', action='store_true', help='Compare catalog content and update only changed search documents.')

    def handle(self, *args, **options):
        using = options['database']
        try:
            result = index_status(using) if options['check'] else sync_index(using, reconcile=True) if options['sync'] else rebuild_index(using)
        except (OSError, ValueError) as error:
            raise CommandError(str(error)) from error
        self.stdout.write(f"Search index: {index_path(using)}")
        self.stdout.write(str(result))
