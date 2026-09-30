"""Import a reviewed named publisher list while preserving its source order."""
import hashlib
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from backend.core.models import Ranking, RankingEntry, Work
from backend.core.management.receipts import save_import_receipt
from backend.core.views import ensure_revision, save_revision


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('path')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        path = Path(options['path'])
        raw = path.read_bytes()
        batch = json.loads(raw)
        with transaction.atomic():
            ranking = Ranking.objects.select_for_update().get(slug=batch['target'])
            if ranking.origin != 'external' or ranking.owner_id or ranking.is_archived:
                raise CommandError('Target must be an active shared external list.')
            if ranking.presentation != batch['presentation']:
                raise CommandError('Presentation does not match the named source definition.')
            if ranking.revision != batch['expected_revision']:
                raise CommandError('Revision conflict; nothing written.')
            records = batch['entries']
            ids = [r['work_id'] for r in records]
            if not records or len(ids) != len(set(ids)):
                raise CommandError('Entries must be nonempty and unique.')
            prepared = []
            for position, record in enumerate(records, 1):
                work = Work.objects.get(pk=record['work_id'], is_archived=False)
                entry = ranking.entries.filter(work=work).first() or RankingEntry(ranking=ranking, work=work)
                entry.position = position
                entry.source_rank = record.get('source_rank') if ranking.presentation == 'ranked' else None
                entry.rationale = record.get('note', '')
                entry.is_archived = False
                entry.full_clean()
                prepared.append(entry)
            omitted = ranking.entries.filter(is_archived=False).exclude(work_id__in=ids)
            if omitted.exists() and not batch.get('allow_reviewed_replacement'):
                raise CommandError('Existing entries require explicit reviewed replacement.')
            if options['dry_run']:
                self.stdout.write(f'Validated {len(prepared)} entries; no writes.')
                return
            ensure_revision(ranking)
            omitted.update(is_archived=True)
            for entry in prepared:
                entry.save()
            ranking.status = batch['status']
            ranking.scope = {**ranking.scope, 'external_import': {
                'input_sha256': hashlib.sha256(raw).hexdigest(),
                'source_checked_on': batch['source_checked_on'],
                'entry_count': len(prepared),
                'unresolved_count': batch.get('unresolved_count', 0),
                'method_note': batch['method_note'],
            }}
            save_revision(ranking, f"Faithful source-list import: {len(prepared)} resolved entries.")
        save_import_receipt(path, {'input_sha256': hashlib.sha256(raw).hexdigest(), 'ranking_id': ranking.pk,
                                  'revision': ranking.revision, 'entry_count': len(prepared)})
        self.stdout.write(f'Imported {len(prepared)} entries into {ranking.slug}, revision {ranking.revision}.')
