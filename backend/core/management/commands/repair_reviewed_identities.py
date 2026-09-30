"""Only the four reviewed reciprocal title/author errors; no fuzzy merging."""
import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from backend.core.models import Work, Person, Ranking, RankingEntry
from backend.core.views import ensure_revision, save_revision

REPAIRS = [(1802, 'Mary Beard', 'SPQR: A History of Ancient Rome', 2706),
           (1834, 'Mary Beard', 'Pompeii: The Life of a Roman Town', None),
           (2176, 'Mary Beard', 'The Roman Triumph', None),
           (8330, 'Agustina Bazterrica', 'Tender Is the Flesh (Cadáver exquisito)', 1427)]


class Command(BaseCommand):
    help = 'Preview four reviewed reciprocal identity corrections; --apply saves revisions and an audit receipt.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        changes = []
        with transaction.atomic():
            for wrong_id, author, title, canonical_id in REPAIRS:
                wrong = Work.objects.select_for_update().get(pk=wrong_id)
                names = list(wrong.authors.values_list('name', flat=True))
                if wrong.title == title and names == [author]:
                    continue
                if wrong.title != author or names != [title]:
                    raise CommandError(f'Identity {wrong_id} no longer matches the reviewed input; aborting.')
                correct = Work.objects.get(pk=canonical_id, is_archived=False) if canonical_id else wrong
                if canonical_id and not correct.authors.filter(name=author).exists():
                    raise CommandError('Canonical author changed; aborting.')
                entries = list(RankingEntry.objects.filter(work=wrong, ranking__origin__in=['curated', 'external'], is_archived=False))
                rankings = list(Ranking.objects.select_for_update().filter(pk__in=[e.ranking_id for e in entries]))
                # A collision needs a separate order/override reconciliation, not silent loss.
                if canonical_id and RankingEntry.objects.filter(ranking_id__in=[r.pk for r in rankings], work=correct).exists():
                    raise CommandError(f'Canonical entry collision for {wrong_id}; review required.')
                changes.append({'work_id': wrong_id, 'before': {'title': wrong.title, 'authors': names},
                                'after': {'title': title, 'authors': [author]}, 'shared_work_id': correct.pk,
                                'rankings': [r.slug for r in rankings], 'private_references': 'unchanged'})
                if not options['apply']:
                    continue
                for ranking in rankings:
                    ensure_revision(ranking)
                people = list(Person.objects.filter(name=author, is_archived=False))
                if len(people) != 1:
                    raise CommandError(f'Ambiguous canonical person {author}; aborting.')
                wrong.title = title
                wrong.is_archived = bool(canonical_id)
                wrong.save(update_fields=['title', 'is_archived', 'updated_at'])
                wrong.authors.set(people)
                for entry in entries:
                    if canonical_id:
                        entry.work = correct; entry.save(update_fields=['work'])
                for ranking in rankings:
                    editorial = ranking.scope.get('editorial') or {}
                    for order in editorial.get('orders', {}).values():
                        order['item_ids'] = [correct.pk if value == wrong_id else value for value in order.get('item_ids', [])]
                    explanations = editorial.get('entries', {})
                    if str(wrong_id) in explanations and wrong_id != correct.pk:
                        explanations[str(correct.pk)] = explanations.pop(str(wrong_id))
                    save_revision(ranking, f'Reviewed reciprocal author/title correction for work {wrong_id}; source positions and private references preserved')
            if options['apply'] and changes:
                directory = Path('research/_runs/2026-09-27/maintenance')
                directory.mkdir(parents=True, exist_ok=True)
                # Write before commit so a failed receipt write rolls back the repair.
                receipt = directory / f'identities-{timezone.now().strftime("%Y%m%dT%H%M%S%fZ")}.json'
                receipt.write_text(json.dumps(changes, ensure_ascii=False, indent=2) + '\n')
        self.stdout.write(json.dumps({'applied': options['apply'], 'repairs': changes}, ensure_ascii=False, indent=2))
