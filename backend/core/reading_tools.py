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

from .models import LibraryItem, PlanItem, ReadingAttempt, ReadingGoal, Tag


class QueueCommand(serializers.Serializer):
    item = serializers.IntegerField(min_value=1)
    action = serializers.ChoiceField(choices=['add', 'remove', 'up', 'down'])


@api_view(['POST'])
@permission_classes([IsAuthenticated])
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
    genre = serializers.ChoiceField(choices=Tag.GENRES, allow_blank=True, default='')

    def validate_month(self, value):
        if value.day != 1:
            raise serializers.ValidationError('Choose the first day of a month.')
        return value


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_shortlist(request):
    command = SendCommand(data=request.data)
    command.is_valid(raise_exception=True)
    month = command.validated_data['month']
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        planned = set(PlanItem.objects.filter(user=request.user).values_list('work_id', flat=True))
        queue = LibraryItem.objects.filter(user=request.user, read_next_position__isnull=False).select_related('work__default_edition', 'edition').order_by('read_next_position', 'id')
        if genre := command.validated_data['genre']:
            queue = queue.filter(work__tags__kind='genre', work__tags__is_archived=False, work__tags__name=genre)
        items, skipped = [], []
        for item in queue:
            reason = 'Already in your plan (in any month)' if item.work_id in planned else 'Start a reread first' if item.status in ['finished', 'abandoned'] else None
            edition = item.edition or item.work.default_edition
            pages = max(0, edition.pages - item.current_page) if edition and edition.pages else None
            if pages == 0 and not reason:
                reason = 'No remaining pages'
            if reason:
                skipped.append({'title': item.work.title, 'reason': reason})
            else:
                items.append({'work': item.work_id, 'title': item.work.title, 'pages': pages})
        if command.validated_data['apply']:
            position = PlanItem.objects.filter(user=request.user, month=month).aggregate(n=Max('position'))['n'] or 0
            for offset, item in enumerate(items, 1):
                PlanItem.objects.create(user=request.user, work_id=item['work'], month=month, position=position + offset, pages=item['pages'])
    return Response({'items': items, 'skipped': skipped, 'applied': command.validated_data['apply']})


class GoalCommand(serializers.Serializer):
    year = serializers.IntegerField(min_value=1900, max_value=2200)
    books = serializers.IntegerField(min_value=1, max_value=1000000, allow_null=True)
    pages = serializers.IntegerField(min_value=1, max_value=100000000, allow_null=True)


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
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
            edition = item.edition or (item.work.default_edition if model is LibraryItem else None)
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
