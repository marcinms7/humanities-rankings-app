import json
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from backend.core.models import Ranking, ResearchSource


class Command(BaseCommand):
    help = 'Persist a saved evidence ledger into exactly its named ranking. Existing evidence is preserved unless --update-existing is passed.'

    def add_arguments(self, parser):
        parser.add_argument('ledger', type=Path)
        parser.add_argument('--target', required=True, help='Existing ranking slug; must exactly match ledger target_id.')
        parser.add_argument('--update-existing', action='store_true', help='Explicitly replace existing source evidence with this reviewed ledger; never deletes sources.')

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            ledger = json.loads(options['ledger'].read_text())
        except (OSError, ValueError) as error:
            raise CommandError(f'Cannot read ledger: {error}') from error
        target = options['target']
        if not isinstance(ledger, dict) or ledger.get('target_id') != target:
            raise CommandError('Ledger target_id must exactly match --target. Sources are never copied to other targets automatically.')
        if ledger.get('ranking_entries'):
            raise CommandError('This command imports research evidence only. Ranking entry imports need separate review.')
        sources = ledger.get('sources')
        if not isinstance(sources, list):
            raise CommandError('Ledger sources must be a list.')
        try:
            ranking = Ranking.objects.get(slug=target, origin='curated', owner__isnull=True, is_archived=False)
        except Ranking.DoesNotExist as error:
            raise CommandError('Create the shared curated ranking definition first; personal and external lists cannot receive this synthesis import.') from error
        prepared = []
        ids, underlying_ids = set(), set()
        for source in sources:
            if not isinstance(source, dict):
                raise CommandError('Each source must be an object.')
            source_id = source.get('source_id')
            underlying = source.get('underlying_source_id')
            if not isinstance(source_id, str) or not source_id or source_id in ids:
                raise CommandError('Every source needs a distinct nonempty source_id.')
            if not isinstance(underlying, str) or not underlying or underlying in underlying_ids:
                raise CommandError(f'{source_id}: repeated or missing underlying_source_id; deduplicate mirrors and reprints first.')
            ids.add(source_id)
            underlying_ids.add(underlying)
            target_ids = source.get('target_ids', [])
            relevance_map = source.get('relevance_by_target', {})
            relevance = relevance_map.get(target) if isinstance(relevance_map, dict) else None
            if not isinstance(target_ids, list) or target not in target_ids or not isinstance(relevance, str) or not relevance.strip():
                raise CommandError(f'{source_id}: explicit relevance for this exact target is required.')
            eligible = source.get('count_eligible', False)
            if not isinstance(eligible, bool):
                raise CommandError(f'{source_id}: count_eligible must be true or false.')
            access_level = source.get('access_level')
            evidence = source.get('evidence_notes', '')
            if not isinstance(evidence, str):
                raise CommandError(f'{source_id}: evidence_notes must be text.')
            if eligible and (access_level not in {'full_relevant_content', 'full_content', 'relevant_excerpt', 'abstract_only', 'summary_only'} or not evidence.strip()):
                raise CommandError(f'{source_id}: counted evidence needs examined content, access limitations and an evidence note.')
            raw_date = source.get('accessed_at')
            try:
                consulted_on = date.fromisoformat(raw_date) if raw_date else None
            except (TypeError, ValueError) as error:
                raise CommandError(f'{source_id}: accessed_at must be a YYYY-MM-DD date.') from error
            if eligible and consulted_on is None:
                raise CommandError(f'{source_id}: counted sources need an access date.')
            url = source.get('canonical_url', '')
            if not isinstance(url, str) or urlparse(url).scheme not in {'https', 'http'} or not urlparse(url).netloc:
                raise CommandError(f'{source_id}: supply a complete HTTP(S) canonical_url.')
            values = {'source_id': source_id, 'title': source.get('title', ''), 'url': url,
                      'family': source.get('source_family', ''), 'publisher': source.get('publisher') or '',
                      'evidence': evidence, 'limitations': source.get('disagreement_or_limitations') or '',
                      'consulted_on': consulted_on, 'eligible': eligible, 'metadata': source}
            prepared.append((underlying, values))
        known_ids = ids | set(ranking.sources.values_list('source_id', flat=True))
        for source in sources:
            dependencies = source.get('depends_on_source_ids', [])
            if not isinstance(dependencies, list) or any(not isinstance(item, str) or item not in known_ids for item in dependencies):
                raise CommandError(f'{source["source_id"]}: dependency IDs must refer to sources saved for this same target or included in this ledger.')
            if source['source_id'] in dependencies:
                raise CommandError(f'{source["source_id"]}: a source cannot depend on itself.')
        created = updated = preserved = 0
        for underlying, values in prepared:
            existing = ResearchSource.objects.filter(ranking=ranking, underlying_source_id=underlying).first()
            if existing and existing.source_id != values['source_id']:
                raise CommandError(f'Underlying source {underlying} already has a different stable source_id.')
            if existing and not options['update_existing']:
                preserved += 1
                continue
            source = existing or ResearchSource(ranking=ranking, underlying_source_id=underlying)
            for field, value in values.items():
                setattr(source, field, value)
            try:
                source.full_clean()
            except ValidationError as error:
                raise CommandError(f'{values["source_id"]}: {error}') from error
            source.save()
            if existing:
                updated += 1
            else:
                created += 1
        if created and ranking.status == 'awaiting_research':
            ranking.status = 'collecting'
            ranking.save(update_fields=['status', 'updated_at'])
        count = ranking.sources.filter(eligible=True, is_archived=False).count()
        self.stdout.write(self.style.SUCCESS(f'{target}: added {created}, updated {updated}, preserved {preserved}; {count} eligible sources in this target only.'))
        self.stdout.write('Partial imports do not publish a ranking, finish its research, or reset research freshness. Review relevance, independence and diversity separately.')
