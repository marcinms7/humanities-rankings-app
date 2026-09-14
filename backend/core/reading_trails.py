"""Editorial reading sequences and account-scoped discovery, never merit scores."""
import json
from pathlib import Path

from django.db.models import Case, Count, IntegerField, OuterRef, Q, Subquery, Value, When
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from .models import LibraryItem, RankingEntry, ReadingAttempt, Work
from .reading_insights import completed_work_ids, membership_rows, shared_lists


def private_response(data):
    response = Response(data)
    response['Cache-Control'] = 'private, no-store'
    return response


@api_view(['GET'])
def trails(request):
    content = json.loads((Path(__file__).parent / 'content/reading_trails.json').read_text())
    ids = {step['work'] for trail in content['trails'] for step in trail['steps']}
    works = {w.pk: w for w in Work.objects.filter(pk__in=ids, is_archived=False).prefetch_related('authors')}
    memberships = membership_rows(request.user, ids)
    saved = dict(LibraryItem.objects.filter(user=request.user, work_id__in=ids).values_list('work_id', 'status'))
    finished = completed_work_ids(request.user)
    for trail in content['trails']:
        for step in trail['steps']:
            work = works.get(step['work'])
            step.update(available=bool(work), title=work.title if work else step['label'],
                        authors=[a.name for a in work.authors.all()] if work else [],
                        lists=memberships.get(step['work'], []), status=saved.get(step['work']),
                        read=step['work'] in finished)
        trail['next_work'] = next((s['work'] for s in trail['steps'] if s['available'] and not s['read']), None)
    return private_response(content)


def bounded_int(params, key, default, low, high):
    value = params.get(key, str(default))
    try:
        result = int(value)
        if not low <= result <= high:
            raise ValueError
        return result
    except (ValueError, TypeError):
        raise ValidationError(f'{key}: choose a number between {low} and {high}.')


@api_view(['GET'])
def personal_discovery(request):
    from .views import CatalogPagination
    p = request.query_params
    minimum = bounded_int(p, 'minimum', 0, 0, 1000)
    max_pages = bounded_int(p, 'max_pages', 0, 0, 100000)
    entries = RankingEntry.objects.filter(ranking__in=shared_lists(request.user), ranking__presentation='ranked', is_archived=False)
    counts = entries.order_by().values('work_id').annotate(n=Count('ranking_id', distinct=True))
    library = LibraryItem.objects.filter(user=request.user, work_id=OuterRef('pk'))
    works = Work.objects.filter(is_archived=False).annotate(
        ranking_count=Subquery(counts.filter(work_id=OuterRef('pk')).values('n')),
        saved_status=Subquery(library.values('status')[:1]),
        chosen_edition=Subquery(library.values('edition_id')[:1]),
        chosen_pages=Subquery(library.values('edition__pages')[:1]),
    ).annotate(discovery_pages=Case(When(chosen_edition__isnull=False, then='chosen_pages'),
                                    default='default_edition__pages', output_field=IntegerField()))
    if minimum:
        works = works.filter(ranking_count__gte=minimum)
    if max_pages:
        works = works.filter(discovery_pages__lte=max_pages, discovery_pages__gte=1)
    if p.get('wishlist') == 'yes':
        works = works.filter(saved_status='want_to_read')
    read = completed_work_ids(request.user)
    if p.get('unread') == 'yes':
        works = works.exclude(pk__in=read)
    if p.get('new_authors') == 'yes':
        # An author is explored if any current/historical attempt was started, not merely wishlisted.
        attempted = Q(status__in=['reading', 'paused', 'finished', 'abandoned']) | Q(current_page__gt=0) | Q(started_on__isnull=False)
        seen_works = set(LibraryItem.objects.filter(attempted, user=request.user).values_list('work_id', flat=True))
        seen_works.update(ReadingAttempt.objects.filter(attempted, user=request.user).values_list('work_id', flat=True))
        seen_authors = Work.objects.filter(pk__in=seen_works).values('authors__pk')
        works = works.filter(authors__isnull=False).exclude(authors__pk__in=seen_authors).distinct()
    if search := p.get('search', '').strip()[:300]:
        works = works.filter(Q(title__icontains=search) | Q(authors__name__icontains=search)).distinct()
    if field := p.get('field', ''):
        works = works.filter(field=field[:30])
    ordering = ('discovery_pages', 'title', 'pk') if max_pages else ('title', 'pk')
    paginator = CatalogPagination()
    page = paginator.paginate_queryset(works.select_related('default_edition').prefetch_related('authors').order_by(*ordering), request)
    memberships = membership_rows(request.user, [w.pk for w in page])
    response = paginator.get_paginated_response([dict(id=w.pk, title=w.title, authors=[a.name for a in w.authors.all()],
        ranking_count=w.ranking_count or 0, lists=[r for r in memberships.get(w.pk, []) if r['presentation'] == 'ranked'],
        status=w.saved_status, read=w.pk in read, pages=w.discovery_pages,
        page_basis='Your selected edition' if w.chosen_edition else 'Catalog default edition') for w in page])
    response.data['note'] = ('Unread means no finished current or archived reading in this account; it can include an in-progress book. '
        'New authors excludes every credited author on a recorded started/paused/finished/abandoned reading. Unknown authors are excluded from that filter. '
        'Short books use your selected edition, otherwise the catalog default; unknown page counts never count as short. '
        'Ranking counts exclude unranked collections and reading sequences and are not independent votes or a quality score. Catalog duplicates are not silently merged.')
    response['Cache-Control'] = 'private, no-store'
    return response
