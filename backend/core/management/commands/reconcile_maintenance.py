"""Conservative, repeatable provenance/snapshot backfill; never changes lengths."""
import json
from collections import Counter
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import transaction
from backend.core.models import Edition, LibraryItem, ReadingAttempt, PlanItem, Ranking, RankingRevision
from backend.core.reading_basis import capture_edition, capture_plan
from research.enrichment_queue import records

ROOT = Path(__file__).resolve().parents[4]


class Command(BaseCommand):
    help = 'Preview supported metadata and frozen reading assumptions; use --apply to persist.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        counts = Counter()
        pages = {}
        for row in records(ROOT / 'research/_runs/2026-09-15/catalog-page-counts/outcomes.jsonl'):
            if row.get('status') == 'found' and row.get('edition_id'):
                pages[row['edition_id']] = row
        covers = {}
        for row in records(ROOT / 'research/_runs/2026-09-13/catalog-public-cover-fallback/outcomes.jsonl'):
            if row.get('status') == 'covered' and row.get('edition_id'):
                covers[row['edition_id']] = row
        with transaction.atomic():
            for edition in Edition.objects.select_for_update().all().iterator():
                changes = {}
                row = pages.get(edition.pk)
                if (row and edition.work_id == row['work_id'] and edition.pages == row.get('pages')
                        and edition.pages_basis == 'unknown' and row.get('basis') in ('isbn_edition', 'openlibrary_edition_median')):
                    changes.update(pages_basis='isbn_matched' if row['basis'] == 'isbn_edition' else 'estimated_across_editions',
                                   pages_source_url=row.get('source_url', ''))
                    counts[changes['pages_basis']] += 1
                row = covers.get(edition.pk)
                if row and edition.work_id == row['work_id'] and edition.cover and edition.cover_basis == 'unknown':
                    marker = f"openlibrary-{row['cover_id']}" if row.get('cover_id') else f"internet-archive-{row['identifier']}" if row.get('identifier') else None
                    if marker and Path(edition.cover.name).stem.startswith(marker):
                        url = 'https://openlibrary.org' + row['source_key'] if row.get('source_key') else 'https://archive.org/details/' + row['identifier']
                        changes.update(cover_basis='representative_work', cover_source_url=url)
                        counts['representative_covers'] += 1
                if changes and options['apply']:
                    Edition.objects.filter(pk=edition.pk).update(**changes)
            for item in LibraryItem.objects.filter(reading_basis={}).select_related('edition', 'work__default_edition'):
                counts['library_snapshots'] += 1
                if options['apply']:
                    LibraryItem.objects.filter(pk=item.pk).update(reading_basis=capture_edition(item.edition or item.work.default_edition, 'current_metadata_at_upgrade'))
            for attempt in ReadingAttempt.objects.filter(reading_basis={}).select_related('edition'):
                counts['attempt_snapshots'] += 1
                if options['apply']:
                    ReadingAttempt.objects.filter(pk=attempt.pk).update(reading_basis=capture_edition(attempt.edition, 'current_metadata_at_upgrade_not_historical_verification'))
            for plan in PlanItem.objects.select_for_update(of=('self',)).filter(reading_basis={}).select_related('work__default_edition'):
                from backend.core.reading_workflow import allocation_has_history
                if allocation_has_history(plan):
                    # A current edition cannot stand in for an unknown saved
                    # basis behind measured reading or a carryover receipt.
                    counts['plan_history_basis_unresolved'] += 1
                    continue
                counts['plan_snapshots'] += 1
                if options['apply']:
                    basis = capture_plan(plan.work, plan.user_id)
                    basis['origin'] = 'current_metadata_at_upgrade'
                    PlanItem.objects.filter(pk=plan.pk).update(reading_basis=basis)
            # Recover grouping only from the exact copied revision, never today's source.
            from backend.core.views import ensure_revision, save_revision
            for ranking in Ranking.objects.filter(origin='personal', scope__group_by='country'):
                revision = RankingRevision.objects.filter(ranking_id=ranking.scope.get('copied_from'), number=ranking.scope.get('copied_revision')).first()
                if not revision:
                    counts['copies_without_exact_revision'] += 1
                    continue
                originals = {row['work_id']: row.get('groupings', []) for row in revision.snapshot.get('entries', []) if not row.get('is_archived')}
                repairs = [(e, originals[e.work_id]) for e in ranking.entries.filter(is_archived=False)
                           if not e.groupings and originals.get(e.work_id)]
                if repairs:
                    counts['copy_groupings'] += len(repairs)
                    if options['apply']:
                        ensure_revision(ranking)
                        for entry, groupings in repairs:
                            entry.groupings = groupings; entry.save(update_fields=['groupings'])
                        for key in ('source_record_count', 'position_count'):
                            ranking.scope.pop(key, None)
                        save_revision(ranking, 'Restored country provenance from the exact copied source revision; personal order preserved')
        self.stdout.write(json.dumps({'applied': options['apply'], 'changes': counts}, indent=2))
