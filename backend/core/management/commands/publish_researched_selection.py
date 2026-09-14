"""Publish an explicitly reviewed initial selection with two qualitative orders."""
import hashlib
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from backend.core.models import Ranking, RankingEntry, Work, Person
from backend.core.views import ensure_revision, save_revision


class Command(BaseCommand):
    help = 'Publish a reviewed first selection; preserve revisions, evidence and private data.'

    def add_arguments(self, parser):
        parser.add_argument('path')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        path = Path(options['path'])
        raw = path.read_bytes()
        batch = json.loads(raw)
        digest = hashlib.sha256(raw).hexdigest()
        with transaction.atomic():
            ranking = Ranking.objects.select_for_update().get(slug=batch['target'])
            if ranking.origin != 'curated' or ranking.owner_id or ranking.is_archived:
                raise CommandError('Only an active shared researched ranking can receive this publication.')
            existing = ranking.scope.get('editorial', {})
            if existing.get('input_sha256') == digest:
                self.stdout.write('This exact selection is already published; no changes.')
                return
            if ranking.revision != batch['expected_revision'] or ((ranking.entries.exists() or existing) and not batch.get('allow_expansion')):
                raise CommandError('Existing entries/revision require a separately reviewed update; nothing overwritten.')
            if ranking.sources.filter(eligible=True, is_archived=False).count() < 50:
                raise CommandError('The target must have at least 50 eligible consulted sources.')
            records = batch['entries']
            keys = [r['key'] for r in records]
            if not keys or len(keys) != len(set(keys)):
                raise CommandError('Selection keys must be nonempty and unique.')
            for lens in ['standing', 'reading']:
                order = batch['orders'][lens]['keys']
                if len(order) != len(keys) or set(order) != set(keys):
                    raise CommandError('Both orders must be permutations of the same selection.')
            prepared, explanations, item_ids = {}, {}, {}
            for record in records:
                model = Work if ranking.item_type == 'work' else Person
                obj = model.objects.get(pk=record['item_id'], is_archived=False)
                if obj.pk in item_ids.values():
                    raise CommandError('Duplicate catalog identity.')
                if ranking.item_type == 'work' and not obj.authors.exists() and not ranking.scope.get('allow_unresolved_attribution'):
                    raise CommandError('A book must have a resolved author identity.')
                if not batch.get('allow_pending_metadata'):
                    if ranking.item_type == 'work':
                        edition = obj.default_edition
                        if not edition or edition.is_archived or edition.abridged or edition.language != 'English' or not edition.cover:
                            raise CommandError('Complete English edition and cover required unless pending metadata is explicit.')
                        if any(not p.portrait or p.is_archived for p in obj.authors.all()):
                            raise CommandError('Author portrait missing.')
                    elif not obj.portrait:
                        raise CommandError('Person portrait missing.')
                source_ids = record['source_ids']
                sources = ranking.sources.filter(source_id__in=source_ids, eligible=True, is_archived=False)
                if not source_ids or sources.count() != len(set(source_ids)):
                    raise CommandError('Entry evidence must resolve to this target’s consulted sources.')
                reported_source_ids = record.get('reported_source_ids', source_ids)
                if (not isinstance(reported_source_ids, list) or not reported_source_ids
                        or any(not isinstance(source_id, str) for source_id in reported_source_ids)):
                    raise CommandError('Reported source IDs must be a nonempty list of stable source IDs.')
                reported_sources = ranking.sources.filter(source_id__in=reported_source_ids, is_archived=False)
                if reported_sources.count() != len(set(reported_source_ids)):
                    raise CommandError('Every reported source must resolve to an active source in this target.')
                if not all(record.get(k, '').strip() for k in ['standing', 'reading', 'caveat']):
                    raise CommandError('Both placement explanations and a limitation are required.')
                item_ids[record['key']] = obj.pk
                explanations[str(obj.pk)] = {k: record[k] for k in ['standing', 'reading', 'caveat']}
                explanations[str(obj.pk)]['sources'] = [dict(source_id=s.source_id, title=s.title, url=s.url) for s in sources]
                additional_reported = reported_sources.exclude(source_id__in=source_ids)
                if additional_reported.exists():
                    explanations[str(obj.pk)]['reported_sources'] = [dict(source_id=s.source_id, title=s.title, url=s.url,
                                                                            eligible=s.eligible)
                                                                      for s in additional_reported]
                for supplement in record.get('supplementary_sources', []):
                    if supplement['source_id'] not in source_ids or not supplement['url'].startswith('https://'):
                        raise CommandError('Supplement must identify an existing consulted source and HTTPS manifestation.')
                    explanations[str(obj.pk)]['sources'].append(supplement)
                entry = ranking.entries.filter(**{ranking.item_type: obj}).first()
                if entry is None:
                    entry = RankingEntry(ranking=ranking, **{ranking.item_type: obj}, source_rank=None, assessments={})
                entry.position = batch['orders']['standing']['keys'].index(record['key']) + 1
                entry.rationale = record['standing']
                entry.is_archived = False
                explanations[str(obj.pk)]['metadata_status'] = record.get('metadata_status', 'complete')
                explanations[str(obj.pk)]['source_positions'] = record.get('source_positions', [])
                entry.full_clean()
                prepared[record['key']] = entry
            previous_ids = set(ranking.entries.filter(is_archived=False).values_list(ranking.item_type + '_id', flat=True))
            omitted = previous_ids - set(item_ids.values())
            exclusions = batch.get('reviewed_exclusions', [])
            if omitted != {r['item_id'] for r in exclusions} or any(not r.get('reason', '').strip() for r in exclusions):
                raise CommandError('Every removed identity requires an explicit reviewed exclusion reason; nothing deleted.')
            editorial = dict(version=batch['version'], published_on=batch['published_on'], notice=batch['notice'], method=batch['method'], input_sha256=digest, entries=explanations,
                             orders={lens: dict(label=order['label'], description=order['description'], item_ids=[item_ids[k] for k in order['keys']]) for lens, order in batch['orders'].items()})
            editorial['reviewed_exclusions'] = exclusions
            if options['dry_run']:
                self.stdout.write(f'Validated {len(prepared)} entries and both orders for {ranking.slug}; no writes.')
                return
            ensure_revision(ranking)
            for entry in ranking.entries.filter(**{ranking.item_type + '_id__in': omitted}):
                entry.is_archived = True
                entry.save(update_fields=['is_archived'])
            for key in batch['orders']['standing']['keys']:
                prepared[key].save()
            ranking.scope = {**ranking.scope, 'editorial': editorial}
            ranking.status = 'initial_selection'
            # Partial publication is not a completed global research refresh.
            ranking.full_clean()
            save_revision(ranking, f'Researched selection: {len(prepared)} entries, critical standing and reading value. Personal scores unset.')
        receipt = path.with_name(path.stem + '-import-receipt.json')
        receipt.write_text(json.dumps(dict(input_sha256=digest, ranking_id=ranking.pk, revision=ranking.revision, entry_count=len(prepared), entry_ids={key: entry.pk for key, entry in prepared.items()}), indent=2) + '\n')
        self.stdout.write(f'Published {len(prepared)} entries in {ranking.slug}, revision {ranking.revision}. Receipt: {receipt}')
