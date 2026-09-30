"""Private daily reading and explicit, previewed monthly carryover.

Monthly pages read are entered by the reader. Lifetime book progress cannot tell
us which month those pages belong to, so older allocations remain unrecorded.
"""
from datetime import date
from math import floor

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .reading_calendar import reading_budget
from .mutations import mutation_guard
from .models import ClassicalStudyProfile, LibraryItem, PlanCarryover, PlanItem
from .plan_previews import PlanPreviewConflict, preview_token, require_preview
from .reading_basis import comparable, plan_effort
from .serializers import LibrarySerializer, PlanSerializer


def allocation_has_history(item):
    if item.pages_read is not None or item.carried_pages > 0:
        return True
    incoming = getattr(item, '_has_incoming_carryover', None)
    return incoming if incoming is not None else item.carryovers_in.exists()


def allocation_remaining(item):
    if item.pages is None:
        return None
    return max(0, item.pages - (item.pages_read or 0) - item.carried_pages)


def capacity_summary(user, month, items):
    """Capacity keeps original scheduled and observed reading totals distinct."""
    budget = reading_budget(user, month)
    budget.update(
        used=round(sum(((item.pages or 0) - item.carried_pages) * plan_effort(item, user) for item in items), 2),
        physical_pages=sum(item.pages or 0 for item in items),
        pages_read=sum(item.pages_read or 0 for item in items),
        carried_pages=sum(item.carried_pages for item in items),
        remaining_pages=sum(allocation_remaining(item) or 0 for item in items),
        remaining_effort=round(sum((allocation_remaining(item) or 0) * plan_effort(item, user) for item in items), 2),
        unrecorded_allocations=sum(item.pages_read is None for item in items),
        unknown_allocations=sum(item.pages is None for item in items),
    )
    return budget


def _month(value):
    try:
        month = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValidationError('Choose a valid reading month.')
    if month.day != 1 or not 1900 <= month.year <= 2199:
        raise ValidationError('Use the first day of a month between 1900 and 2199.')
    return month


def _plans(user):
    return PlanItem.objects.filter(user=user).annotate(
        _has_incoming_carryover=Exists(PlanCarryover.objects.filter(target_plan_id=OuterRef('pk'))),
    ).select_related('work__default_edition').prefetch_related('work__authors', 'work__tags')


def _library(user):
    return LibraryItem.objects.filter(user=user).select_related('edition', 'work__default_edition').prefetch_related('work__authors', 'work__tags')


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def today(request):
    month = _month(request.query_params.get('month', timezone.localdate().replace(day=1).isoformat()))
    library = _library(request.user)
    current = library.filter(status='reading')
    queue = library.filter(read_next_position__isnull=False).exclude(status__in=['finished', 'abandoned']).order_by('read_next_position', 'id')
    plans = list(_plans(request.user).filter(month=month))
    return Response({
        'month': month.isoformat(),
        'currently_reading': LibrarySerializer(current[:12], many=True, context={'request': request}).data,
        'currently_reading_count': current.count(),
        'next_books': LibrarySerializer(queue[:5], many=True, context={'request': request}).data,
        'next_books_count': queue.count(),
        'plan': PlanSerializer(plans[:20], many=True, context={'request': request}).data,
        'plan_count': len(plans),
        'capacity': capacity_summary(request.user, month, plans),
    })


class BookProgressCommand(serializers.Serializer):
    item = serializers.IntegerField(min_value=1)
    current_page = serializers.IntegerField(min_value=0)
    expected_updated_at = serializers.DateTimeField()
    finish = serializers.BooleanField(default=False)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@mutation_guard
