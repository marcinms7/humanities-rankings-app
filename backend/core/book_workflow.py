"""Preview a single book allocation from its saved reading edition."""
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .mutations import mutation_guard
from .models import LibraryItem, PlanItem
from .plan_previews import preview_token, require_preview
from .reading_basis import capture_plan, comparable, plan_effort
from .reading_workflow import allocation_remaining, capacity_summary
from .serializers import PlanSerializer


class AllocationCommand(serializers.Serializer):
    work = serializers.IntegerField(min_value=1)
    month = serializers.DateField()
    pages = serializers.IntegerField(min_value=1, max_value=100000, allow_null=True)
    locked = serializers.BooleanField(default=False)
    apply = serializers.BooleanField(default=False)
    preview_token = serializers.CharField(required=False, max_length=8000)

    def validate_month(self, value):
        if value.day != 1 or not 1900 <= value.year <= 2200:
            raise serializers.ValidationError('Choose the first day of a month between 1900 and 2200.')
        return value


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@mutation_guard
def reading_allocation(request):
    command = AllocationCommand(data=request.data)
    command.is_valid(raise_exception=True)
    values = command.validated_data
    with transaction.atomic():
        request.user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
        item = get_object_or_404(LibraryItem.objects.select_related('work__default_edition', 'edition').select_for_update(of=('self',)),
                                 user=request.user, work_id=values['work'])
        if item.status in {'finished', 'abandoned'}:
            raise serializers.ValidationError('Start a reread before scheduling another reading attempt.')
        basis = capture_plan(item.work, request.user.pk)
        remaining = max(0, basis['pages'] - item.current_page) if basis.get('pages') is not None else None
        if remaining == 0:
            raise serializers.ValidationError('No pages remain in this reading attempt. Update the reading record before scheduling it again.')
        if values['pages'] is not None and remaining is not None and values['pages'] > remaining:
            raise serializers.ValidationError('This allocation exceeds the remaining pages in your saved reading edition.')
        fields = {key: values[key] for key in ['work', 'month', 'pages', 'locked']}
        serializer = PlanSerializer(data=fields, context={'request': request})
        serializer.is_valid(raise_exception=True)
        allocations = list(PlanItem.objects.filter(user=request.user, month=values['month']).select_related('work__default_edition'))
        elsewhere = list(PlanItem.objects.filter(user=request.user, work=item.work).exclude(month=values['month']))
        capacity = capacity_summary(request.user, values['month'], allocations)
        factor = basis['effort_multiplier'] if request.user.difficulty_aware_planning else 1
        effort = values['pages'] * factor if values['pages'] is not None else None
        committed = sum(((row.pages or 0) - row.carried_pages) *
                        (plan_effort(row, request.user) if request.user.difficulty_aware_planning else 1)
                        for row in allocations)
        result = {'work': item.work_id, 'title': item.work.title, 'month': values['month'],
                  'pages': values['pages'], 'remaining_pages': remaining, 'effort_pages': effort,
                  'locked': values['locked'], 'capacity': capacity,
                  'over_capacity': max(0, committed + (effort or 0) - capacity['budget']),
                  'reading_basis': comparable(basis),
                  'other_allocations': [{'month': row.month, 'pages': row.pages, 'pages_read': row.pages_read,
                                         'remaining_pages': allocation_remaining(row), 'locked': row.locked,
                                         'same_reading_basis': comparable(row.reading_basis) == comparable(basis)}
                                        for row in elsewhere if allocation_remaining(row) != 0],
                  'warnings': []}
        if result['other_allocations']:
            result['warnings'].append('This book also has unfinished or unrecorded allocations in other months. '
                'Review them to avoid scheduling the same pages twice; this adds a new allocation without moving those pages.')
        if values['pages'] is None:
            result['warnings'].append('An allocation without pages is not included in the capacity calculation.')
        state = {'proposal': result, 'library': {'id': item.pk, 'updated_at': item.updated_at},
                 'basis': {**comparable(basis), 'effort_multiplier': basis['effort_multiplier']},
                 'allocations': [{key: getattr(row, key) for key in ['id', 'pages', 'pages_read', 'carried_pages', 'locked', 'reading_basis', 'updated_at']}
                                 for row in allocations],
                 'other_allocations': [{key: getattr(row, key) for key in ['id', 'month', 'pages', 'pages_read', 'carried_pages', 'locked', 'reading_basis', 'updated_at']}
                                       for row in elsewhere]}
        if values['apply']:
            require_preview(values.get('preview_token'), request.user, 'book-allocation', state)
            position = (PlanItem.objects.filter(user=request.user, month=values['month']).aggregate(n=Max('position'))['n'] or 0) + 1
            plan = serializer.save(user=request.user, position=position, reading_basis=basis)
            return Response({'applied': True, 'plan': PlanSerializer(plan, context={'request': request}).data})
        return Response({**result, 'applied': False, 'preview_token': preview_token(request.user, 'book-allocation', state)})
