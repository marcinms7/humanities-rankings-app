"""Bounded, additive actions on selected books in a reader's private data."""
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from .catalog_cache import invalidate_catalog
from .models import LibraryItem, Ranking, RankingEntry, Work
from .reading_basis import capture_edition
from .serializers import string_list


ACTIONS = ['library', 'read_next', 'personal_list', 'shelves', 'personal_tags']


class PositiveID(serializers.IntegerField):
    def __init__(self, **kwargs):
        super().__init__(min_value=1, max_value=2**63 - 1, **kwargs)

    def to_internal_value(self, data):
        if type(data) is not int:
            self.fail('invalid')
        return super().to_internal_value(data)


class Label(serializers.CharField):
    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail('invalid')
        return super().to_internal_value(data)


class BulkBookActionCommand(serializers.Serializer):
    work_ids = serializers.ListField(child=PositiveID(), min_length=1, max_length=200)
    action = serializers.ChoiceField(choices=ACTIONS)
    ranking_id = PositiveID(required=False)
    expected_revision = PositiveID(required=False)
    values = serializers.ListField(child=Label(max_length=100), min_length=1, max_length=50, required=False)

    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) - set(self.fields):
            raise ValidationError({'non_field_errors': ['Use only the fields for this selected-book action.']})
        return super().to_internal_value(data)

    def validate_work_ids(self, value):
        return list(dict.fromkeys(value))

    def validate_values(self, value):
        return string_list(value)

    def validate(self, attrs):
        action = attrs['action']
        if action == 'personal_list':
            if 'ranking_id' not in attrs:
                raise ValidationError({'ranking_id': 'Choose one of your private book lists.'})
        elif 'ranking_id' in attrs or 'expected_revision' in attrs:
            raise ValidationError('A list and revision apply only to the personal-list action.')
        if action in {'shelves', 'personal_tags'}:
            if not attrs.get('values'):
                raise ValidationError({'values': 'Enter at least one shelf or tag name.'})
        elif 'values' in attrs:
            raise ValidationError({'values': 'Names apply only when adding shelves or tags.'})
        return attrs


class BulkBookActionResult(serializers.Serializer):
    action = serializers.ChoiceField(choices=ACTIONS)
    selected_count = serializers.IntegerField()
    added_to_library = serializers.IntegerField()
    added_to_read_next = serializers.IntegerField()
    added_to_list = serializers.IntegerField()
    updated_labels = serializers.IntegerField()
    unchanged_count = serializers.IntegerField()
    ranking_id = serializers.IntegerField(allow_null=True)
    revision = serializers.IntegerField(allow_null=True)


@transaction.atomic
def apply_bulk_action(request, command):
    """Append under the ordinary account lock; never replace saved field values.

    LibraryViewSet's mutation guard retains the response and all these writes in
    one transaction for retries. The same account lock also protects requests
    from older clients without an idempotency key.
    """
    from .views import check_revision, ensure_revision, save_revision

    get_user_model().objects.select_for_update().get(pk=request.user.pk)
    ids, action = command['work_ids'], command['action']
    works = {work.pk: work for work in Work.objects.filter(pk__in=ids, is_archived=False).select_related('default_edition')}
    if len(works) != len(ids):
        raise ValidationError({'work_ids': 'Every selected book must still be active in the catalog. Refresh your selection.'})
    result = dict(action=action, selected_count=len(ids), added_to_library=0,
                  added_to_read_next=0, added_to_list=0, updated_labels=0,
                  unchanged_count=0, ranking_id=None, revision=None)

    if action == 'personal_list':
        ranking = Ranking.objects.select_for_update().filter(
            pk=command['ranking_id'], owner=request.user, origin='personal',
            item_type='work', is_archived=False, sharing_enabled=False).first()
        if ranking is None:
            raise ValidationError({'ranking_id': 'Choose one of your active, private book lists.'})
        check_revision(ranking, request)
        if ranking.scope.get('forms') and any(works[pk].form not in ranking.scope['forms'] for pk in ids):
            raise ValidationError({'work_ids': 'One or more selected books fall outside this list’s form scope.'})
        existing = dict(ranking.entries.filter(work_id__in=ids).values_list('work_id', 'is_archived'))
        if any(existing.values()):
            raise ValidationError({'work_ids': 'A selected book has an archived entry in this list. Review that entry before adding it again.'})
        missing = [pk for pk in ids if pk not in existing]
        if missing:
            ensure_revision(ranking)
            position = ranking.entries.aggregate(last=Max('position'))['last'] or 0
            RankingEntry.objects.bulk_create([
                RankingEntry(ranking=ranking, work=works[pk], position=position + offset)
                for offset, pk in enumerate(missing, 1)
            ])
            save_revision(ranking, f'Added {len(missing)} selected books')
        result.update(added_to_list=len(missing), unchanged_count=len(ids) - len(missing),
                      ranking_id=ranking.pk, revision=ranking.revision)
        return result

    library = {item.work_id: item for item in LibraryItem.objects.select_for_update().filter(user=request.user, work_id__in=ids)}
    if action in {'shelves', 'personal_tags'}:
        if len(library) != len(ids):
            raise ValidationError({'work_ids': 'Save every selected book to your library before adding shelves or tags.'})
        changed = []
        for pk in ids:
            item = library[pk]
            original = getattr(item, action)
            merged = list(dict.fromkeys([*original, *command['values']]))
            if len(merged) > 50:
                raise ValidationError({'values': 'This would exceed the limit of 50 names on a selected book. Nothing was changed.'})
            if merged != original:
                setattr(item, action, merged)
                item.updated_at = timezone.now()
                changed.append(item)
        if changed:
            LibraryItem.objects.bulk_update(changed, [action, 'updated_at'])
            # Bulk writes skip model signals; keep the existing invalidation
            # behavior on PostgreSQL as well as SQLite after the commit.
            transaction.on_commit(invalidate_catalog)
        result.update(updated_labels=len(changed), unchanged_count=len(ids) - len(changed))
        return result

    missing = [pk for pk in ids if pk not in library]
    if any(works[pk].default_edition and works[pk].default_edition.is_archived for pk in missing):
        raise ValidationError({'work_ids': 'A selected book has an archived default edition. Save it individually with an active edition first.'})
    # bulk_create skips Model.save: freeze the same edition basis explicitly.
    additions = [LibraryItem(user=request.user, work=works[pk], reading_basis=capture_edition(works[pk].default_edition))
                 for pk in missing]
    if additions:
        LibraryItem.objects.bulk_create(additions)
        library.update({item.work_id: item for item in additions})
    result['added_to_library'] = len(additions)
    if action == 'read_next':
        position = LibraryItem.objects.filter(user=request.user).aggregate(last=Max('read_next_position'))['last'] or 0
        changed = []
        for pk in ids:
            item = library[pk]
            if item.read_next_position is None:
                position += 1
                item.read_next_position = position
                item.updated_at = timezone.now()
                changed.append(item)
        if changed:
            LibraryItem.objects.bulk_update(changed, ['read_next_position', 'updated_at'])
        result.update(added_to_read_next=len(changed), unchanged_count=len(ids) - len(changed))
    else:
        result['unchanged_count'] = len(ids) - len(additions)
    if result['added_to_library'] or result['added_to_read_next']:
        transaction.on_commit(invalidate_catalog)
    return result
