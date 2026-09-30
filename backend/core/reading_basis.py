"""Frozen edition/length assumptions for private progress, history and plans."""
from types import SimpleNamespace
from django.utils import timezone
from backend.domain.reading_capacity import effort_per_page

EDITION_FIELDS = ('pages', 'word_count', 'pages_basis', 'pages_source_url', 'isbn',
                  'language', 'translator', 'publisher', 'abridged')
LABELS = {'unknown': 'Page-count basis not recorded', 'isbn_matched': 'Pages from an ISBN-matched provider record',
          'estimated_across_editions': 'Approximate pages across editions', 'manually_recorded': 'Manually recorded pages'}


def capture_edition(edition, origin='selected'):
    return {'edition_id': edition.pk if edition else None,
            **{key: getattr(edition, key, None) for key in EDITION_FIELDS},
            'captured_at': timezone.now().isoformat(), 'origin': origin}


def comparable(basis):
    return {key: basis.get(key) for key in ('edition_id', *EDITION_FIELDS)}


def length_edition(item):
    if item.reading_basis:
        return SimpleNamespace(**{key: item.reading_basis.get(key) for key in EDITION_FIELDS},
                               pk=item.reading_basis.get('edition_id'))
    return item.edition or item.work.default_edition


def needs_review(item):
    return bool(item.reading_basis and comparable(item.reading_basis) != comparable(
        capture_edition(item.edition or item.work.default_edition)))


def capture_plan(work, user_id):
    from .models import LibraryItem
    item = LibraryItem.objects.filter(user_id=user_id, work=work).select_related('edition', 'work__default_edition').first()
    edition = length_edition(item) if item else work.default_edition
    basis = dict(item.reading_basis) if item and item.reading_basis else capture_edition(edition)
    basis.update(effort_multiplier=effort_per_page(work, edition), allocated_at=timezone.now().isoformat())
    return basis


def plan_effort(plan, user):
    if not user.difficulty_aware_planning:
        return 1.0
    if plan.reading_basis.get('effort_multiplier') is not None:
        return plan.reading_basis['effort_multiplier']
    return capture_plan(plan.work, user.pk)['effort_multiplier']


def plan_needs_review(plan, current):
    return bool(plan.reading_basis and (
        comparable(plan.reading_basis) != comparable(current) or
        plan.reading_basis.get('effort_multiplier') != current.get('effort_multiplier')))
