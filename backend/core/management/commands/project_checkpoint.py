"""Dated current-state report from the configured DB; no catalog/private writes."""
import json
from collections import Counter
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from django.utils import timezone
from backend.core.models import Work, Person, Edition, Ranking, RankingEntry, ResearchSource
from backend.core.evidence_provenance import source_provenance, order_status


class Command(BaseCommand):
    help = 'Refresh docs/CURRENT_STATE.md and a public metadata backlog from actual saved records.'

    def handle(self, *args, **options):
        now = timezone.now().isoformat(timespec='seconds')
        works = Work.objects.filter(is_archived=False).select_related('default_edition').prefetch_related('authors', 'editions')
        people = Person.objects.filter(is_archived=False)
        shared = list(Ranking.objects.filter(is_archived=False).exclude(origin='personal').order_by('slug'))
        ids = [ranking.pk for ranking in shared]
        entry_counts = dict(RankingEntry.objects.filter(ranking_id__in=ids, is_archived=False).order_by().values('ranking_id').annotate(total=Count('pk')).values_list('ranking_id', 'total'))
        source_counts = {row['ranking_id']: row for row in ResearchSource.objects.filter(ranking_id__in=ids, is_archived=False).order_by().values('ranking_id').annotate(retained=Count('pk'), eligible=Count('pk', filter=Q(eligible=True)))}
        for ranking in shared:
            ranking.active_entries = entry_counts.get(ranking.pk, 0)
            ranking.retained = source_counts.get(ranking.pk, {}).get('retained', 0)
            ranking.eligible = source_counts.get(ranking.pk, {}).get('eligible', 0)
        rows = [dict(slug=r.slug, title=r.title, entries=r.active_entries, retained_sources=r.retained,
                     eligible_records=r.eligible, revision=r.revision, origin=r.origin, presentation=r.presentation,
                     order_status=order_status(r)) for r in shared]
        backlog = []
        for work in works:
            edition = work.default_edition
            missing = []
            if not edition or not edition.cover: missing.append('cover')
            if not edition or not edition.pages: missing.append('page_count')
            if not edition or not edition.isbn: missing.append('edition_identifier')
            if edition and edition.pages and edition.pages_basis in ('unknown', 'estimated_across_editions'):
                missing.append('edition_length_verification')
            if not work.authors.exists(): missing.append('authorship_review')
            if missing:
                options = [e.pk for e in work.editions.all() if not e.is_archived and e.language == 'English'
                           and e.isbn and e.pages and e.pages_basis == 'isbn_matched']
                backlog.append(dict(work_id=work.pk, title=work.title, tasks=missing,
                                    isbn_matched_english_options=options))
        sources = ResearchSource.objects.filter(is_archived=False, ranking__is_archived=False).exclude(ranking__origin='personal')
        origins, access, roles = Counter(), Counter(), Counter()
        for source in sources.iterator():
            p = source_provenance(source)
            origins[p['consultation_origin']] += 1
            access[str(p['access_extent'])] += 1
            roles[str(p['evidence_role'])] += 1
        english_options = Edition.objects.filter(is_archived=False, work__is_archived=False,
                                                language='English', pages_basis='isbn_matched', pages__isnull=False).exclude(isbn='')
        counts = dict(active_works=works.count(), active_people=people.count(), editions=Edition.objects.filter(is_archived=False).count(),
                      default_covers=works.exclude(default_edition__cover='').filter(default_edition__cover__isnull=False).count(),
                      default_page_counts=works.filter(default_edition__pages__isnull=False).count(),
                      portraits=people.exclude(portrait='').count(), shared_lists=len(rows),
                      isbn_matched_english_editions=english_options.count(),
                      works_with_isbn_matched_english_options=english_options.values('work_id').distinct().count(),
                      retained_source_records=sources.count(), eligible_source_records=sources.filter(eligible=True).count())
        report = dict(captured_at=now, counts=counts, source_origins=origins, access_extents=access, evidence_roles=roles,
                      rankings=rows, metadata_tasks=backlog,
                      portraits_needed=list(people.filter(portrait='').values_list('pk', flat=True)))
        directory = Path('research/_runs/current-state'); directory.mkdir(parents=True, exist_ok=True)
        (directory / 'checkpoint.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        lines = ['# Current saved state', '', f'Database snapshot: **{now}**. Refresh with `manage.py project_checkpoint`.', '',
                 'This dated report supersedes counts and pending-import statements in historical receipts. Counts can change during owner-file intake. It does not certify editorial or bibliographic completeness.', '',
                 '| Measure | Saved count |', '| --- | ---: |']
        lines += [f'| {key.replace("_", " ")} | {value:,} |' for key, value in counts.items()]
        lines += ['', 'Source totals are target-local ledger records, including supplied-report consultations and reused sources. Eligibility does not establish an independent judgment or full-text verification. Page medians across editions remain estimates. Matching standing/reading orders are explicitly labelled in the app; new orders require evidence and editorial work.', '',
                  'The [machine-readable checkpoint and unresolved media/edition tasks](../research/_runs/current-state/checkpoint.json) preserve explicit outstanding work. Missing images never gate ranking membership.', '',
                  'Metadata tasks describe the default/display edition. ISBN-matched English alternatives are recorded separately; adding an option does not change a reader’s selected edition or establish translation quality/completeness.', '',
                  '| Ranking | Entries | Eligible / retained records | Revision |', '| --- | ---: | ---: | ---: |']
        lines += [f'| {r["slug"]} | {r["entries"]} | {r["eligible_records"]} / {r["retained_sources"]} | {r["revision"]} |' for r in rows]
        Path('docs/CURRENT_STATE.md').write_text('\n'.join(lines) + '\n')
        self.stdout.write(json.dumps(counts, indent=2))