def today_progress(request):
    command = BookProgressCommand(data=request.data)
    command.is_valid(raise_exception=True)
    values = command.validated_data
    with transaction.atomic():
        request.user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
        item = get_object_or_404(_library(request.user).select_for_update(of=('self',)), pk=values['item'])
        if item.updated_at != values['expected_updated_at']:
            raise PlanPreviewConflict('This book changed elsewhere. Reload Today before saving progress.')
        if item.status in ['finished', 'abandoned']:
            raise ValidationError('Start a reread before recording new progress.')
        serializer = LibrarySerializer(item, data={
            'current_page': values['current_page'],
            'status': 'finished' if values['finish'] else 'reading',
        }, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
    return Response(serializer.data)


class PlanProgressCommand(serializers.Serializer):
    pages_read = serializers.IntegerField(min_value=0, allow_null=True)
    expected_updated_at = serializers.DateTimeField()


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@mutation_guard
def plan_progress(request, pk):
    command = PlanProgressCommand(data=request.data)
    command.is_valid(raise_exception=True)
    values = command.validated_data
    with transaction.atomic():
        request.user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
        item = get_object_or_404(_plans(request.user).select_for_update(of=('self',)), pk=pk)
        if item.updated_at != values['expected_updated_at']:
            raise PlanPreviewConflict('This allocation changed elsewhere. Reload it before saving progress.')
        if item.pages is None:
            raise ValidationError('Set the scheduled page allocation before recording monthly pages read.')
        if item.carried_pages and values['pages_read'] is None:
            raise ValidationError('Keep an explicit reading total for an allocation already carried forward.')
        if values['pages_read'] is not None and values['pages_read'] + item.carried_pages > item.pages:
            raise ValidationError('Pages read plus pages already carried forward cannot exceed the original allocation.')
        item.pages_read = values['pages_read']
        item.save(update_fields=['pages_read', 'updated_at'])
    return Response(PlanSerializer(item, context={'request': request}).data)


class CarryoverCommand(serializers.Serializer):
    source_month = serializers.DateField()
    plan_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False, max_length=500)
    allow_over_capacity = serializers.BooleanField(default=False)
    apply = serializers.BooleanField(default=False)
    preview_token = serializers.CharField(required=False, max_length=8000)

    def validate_source_month(self, value):
        return _month(value.isoformat())

    def validate_plan_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError('Choose each allocation once.')
        return value


