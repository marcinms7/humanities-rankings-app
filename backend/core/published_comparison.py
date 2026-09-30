"""Read-only comparisons of saved publisher lists, preserving their source ranks."""
from collections import Counter

from django.db.models import Count, F, Prefetch, Q
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Person, RankingEntry, Work
from .ranking_contracts import RankingPersonCardSerializer
from .reading_insights import shared_lists
from .search import search_catalog
from .serializers import WorkCardSerializer


class PublishedListOptionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    publisher = serializers.CharField()
    item_type = serializers.ChoiceField(choices=['work', 'person'])
    total = serializers.IntegerField()


class PublishedListDetailSerializer(PublishedListOptionSerializer):
    source_url = serializers.CharField()
    description = serializers.CharField()
    scope_labels = serializers.ListField(child=serializers.CharField())
    method = serializers.CharField()
    limitation = serializers.CharField()
    known_ranks = serializers.IntegerField()
    unresolved_count = serializers.IntegerField(allow_null=True)


class PublishedComparisonSummarySerializer(serializers.Serializer):
    shared = serializers.IntegerField()
    left_only = serializers.IntegerField()
    right_only = serializers.IntegerField()
    union = serializers.IntegerField()
    comparable = serializers.IntegerField()
    different = serializers.IntegerField()


class PublishedComparisonRowSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    book = WorkCardSerializer(allow_null=True)
    person = RankingPersonCardSerializer(allow_null=True)
    left_rank = serializers.IntegerField(allow_null=True)
    right_rank = serializers.IntegerField(allow_null=True)
    left_tied = serializers.BooleanField()
    right_tied = serializers.BooleanField()
    in_left = serializers.BooleanField()
    in_right = serializers.BooleanField()
    delta = serializers.IntegerField(allow_null=True)


class PublishedComparisonSerializer(serializers.Serializer):
    options = PublishedListOptionSerializer(many=True)
    left = PublishedListDetailSerializer(allow_null=True)
    right = PublishedListDetailSerializer(allow_null=True)
    summary = PublishedComparisonSummarySerializer(allow_null=True)
    count = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = PublishedComparisonRowSerializer(many=True)
    note = serializers.CharField()


class ComparisonQuerySerializer(serializers.Serializer):
    left = serializers.IntegerField(min_value=1, max_value=9223372036854775807, required=False)
    right = serializers.IntegerField(min_value=1, max_value=9223372036854775807, required=False)
    view = serializers.ChoiceField(choices=['shared', 'left_only', 'right_only'], default='shared')
    sort = serializers.ChoiceField(choices=['left', 'right', 'difference', 'title'], default='left')
    search = serializers.CharField(max_length=300, allow_blank=True, default='')


class ComparisonPagination(PageNumberPagination):
    page_size = 24


NOTE = ('Comparisons use saved catalog identities and recorded publisher ranks only. Ties retain their '
        'original numbers; missing ranks stay unknown. Different scopes, methods and list lengths mean '
        'a position difference is not a common merit score. Series and their individual books are not '
        'merged. Counts describe the saved, active entries; absent books may be outside a list’s scope '
        'or missing from its import.')


def _text(value):
    return value if isinstance(value, str) else ''


def _option(ranking):
    return dict(id=ranking.pk, title=ranking.title, publisher=ranking.publisher,
                item_type=ranking.item_type, total=ranking.comparison_total)


def _detail(ranking, rows):
    scope = ranking.scope if isinstance(ranking.scope, dict) else {}
    metadata = scope.get('external_metadata', {})
    imported = scope.get('external_import', {})
    metadata = metadata if isinstance(metadata, dict) else {}
    imported = imported if isinstance(imported, dict) else {}
    labels = [ranking.domain]
    for key, title in [('countries', 'Countries'), ('forms', 'Forms'), ('languages', 'Languages'),
                       ('centuries', 'Centuries'), ('period', 'Period')]:
        value = scope.get(key)
        if isinstance(value, list):
            value = ', '.join(str(item) for item in value if isinstance(item, (str, int)))
        if isinstance(value, (str, int)) and value:
            labels.append(f'{title}: {value}')
    unresolved = imported.get('unresolved_count')
    if type(unresolved) is not int or unresolved < 0:
        unresolved = None
    return dict(**_option(ranking), source_url=ranking.source_url,
                description=ranking.description, scope_labels=labels,
                method=_text(metadata.get('method')) or _text(imported.get('method_note')),
                limitation=_text(metadata.get('limitation')),
                known_ranks=sum(row['rank'] is not None for row in rows.values()),
                unresolved_count=unresolved)


def _entries(ranking):
    key = 'work' if ranking.item_type == 'work' else 'person'
    rows = RankingEntry.objects.filter(ranking=ranking, is_archived=False,
        **{f'{key}__is_archived': False}).values(f'{key}_id', 'source_rank', 'position', 'groupings',
            title=F(f'{key}__title' if key == 'work' else f'{key}__name'))
    # Display order is deliberately not a fallback rank. Group-local placements
    # also do not establish one global publisher position.
    return {row[f'{key}_id']: dict(rank=row['source_rank'] if not row['groupings'] and
        row['source_rank'] is not None and row['source_rank'] > 0 else None,
        position=row['position'], title=row['title']) for row in rows}


