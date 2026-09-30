"""Private reading summaries and visible shared-list membership; no inferred reading dates."""
from collections import Counter, defaultdict
from django.db.models import Count, Q, OuterRef, Subquery
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import LibraryItem, ReadingAttempt, Work, Ranking, RankingEntry


def completed_work_ids(user):
    return set(LibraryItem.objects.filter(user=user, status='finished').values_list('work_id', flat=True)) | set(
        ReadingAttempt.objects.filter(user=user, status='finished').values_list('work_id', flat=True))


@api_view(['GET'])
def insights(request):
    current = list(LibraryItem.objects.filter(user=request.user).values('work_id', 'status', 'rating', 'finished_on'))
    previous = list(ReadingAttempt.objects.filter(user=request.user).values('work_id', 'status', 'rating', 'finished_on'))
    finished = [row for row in current + previous if row['status'] == 'finished']
    unique = {row['work_id'] for row in finished}
    months = Counter(row['finished_on'].strftime('%Y-%m') for row in finished if row['finished_on'])
    today = timezone.localdate()
    ordinal = today.year * 12 + today.month - 1
    trends = [{'month': f'{n // 12:04d}-{n % 12 + 1:02d}', 'count': months[f'{n // 12:04d}-{n % 12 + 1:02d}']}
              for n in range(ordinal - 11, ordinal + 1)]
    # Current library ratings express today's preference; archive ratings remain per-attempt history.
    ratings = {row['work_id']: row['rating'] for row in current if row['rating'] is not None}
    authors = defaultdict(lambda: {'finished': set(), 'ratings': {}})
    for work in Work.objects.filter(pk__in=unique | ratings.keys()).prefetch_related('authors'):
        for author in work.authors.all():
            key = (author.pk, author.name)
            if work.pk in unique:
                authors[key]['finished'].add(work.pk)
            if work.pk in ratings:
                authors[key]['ratings'][work.pk] = ratings[work.pk]
    favourites = [{'id': key[0], 'name': key[1], 'books_finished': len(value['finished']),
                   'rated_books': len(value['ratings']),
                   'average_rating': round(sum(value['ratings'].values()) / len(value['ratings']), 2) if value['ratings'] else None}
                  for key, value in authors.items()]
    favourites.sort(key=lambda a: (-(a['average_rating'] or 0), -a['rated_books'], -a['books_finished'], a['name']))
    distribution = Counter(ratings.values())
    return Response({'books_finished': len(unique), 'completed_attempts': len(finished),
        'rereads_finished': len(finished) - len(unique), 'currently_reading': sum(r['status'] == 'reading' for r in current),
        'undated_completions': sum(r['finished_on'] is None for r in finished), 'months': trends,
        'rating_distribution': [{'rating': n, 'count': distribution[n]} for n in range(1, 11)],
        'rated_books': len(ratings), 'unrated_books': len(current) - len(ratings), 'favourite_authors': favourites[:10]})


def shared_lists(user):
    access = Q(is_public=True)
    if user.is_staff:
        access |= Q(owner__isnull=True)
    return Ranking.objects.filter(access, is_archived=False).exclude(origin='personal')


def membership_rows(user, work_ids):
    entries = RankingEntry.objects.filter(ranking__in=shared_lists(user), is_archived=False, work_id__in=work_ids)
    groups = defaultdict(dict)
    for row in entries.values('work_id', 'ranking_id', 'ranking__slug', 'ranking__title', 'ranking__origin', 'ranking__presentation',
                              'position', 'source_rank').order_by('ranking__title', 'ranking_id'):
        groups[row['work_id']][row['ranking_id']] = {'id': row['ranking_id'], 'title': row['ranking__title'],
            'kind': 'Reading collection' if row['ranking__presentation'] != 'ranked' else 'Published ranking' if row['ranking__origin'] == 'external' else 'Researched ranking',
            'origin': row['ranking__origin'], 'presentation': row['ranking__presentation'], 'slug': row['ranking__slug'],
            'position': row['position'], 'source_rank': row['source_rank']}
    return {pk: list(rows.values()) for pk, rows in groups.items()}


@api_view(['GET'])
def collection_context(request):
    from .views import ranking_queryset, positive_id
    ranking = get_object_or_404(ranking_queryset(request.user), pk=positive_id(request.query_params.get('ranking'), 'ranking'))
    ids = list(ranking.entries.filter(is_archived=False, work__isnull=False).values_list('work_id', flat=True))
    members = membership_rows(request.user, ids)
    saved = {r['work_id']: r for r in LibraryItem.objects.filter(user=request.user, work_id__in=ids).values('work_id', 'rating', 'status')}
    read = completed_work_ids(request.user)
    return Response({str(pk): {'rating': saved.get(pk, {}).get('rating'), 'status': saved.get(pk, {}).get('status'),
                              'read': pk in read, 'lists': members.get(pk, [])} for pk in ids})


@api_view(['GET'])
def overlap(request):
    from .views import CatalogPagination, positive_id
    entries = RankingEntry.objects.filter(ranking__in=shared_lists(request.user), is_archived=False, work__is_archived=False)
    repeated = entries.order_by().values('work_id').annotate(total=Count('ranking_id', distinct=True))
    works = Work.objects.annotate(list_count=Subquery(repeated.filter(work_id=OuterRef('pk')).values('total'))).filter(
        list_count__gte=2).prefetch_related('authors', 'tags')
    if ranking := request.query_params.get('ranking'):
        target = get_object_or_404(shared_lists(request.user), pk=positive_id(ranking, 'ranking'))
        works = works.filter(pk__in=entries.filter(ranking=target).values('work_id'))
    if search := request.query_params.get('search'):
        from .search import search_catalog
        works = search_catalog(works, search, order=False)
    if genre := request.query_params.get('genre'):
        works = works.filter(tags__kind='genre', tags__is_archived=False, tags__name=genre).distinct()
    read = completed_work_ids(request.user)
    if request.query_params.get('read') == 'yes':
        works = works.filter(pk__in=read)
    elif request.query_params.get('read') == 'no':
        works = works.exclude(pk__in=read)
    # List agreement is discovery metadata, not a new merit ranking.
    ordered = works.order_by('-list_count', 'title', 'pk')
    paginator = CatalogPagination()
    page = paginator.paginate_queryset(ordered, request)
    memberships = membership_rows(request.user, [w.pk for w in page])
    return paginator.get_paginated_response([{'id': w.pk, 'title': w.title, 'authors': [a.name for a in w.authors.all()],
        'genres': sorted((tag.name for tag in w.tags.all() if tag.kind == 'genre' and not tag.is_archived), key=str.casefold),
        'read': w.pk in read, 'lists': memberships.get(w.pk, []), 'list_count': w.list_count} for w in page])