def _plan_state(item):
    return {key: getattr(item, key) for key in (
        'id', 'work_id', 'month', 'position', 'pages', 'pages_read', 'carried_pages',
        'locked', 'reading_basis', 'updated_at')}


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@mutation_guard
def carryover(request):
    command = CarryoverCommand(data=request.data)
    command.is_valid(raise_exception=True)
    values = command.validated_data
    source_month = values['source_month']
    target_month = date(source_month.year + (source_month.month == 12), source_month.month % 12 + 1, 1)
    with transaction.atomic():
        request.user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
        rows = list(_plans(request.user).select_for_update(of=('self',)).filter(month__in=[source_month, target_month]))
        sources = [item for item in rows if item.month == source_month]
        targets = [item for item in rows if item.month == target_month]
        selected = values.get('plan_ids', [item.pk for item in sources])
        if not set(selected).issubset({item.pk for item in sources}):
            raise ValidationError('Choose allocations from your selected source month.')
        target_by_work = {item.work_id: item for item in targets}
        profile = ClassicalStudyProfile.objects.filter(user=request.user).values_list('state', flat=True).first() or {}
        classical = profile.get('companion', {}).get('plans', {})
        before = capacity_summary(request.user, target_month, targets)
        # Already carried-out pages are historical rather than new commitments.
        committed = sum(((item.pages or 0) - item.carried_pages) * plan_effort(item, request.user) for item in targets)
        room = before['budget'] - committed
        proposals, skipped, left = [], [], []
        for item in sources:
            if item.pk not in selected:
                continue
            destination = target_by_work.get(item.work_id)
            remaining = allocation_remaining(item)
            reason = None
            if item.locked:
                reason = 'Locked allocation: unlock it before carrying pages forward.'
            elif str(item.pk) in classical:
                reason = 'Classical study allocation: reschedule its selected passages in My classical plan.'
            elif item.pages is None:
                reason = 'Set the scheduled page count first.'
            elif item.pages_read is None:
                reason = 'Record pages read for this month first; enter 0 if none were read.'
            elif not remaining:
                reason = 'No unfinished pages remain.'
            elif destination and destination.locked:
                reason = 'The next month already has a locked allocation for this work.'
            elif destination and str(destination.pk) in classical:
                reason = 'The next month already contains a classical study allocation for this work.'
            elif destination and destination.pages is None:
                reason = 'The next month has an allocation without a page count.'
            elif destination and (comparable(item.reading_basis) != comparable(destination.reading_basis)
                                  or item.reading_basis.get('effort_multiplier') != destination.reading_basis.get('effort_multiplier')):
                reason = 'The next month uses a different saved edition or effort basis.'
            if reason:
                skipped.append({'id': item.pk, 'work': item.work_id, 'title': item.work.title, 'reason': reason})
                continue
            factor = plan_effort(item, request.user)
            pages = remaining if values['allow_over_capacity'] else min(remaining, max(0, floor((room + 1e-8) / factor)))
            if pages:
                proposals.append({'id': item.pk, 'work': item.work_id, 'title': item.work.title,
                                  'pages': pages, 'remaining_before': remaining,
                                  'target_id': destination.pk if destination else None,
                                  'action': 'append' if destination else 'create',
                                  'effort_pages': round(pages * factor, 2)})
                room -= pages * factor
            if pages < remaining:
                left.append({'id': item.pk, 'title': item.work.title, 'pages': remaining - pages,
                             'reason': 'These pages stay in the source month because they do not fit the next month’s remaining capacity.'})
        result = {
            'source_month': source_month.isoformat(), 'target_month': target_month.isoformat(),
            'items': proposals, 'skipped': skipped, 'left_in_source': left,
            'capacity': {**before, 'committed_before': round(committed, 2),
                         'committed_after': round(before['budget'] - room, 2),
                         'remaining_after': round(room, 2)},
            'warnings': ['The destination includes allocations with unknown page counts; available capacity may be overstated.'] if before['unknown_allocations'] else [],
            'applied': values['apply'],
        }
        # Use unrounded proposal inputs as well as the displayed result to make
        # changed settings, allocations and study scope invalidate confirmation.
        state = {'source': source_month, 'target': target_month, 'selected': selected,
                 'allow_over_capacity': values['allow_over_capacity'],
                 'plans': [_plan_state(item) for item in rows], 'classical': classical,
                 'proposal': {key: value for key, value in result.items() if key != 'applied'},
                 'difficulty_aware': request.user.difficulty_aware_planning}
        if values['apply']:
            require_preview(values.get('preview_token'), request.user, 'carryover', state)
            position = max((item.position for item in targets), default=0)
            by_id = {item.pk: item for item in sources}
            for proposal in proposals:
                source = by_id[proposal['id']]
                destination = target_by_work.get(source.work_id)
                if destination:
                    destination.pages += proposal['pages']
                    destination.save(update_fields=['pages', 'updated_at'])
                else:
                    position += 1
                    destination = PlanItem.objects.create(user=request.user, work=source.work,
                        month=target_month, position=position, pages=proposal['pages'],
                        reading_basis=dict(source.reading_basis))
                    target_by_work[source.work_id] = destination
                source.carried_pages += proposal['pages']
                source.save(update_fields=['carried_pages', 'updated_at'])
                PlanCarryover.objects.create(user=request.user, source_plan=source, target_plan=destination,
                    work=source.work, source_month=source_month, target_month=target_month,
                    pages=proposal['pages'], reading_basis=dict(source.reading_basis))
        else:
            result['preview_token'] = preview_token(request.user, 'carryover', state)
    return Response(result)
