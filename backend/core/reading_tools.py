"""Private shortlist and annual goals; never modify shared catalog records."""
from collections import defaultdict

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from backend.domain.reading_capacity import effort_per_page
from .mutations import mutation_guard
from .models import LibraryItem, PlanCarryover, PlanItem, ReadingAttempt, ReadingGoal, Tag
from .plan_previews import preview_token, require_preview
from .reading_basis import capture_edition, comparable, length_edition


class QueueCommand(serializers.Serializer):
    item = serializers.IntegerField(min_value=1)
    action = serializers.ChoiceField(choices=['add', 'remove', 'up', 'down'])


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@mutation_guard
def shortlist(request):
    command = QueueCommand(data=request.data)
    command.is_valid(raise_exception=True)
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        item = get_object_or_404(LibraryItem, user=request.user, pk=command.validated_data['item'])
        queue = list(LibraryItem.objects.filter(user=request.user, read_next_position__isnull=False).order_by('read_next_position', 'id'))
        action = command.validated_data['action']
        index = next((n for n, row in enumerate(queue) if row.pk == item.pk), None)
        if action == 'add' and index is None:
            queue.append(item)
        elif action == 'remove':
            queue = [row for row in queue if row.pk != item.pk]
            item.read_next_position = None
            item.save(update_fields=['read_next_position'])
        elif action in ['up', 'down'] and index is not None:
            target = index + (-1 if action == 'up' else 1)
            if 0 <= target < len(queue):
                queue[index], queue[target] = queue[target], queue[index]
        for position, row in enumerate(queue, 1):
            row.read_next_position = position
        LibraryItem.objects.bulk_update(queue, ['read_next_position'])
    return Response({'saved': True})


class SendCommand(serializers.Serializer):
    month = serializers.DateField()
    apply = serializers.BooleanField(default=False)
    preview_token = serializers.CharField(required=False, max_length=8000)
    genre = serializers.ChoiceField(choices=Tag.GENRES, allow_blank=True, default='')

    def validate_month(self, value):
        if value.day != 1:
            raise serializers.ValidationError('Choose the first day of a month.')
        return value


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@mutation_guard
def send_shortlist(request):
    command = SendCommand(data=request.data)
    command.is_valid(raise_exception=True)
    month = command.validated_data['month']
    with transaction.atomic():
        request.user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
        plans = list(PlanItem.objects.filter(user=request.user).order_by('pk').values(
            'pk', 'work_id', 'month', 'position', 'pages', 'pages_read', 'carried_pages',
            'locked', 'reading_basis', 'updated_at'))
        # Completed allocations are retained as history. They must not prevent
        # a later reread being scheduled, while an existing row in this month
        # still occupies the unique work/month slot even when complete.
        same_month = {plan['work_id'] for plan in plans if plan['month'] == month}
        outstanding = {plan['work_id'] for plan in plans if plan['pages'] is None
                       or plan['pages'] - (plan['pages_read'] or 0) - plan['carried_pages'] > 0}
        queue = LibraryItem.objects.filter(user=request.user, read_next_position__isnull=False).select_related('work__default_edition', 'edition').order_by('read_next_position', 'id')
        if genre := command.validated_data['genre']:
            queue = queue.filter(work__tags__kind='genre', work__tags__is_archived=False, work__tags__name=genre)
        from .reading_workflow import capacity_summary
        capacity = capacity_summary(request.user, month, list(PlanItem.objects.filter(user=request.user, month=month).select_related('work__default_edition')))
        room = capacity['budget'] - capacity['used']
        items, skipped, library_state = [], [], []
        for item in queue:
            reason = ('Already has an allocation in this month' if item.work_id in same_month
                      else 'Has unfinished or unrecorded pages in another month' if item.work_id in outstanding
                      else 'Start a reread first' if item.status in ['finished', 'abandoned'] else None)
            edition = length_edition(item)
            library_state.append({'id': item.pk, 'work': item.work_id, 'updated_at': item.updated_at,
                'position': item.read_next_position, 'status': item.status, 'current_page': item.current_page,
                'basis': comparable(item.reading_basis or capture_edition(edition)),
                'effort_multiplier': effort_per_page(item.work, edition)})
            pages = max(0, edition.pages - item.current_page) if edition and edition.pages else None
            if pages == 0 and not reason:
                reason = 'No remaining pages'
            cost = pages * effort_per_page(item.work, edition, request.user.difficulty_aware_planning) if pages is not None else None
            if not reason and cost is None:
                reason = 'Add an edition page count before fitting this book to the month'
            if not reason and cost > room + 1e-8:
                reason = 'Does not fit this month’s remaining target, including temporary targets and pauses; schedule selected pages in Reading plan'
            if not reason:
                room -= cost
            if reason:
                skipped.append({'title': item.work.title, 'reason': reason})
            else:
                items.append({'work': item.work_id, 'title': item.work.title, 'pages': pages})
        state = {'capacity': capacity, 'month': month, 'genre': genre, 'library': library_state, 'plans': plans,
                 'carryovers': list(PlanCarryover.objects.filter(user=request.user).order_by('pk').values(
                     'pk', 'source_plan_id', 'target_plan_id', 'pages', 'created_at')),
                 'items': items, 'skipped': skipped}
        if command.validated_data['apply']:
            require_preview(command.validated_data.get('preview_token'), request.user, 'shortlist', state)
            position = PlanItem.objects.filter(user=request.user, month=month).aggregate(n=Max('position'))['n'] or 0
            for offset, item in enumerate(items, 1):
                PlanItem.objects.create(user=request.user, work_id=item['work'], month=month, position=position + offset, pages=item['pages'])
    return Response({'capacity': capacity, 'remaining_after': round(room, 2), 'items': items, 'skipped': skipped, 'applied': command.validated_data['apply'],
                     'preview_token': preview_token(request.user, 'shortlist', state)})


class GoalCommand(serializers.Serializer):
    year = serializers.IntegerField(min_value=1900, max_value=2200)
    books = serializers.IntegerField(min_value=1, max_value=1000000, allow_null=True)
    pages = serializers.IntegerField(min_value=1, max_value=100000000, allow_null=True)


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
@mutation_guard
def annual_reading(request):
    if request.method == 'PATCH':
        command = GoalCommand(data=request.data)
        command.is_valid(raise_exception=True)
        values = command.validated_data.copy()
        year = values.pop('year')
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            ReadingGoal.objects.update_or_create(user=request.user, year=year, defaults=values)
    years = defaultdict(lambda: {'books': 0, 'pages': 0, 'unknown_pages': 0, 'works': set(), 'book_goal': None, 'page_goal': None})
    years[timezone.localdate().year]
    undated = 0
    for model in [LibraryItem, ReadingAttempt]:
        for item in model.objects.filter(user=request.user, status='finished').select_related('edition', 'work__default_edition'):
            if not item.finished_on:
                undated += 1
                continue
            row = years[item.finished_on.year]
            row['books'] += 1
            row['works'].add(item.work_id)
            # Archived attempts keep their selected historical edition; do not guess a new one.
            edition = length_edition(item) if item.reading_basis or model is LibraryItem else item.edition
            pages = edition.pages if edition and edition.pages else item.current_page or None
            if pages is None:
                row['unknown_pages'] += 1
            else:
                row['pages'] += pages
    for goal in ReadingGoal.objects.filter(user=request.user):
        years[goal.year].update(book_goal=goal.books, page_goal=goal.pages)
    result = []
    for year, row in sorted(years.items(), reverse=True):
        row['unique_books'] = len(row.pop('works'))
        result.append({'year': year, **row})
    return Response({'years': result, 'undated_completions': undated})
