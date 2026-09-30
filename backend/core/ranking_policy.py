"""Reader editing and portable presentation of personal ranking copies."""
from copy import deepcopy


def can_edit_ranking(ranking, user):
    return bool(user.is_authenticated and ranking.origin == 'personal' and ranking.owner_id == user.pk)


def display_scope(ranking, entries):
    """Public-safe display metadata; inherited research totals are not live totals."""
    if ranking.scope.get('group_by') != 'country':
        return {}
    return {'group_by': 'country', 'position_count': sum(len(e.groupings) for e in entries)}


def copy_scope(original):
    scope = deepcopy(original.scope)
    # Evidence remains attached to the original target, not a new research claim.
    for key in ('source_record_count', 'position_count', 'editorial'):
        scope.pop(key, None)
    scope.update(copied_from=original.pk, copied_revision=original.revision,
                 copied_source_title=original.title, copied_source_slug=original.slug)
    return scope
