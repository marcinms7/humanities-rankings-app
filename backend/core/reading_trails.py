"""Editorial reading sequences and account-scoped discovery, never merit scores."""
import json
from pathlib import Path

from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import LibraryItem, ReadingAttempt, Work
from .reading_insights import completed_work_ids, membership_rows
from .saved_discovery import apply_discovery_filters, effective_filters


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


@api_view(['GET'])
def personal_discovery(request):
    from .views import CatalogPagination
    filters = effective_filters(request.user, request.query_params)
    works = apply_discovery_filters(Work.objects.filter(is_archived=False), request.user, request.query_params)
    ordering = ('discovery_pages', 'title', 'pk') if filters['max_pages'] else ('title', 'pk')
    paginator = CatalogPagination()
    page = paginator.paginate_queryset(works.select_related('default_edition').only(
        'id', 'title', 'default_edition_id', 'default_edition__id', 'default_edition__pages'
    ).prefetch_related('authors').order_by(*ordering), request)
    work_ids = [work.pk for work in page]
    read = set(LibraryItem.objects.filter(user=request.user, work_id__in=work_ids, status='finished').values_list('work_id', flat=True))
    read.update(ReadingAttempt.objects.filter(user=request.user, work_id__in=work_ids, status='finished').values_list('work_id', flat=True))
    memberships = membership_rows(request.user, work_ids)
    response = paginator.get_paginated_response([dict(id=w.pk, title=w.title, authors=[a.name for a in w.authors.all()],
        ranking_count=w.ranking_count or 0, lists=[r for r in memberships.get(w.pk, []) if r['presentation'] == 'ranked'],
        status=w.saved_status, read=w.pk in read, pages=w.discovery_pages,
        page_basis='Your saved reading length' if w.chosen_edition else 'Catalog default edition') for w in page])
    response.data['filters'] = filters
    response.data['note'] = ('Unread means no finished current or archived reading in this account; it can include an in-progress book. '
        'New authors excludes every credited author on a recorded started/paused/finished/abandoned reading. Unknown authors are excluded from that filter. '
        'Short books use your selected edition, otherwise the catalog default; unknown page counts never count as short. '
        'Bookmarked rankings includes only visible researched/published merit rankings that you bookmarked. '
        'Country matches the work’s recorded literary/cultural associations. '
        'Ranking counts exclude unranked collections and reading sequences and are not independent votes or a quality score. Catalog duplicates are not silently merged.')
    response['Cache-Control'] = 'private, no-store'
    return response
