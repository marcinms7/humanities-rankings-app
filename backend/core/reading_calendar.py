"""Previewed private calendar exceptions, shared by every reading budget."""
from datetime import date

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers as s
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from backend.domain.reading_capacity import reading_budget as base_reading_budget
from .models import PlanItem, ReadingCalendar
from .mutations import mutation_guard


def calendar_state(user):
    if not hasattr(user, '_reading_calendar_state'):
        saved = ReadingCalendar.objects.filter(user=user).values('revision', 'pauses', 'month_targets').first()
        user._reading_calendar_state = saved or {'revision': 0, 'pauses': [], 'month_targets': []}
    return user._reading_calendar_state


def reading_budget(user, month, adjustments=None):
    return base_reading_budget(user, month, calendar_state(user) if adjustments is None else adjustments)


def _date(value):
    if not 1900 <= value.year <= 2199:
        raise s.ValidationError('Choose dates between 1900 and 2199.')
    return value


class CalendarPauseContract(s.Serializer):
    start = s.DateField()
    end = s.DateField()
    label = s.CharField(max_length=100, allow_blank=True, default='')

    def validate(self, data):
        _date(data['start'])
        _date(data['end'])
        if not 0 <= (data['end'] - data['start']).days <= 365:
            raise s.ValidationError('A pause must end on or after its start, within 366 days.')
        return data


class CalendarMonthTargetContract(s.Serializer):
    month = s.DateField()
    percent = s.IntegerField(min_value=0, max_value=300)

    def validate_month(self, value):
        _date(value)
        if value.day != 1:
            raise s.ValidationError('Choose the first day of the month.')
        return value


class CalendarStateContract(s.Serializer):
    revision = s.IntegerField(min_value=0)
    pauses = CalendarPauseContract(many=True)
    month_targets = CalendarMonthTargetContract(many=True)


class CalendarCommand(CalendarStateContract):
    apply = s.BooleanField(default=False)
    preview_token = s.CharField(max_length=8000, required=False)
    start_month = s.DateField()
    months = s.IntegerField(min_value=1, max_value=24, default=3)

    def validate(self, data):
        _date(data['start_month'])
        if data['start_month'].day != 1:
            raise s.ValidationError('Choose the first day of the preview month.')
        if len(data['pauses']) > 100 or len(data['month_targets']) > 240:
            raise s.ValidationError('Keep at most 100 pauses and 240 temporary month targets.')
        months = [row['month'] for row in data['month_targets']]
        if len(months) != len(set(months)):
            raise s.ValidationError('Choose each temporary month once.')
        return data


class CalendarAllocationContract(s.Serializer):
    id = s.IntegerField()
    title = s.CharField()
    pages = s.IntegerField(allow_null=True)
    locked = s.BooleanField()
    has_history = s.BooleanField()


class CalendarMonthPreviewContract(s.Serializer):
    month = s.DateField()
    before_budget = s.FloatField()
    after_budget = s.FloatField()
    base_budget = s.FloatField()
    paused_days = s.IntegerField()
    calendar_days = s.IntegerField()
    month_percent = s.IntegerField()
    used = s.FloatField()
    over_capacity = s.FloatField()
    unit = s.CharField()
    allocations = CalendarAllocationContract(many=True)
    unknown_allocations = s.IntegerField()


class CalendarPreviewContract(s.Serializer):
    applied = s.BooleanField()
    calendar = CalendarStateContract()
    months = CalendarMonthPreviewContract(many=True)
    preview_token = s.CharField()


def _affected(state):
    result = {date.fromisoformat(row['month']) for row in state['month_targets']}
    for pause in state['pauses']:
        month = date.fromisoformat(pause['start']).replace(day=1)
        end = date.fromisoformat(pause['end']).replace(day=1)
        while month <= end:
            result.add(month)
            month = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
    return result


def _canonical(values):
    return {'revision': values['revision'],
            'pauses': sorted(({'start': row['start'].isoformat(), 'end': row['end'].isoformat(), 'label': row['label']}
                              for row in values['pauses']), key=lambda row: (row['start'], row['end'], row['label'])),
            'month_targets': sorted(({'month': row['month'].isoformat(), 'percent': row['percent']}
                                    for row in values['month_targets'] if row['percent'] != 100), key=lambda row: row['month'])}


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@mutation_guard
def reading_calendar(request):
    if request.method == 'GET':
        return Response(CalendarStateContract(calendar_state(request.user)).data)
    from backend.domain.planning import month_range
    from .plan_previews import PlanPreviewConflict, preview_token, require_preview
    from .reading_basis import plan_effort
    from .reading_workflow import allocation_has_history
    from django.db.models import Exists, OuterRef
    from .models import PlanCarryover

    command = CalendarCommand(data=request.data)
    command.is_valid(raise_exception=True)
    values = command.validated_data
    proposed = _canonical(values)
    with transaction.atomic():
        request.user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
        existing = calendar_state(request.user)
        if existing['revision'] != proposed['revision']:
            raise PlanPreviewConflict('Your reading calendar changed elsewhere. Reopen it before previewing again.')
        months = sorted(_affected(existing) | _affected(proposed) |
                        set(month_range(values['start_month'], values['months'])))
        if len(months) > 240 or months[-1].year > 2199:
            raise s.ValidationError('Preview at most 240 affected months, through 2199.')
        plans = list(PlanItem.objects.filter(user=request.user, month__in=months).annotate(
            _has_incoming_carryover=Exists(PlanCarryover.objects.filter(target_plan_id=OuterRef('pk')))
        ).select_related('work__default_edition').order_by('month', 'position', 'id'))
        changes = []
        for month in months:
            before, after = reading_budget(request.user, month, existing), reading_budget(request.user, month, proposed)
            rows = [item for item in plans if item.month == month]
            used = round(sum(((item.pages or 0) - item.carried_pages) * plan_effort(item, request.user) for item in rows), 2)
            changes.append({'month': month, 'before_budget': before['budget'], 'after_budget': after['budget'],
                **{key: after[key] for key in ('base_budget', 'paused_days', 'calendar_days', 'month_percent', 'unit')},
                'used': used, 'over_capacity': max(0, round(used - after['budget'], 2)),
                'unknown_allocations': sum(item.pages is None for item in rows),
                'allocations': [{'id': item.pk, 'title': item.work.title, 'pages': item.pages,
                                 'locked': item.locked, 'has_history': allocation_has_history(item)} for item in rows]})
        state = {'existing': existing, 'proposed': proposed, 'months': changes,
                 'plans': [{key: getattr(item, key) for key in ('id', 'updated_at', 'reading_basis', 'pages_read', 'carried_pages')} for item in plans]}
        token = preview_token(request.user, 'reading-calendar', state)
        if values['apply']:
            require_preview(values.get('preview_token'), request.user, 'reading-calendar', state)
            proposed['revision'] += 1
            ReadingCalendar.objects.update_or_create(user=request.user, defaults=proposed)
            request.user._reading_calendar_state = proposed
        return Response(CalendarPreviewContract({'applied': values['apply'], 'calendar': proposed,
                                                 'months': changes, 'preview_token': token}).data)