@api_view(['GET'])
@permission_classes([AllowAny])
def published_comparison(request):
    params = {key: value for key, value in request.query_params.items()
              if key not in {'left', 'right'} or value != ''}
    query = ComparisonQuerySerializer(data=params)
    query.is_valid(raise_exception=True)
    values = query.validated_data
    active = Q(entries__is_archived=False) & (
        Q(item_type='work', entries__work__is_archived=False) |
        Q(item_type='person', entries__person__is_archived=False))
    rankings = list(shared_lists(request.user).filter(origin='external', presentation='ranked',
        owner__isnull=True).annotate(comparison_total=Count('entries', filter=active)).order_by('title', 'pk'))
    by_id = {ranking.pk: ranking for ranking in rankings}
    selected = {}
    for key in ['left', 'right']:
        if values.get(key) is not None:
            if values[key] not in by_id:
                raise NotFound('Choose an available published ranking.')
            selected[key] = by_id[values[key]]
    left, right = selected.get('left'), selected.get('right')
    if left and right:
        if left.pk == right.pk:
            raise ValidationError({'right': 'Choose two different published lists.'})
        if left.item_type != right.item_type:
            raise ValidationError({'right': 'Compare two book lists or two people lists.'})
    a, b = _entries(left) if left else {}, _entries(right) if right else {}
    payload = dict(options=[_option(ranking) for ranking in rankings],
        left=_detail(left, a) if left else None, right=_detail(right, b) if right else None,
        summary=None, count=0, next=None, previous=None, results=[], note=NOTE)
    if left and right:
        shared, left_only, right_only = a.keys() & b.keys(), a.keys() - b.keys(), b.keys() - a.keys()
        comparable = {pk for pk in shared if a[pk]['rank'] is not None and b[pk]['rank'] is not None}
        payload['summary'] = dict(shared=len(shared), left_only=len(left_only), right_only=len(right_only),
            union=len(a.keys() | b.keys()), comparable=len(comparable),
            different=sum(a[pk]['rank'] != b[pk]['rank'] for pk in comparable))
        ids = {'shared': shared, 'left_only': left_only, 'right_only': right_only}[values['view']]
        model = Work if left.item_type == 'work' else Person
        if values['search']:
            ids = set(search_catalog(model.objects.filter(pk__in=ids), values['search'],
                kind=left.item_type, order=False).values_list('pk', flat=True))
        def rank_key(pk, side):
            value = side.get(pk, {}).get('rank')
            return (value is None, value or 0)
        def title_key(pk):
            return (a.get(pk) or b[pk])['title'].casefold(), pk
        def sort_key(pk):
            if values['sort'] == 'title':
                return title_key(pk)
            if values['sort'] == 'difference':
                return (pk not in comparable, -abs(b[pk]['rank'] - a[pk]['rank']) if pk in comparable else 0,
                        *title_key(pk))
            side = a if values['sort'] == 'left' else b
            # Equal source ranks retain the publisher's recorded display order;
            # this tiebreaker never becomes a displayed merit position.
            return (*rank_key(pk, side), side.get(pk, {}).get('position', 0), *title_key(pk))
        paginator = ComparisonPagination()
        page = paginator.paginate_queryset(sorted(ids, key=sort_key), request)
        objects = model.objects.filter(pk__in=page, is_archived=False)
        if model is Work:
            objects = list(objects.select_related('default_edition').prefetch_related(
                Prefetch('authors', queryset=Person.objects.filter(is_archived=False)), 'tags'))
            for work in objects:
                if work.default_edition and work.default_edition.is_archived:
                    work.default_edition = None
        serializer = WorkCardSerializer if model is Work else RankingPersonCardSerializer
        cards = {row['id']: row for row in serializer(objects, many=True, context={'request': request}).data}
        ties_a, ties_b = Counter(row['rank'] for row in a.values()), Counter(row['rank'] for row in b.values())
        rows = []
        for pk in page:
            if pk not in cards:
                continue  # A concurrent archive must not resurrect a catalog record.
            rank_a, rank_b = a.get(pk, {}).get('rank'), b.get(pk, {}).get('rank')
            rows.append(dict(id=pk, book=cards[pk] if model is Work else None,
                person=cards[pk] if model is Person else None,
                left_rank=rank_a, right_rank=rank_b, in_left=pk in a, in_right=pk in b,
                left_tied=rank_a is not None and ties_a[rank_a] > 1,
                right_tied=rank_b is not None and ties_b[rank_b] > 1,
                delta=rank_b-rank_a if pk in comparable else None))
        payload.update(paginator.get_paginated_response(rows).data)
    response = Response(payload)
    response['Cache-Control'] = 'private, no-store'
    return response
