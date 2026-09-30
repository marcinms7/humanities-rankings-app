"""Lossless storage adapter for existing study JSON and owned growing records.

The public API shape and all historical revisions stay compatible. Writes touch
only records that changed; small preferences and plan links stay on the profile.
"""
from copy import deepcopy
from hashlib import sha256
import json

from .models import StudyRecord


RECORD_PATHS = (
    ('modules',), ('companion', 'commonplaces'), ('learning', 'essays'),
    ('learning', 'recall'), ('reading_desk', 'note'), ('reading_desk', 'exercise'),
)


def record_key(path):
    return sha256(json.dumps(path, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def put_path(state, path, value):
    target = state
    for key in path[:-1]:
        target = target.setdefault(key, {})
    target[path[-1]] = deepcopy(value)


def split_state(state):
    small = deepcopy(state)
    records = {}
    paths = list(RECORD_PATHS)
    activities = small.get('activities', {})
    if isinstance(activities, dict):
        paths.extend(('activities', version) for version in activities)
    for path in paths:
        target = small
        for key in path:
            target = target.get(key, {}) if isinstance(target, dict) else {}
        if not isinstance(target, dict):
            continue
        for key, value in list(target.items()):
            full_path = [*path, key]
            records[record_key(full_path)] = (full_path, value)
            del target[key]
    return small, records


def load_state(profile):
    if profile is None:
        return {}
    state = deepcopy(profile.state)
    for row in StudyRecord.objects.filter(user_id=profile.user_id).values('path', 'value').iterator(chunk_size=100):
        put_path(state, row['path'], row['value'])
    return state


def save_state(profile, state):
    """Caller holds the account/profile locks in an atomic transaction."""
    small, records = split_state(state)
    stored = {row.record_key: row for row in StudyRecord.objects.filter(user_id=profile.user_id)}
    for key, (path, value) in records.items():
        row = stored.get(key)
        if row is None:
            StudyRecord.objects.create(user_id=profile.user_id, record_key=key, path=path, value=value)
        elif row.value != value:
            row.value = value
            row.revision += 1
            row.save(update_fields=['value', 'revision', 'updated_at'])
    # There is no destructive study-record delete operation. Refuse a caller
    # accidentally dropping history while saving a partial state.
    if set(stored) - set(records):
        raise ValueError('A study update must preserve previously saved records.')
    profile.state = small
    profile.save(update_fields=['state', 'updated_at'])


def state_changes(before, after, path=()):
    """Small path operations avoid resending unrelated notes and essay history."""
    if isinstance(before, dict) and isinstance(after, dict):
        changes = []
        for key in sorted(set(before) | set(after)):
            if key not in after:
                changes.append({'path': [*path, key], 'remove': True})
            elif key not in before:
                changes.append({'path': [*path, key], 'value': after[key]})
            else:
                changes.extend(state_changes(before[key], after[key], (*path, key)))
        return changes
    return [] if before == after else [{'path': list(path), 'value': after}]


FAMILIES = {
    'modules': [('modules',)], 'activities': [('activities',)],
    'companion': [('companion', 'commonplaces')],
    'learning': [('learning', 'essays'), ('learning', 'recall')],
    'essays': [('learning', 'essays')], 'recall': [('learning', 'recall')],
    'desk': [('reading_desk',)], 'sessions': [('learning', 'sessions')],
}


def browser_record(path, value):
    """Keep current editable values; revision text is fetched on demand."""
    result = deepcopy(value)
    if isinstance(result, dict):
        result['_record_key'] = record_key(path)
        for field in ['history', 'attempts']:
            if isinstance(result.get(field), list):
                result[f'_{field}_count'] = len(result[field])
                result[field] = []
    return result


def browser_state(state):
    small, records = split_state(state)
    for path, value in records.values():
        put_path(small, path, browser_record(path, value))
    sessions = small.get('learning', {}).get('sessions')
    if isinstance(sessions, list):
        small['learning']['sessions'] = {str(index): value for index, value in enumerate(sessions)}
    return small


def summary_state(profile, revision):
    """Project only progress/due dates from JSON; never transfer large record bodies."""
    from django.db.models.fields.json import KeyTransform
    if profile is None:
        return {}
    small, legacy = split_state(profile.state)
    small.get('learning', {}).pop('sessions', None)
    rows = StudyRecord.objects.filter(user_id=profile.user_id).annotate(
        completion=KeyTransform(revision, 'value'), due=KeyTransform('due', 'value'),
        revisit=KeyTransform('revisit', 'value')).values('path', 'completion', 'due', 'revisit')
    projected = list(rows)
    projected.extend({'path': path, 'completion': value.get(revision), 'due': value.get('due'), 'revisit': value.get('revisit')}
                     for path, value in legacy.values() if isinstance(value, dict))
    for row in projected:
        path = row['path']
        if path[0] == 'modules':
            put_path(small, path, {revision: row['completion'] or {}})
        elif path[:2] == ['learning', 'recall']:
            put_path(small, path, {'due': row['due']} if row['due'] else {})
        elif path[:2] == ['companion', 'commonplaces']:
            put_path(small, path, {'revisit': row['revisit']} if row['revisit'] else {})
    return small


def record_rows(profile, family):
    from django.db.models import Q
    prefixes = FAMILIES[family]
    condition = Q(pk__in=[])
    for prefix in prefixes:
        condition |= Q(**{f'path__{index}': value for index, value in enumerate(prefix)})
    return StudyRecord.objects.filter(user_id=profile.user_id).filter(condition).order_by('record_key')


def current_record_rows(queryset):
    from django.db import connections
    from django.db.models import F, Func, IntegerField, JSONField, Value
    from django.db.models.fields.json import KeyTransform
    from django.db.models.functions import Coalesce
    vendor = connections[queryset.db].vendor
    if vendor == 'sqlite':
        body = Func(F('value'), Value('$.history'), Value('$.attempts'), function='json_remove', output_field=JSONField())
        length = lambda field: Func(F('value'), Value('$.' + field), function='json_array_length', output_field=IntegerField())
    elif vendor == 'postgresql':
        body = Func(F('value'), Value('history'), Value('attempts'), template='(%(expressions)s)', arg_joiner=' - ', output_field=JSONField())
        length = lambda field: Func(KeyTransform(field, 'value'), function='jsonb_array_length', output_field=IntegerField())
    else:
        return queryset.values('record_key', 'path', 'value')
    return queryset.annotate(current=body, history_count=Coalesce(length('history'), 0),
                             attempts_count=Coalesce(length('attempts'), 0)).values('record_key', 'path', 'current', 'history_count', 'attempts_count')


def current_record(row):
    value = browser_record(row['path'], row.get('current', row.get('value')))
    if 'current' in row and isinstance(value, dict):
        if row['path'][:2] == ['learning', 'essays'] or row['path'][0] == 'reading_desk':
            value.update(history=[], _history_count=row['history_count'])
        elif row['path'][:2] == ['learning', 'recall']:
            value.update(attempts=[], _attempts_count=row['attempts_count'])
    return {'key': row['record_key'], 'path': row['path'], 'value': value}


def records_page(profile, family, page=1, *, expected=None, history_key=None):
    """24 current records, or 12 prior revisions. Caller already checked ownership."""
    from rest_framework.exceptions import ValidationError
    from .plan_previews import PlanPreviewConflict
    if family not in FAMILIES:
        raise ValidationError('Choose a known study record family.')
    revision = profile.updated_at.isoformat() if profile else None
    if expected is not None and expected != (revision or ''):
        raise PlanPreviewConflict('Saved study work changed while loading. Refresh saved work; your drafts are preserved.')
    if type(page) is not int or not 1 <= page <= 100000:
        raise ValidationError('Choose a positive study page.')
    rows, count, page_size = [], 0, 24
    if profile:
        if history_key:
            row = StudyRecord.objects.filter(user_id=profile.user_id, record_key=history_key).first()
            if row is None:
                _, legacy = split_state(profile.state)
                pair = legacy.get(history_key)
                if pair is None:
                    raise ValidationError('That saved study record is unavailable.')
                path, value = pair
            else:
                path, value = row.path, row.value
            if not any(tuple(path[:len(prefix)]) == prefix for prefix in FAMILIES[family]):
                raise ValidationError('That record is outside the selected study family.')
            history = value.get('history', value.get('attempts', []))
            page_size, count = 12, len(history)
            rows = list(reversed(history))[((page - 1) * page_size):(page * page_size)]
        else:
            queryset = record_rows(profile, family)
            _, legacy = split_state(profile.state)
            stored_keys = set(queryset.values_list('record_key', flat=True))
            extra = [(key, path, value) for key, (path, value) in legacy.items()
                     if key not in stored_keys and any(tuple(path[:len(prefix)]) == prefix for prefix in FAMILIES[family])]
            if family == 'sessions':
                extra.extend((str(index), ['learning', 'sessions', str(index)], value)
                             for index, value in reversed(list(enumerate(profile.state.get('learning', {}).get('sessions', [])))))
            stored_count = queryset.count()
            count = stored_count + len(extra)
            start, end = (page - 1) * page_size, page * page_size
            rows = [current_record(row) for row in current_record_rows(queryset)[start:min(end, stored_count)]] if start < stored_count else []
            if end > stored_count:
                rows.extend({'key': key, 'path': path, 'value': browser_record(path, value)}
                            for key, path, value in extra[max(0, start - stored_count):max(0, end - stored_count)])
    return {'family': family, 'count': count, 'page': page, 'page_size': page_size,
            'next_page': page + 1 if page * page_size < count else None, 'results': rows,
            'updated_at': revision}


# Explicit contracts are also consumed by the frontend contract generator.
from rest_framework import serializers


class StudyRecordContract(serializers.Serializer):
    key = serializers.CharField()
    path = serializers.ListField(child=serializers.CharField())
    value = serializers.JSONField()


class StudyRecordsPageContract(serializers.Serializer):
    family = serializers.ChoiceField(choices=list(FAMILIES))
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    next_page = serializers.IntegerField(allow_null=True)
    results = StudyRecordContract(many=True)
    updated_at = serializers.DateTimeField(allow_null=True)
