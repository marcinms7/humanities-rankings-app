"""Page ranking IDs/placements before loading book, person and private context cards."""
from copy import deepcopy

from django.db import connection
from django.db.models import F, Q, Value
from rest_framework.exceptions import ValidationError

from .catalog_cache import cached_catalog
from .evidence_provenance import order_status
from .models import LibraryItem, Person, ReadingAttempt, Tag, Work
from .ranking_contracts import RankingBrowseEntrySerializer
from .reading_insights import membership_rows
from .serializers import RankingSerializer


def position_map(order):
    ids = order.get('item_ids', []) if isinstance(order, dict) else []
    if not isinstance(ids, list):
        return {}
    positions, duplicated = {}, set()
    for index, item_id in enumerate(ids, 1):
        if isinstance(item_id, int) and not isinstance(item_id, bool):
            if item_id in positions:
                duplicated.add(item_id)
            positions[item_id] = index
    return {key: rank for key, rank in positions.items() if key not in duplicated}


def compact_ranking(ranking, request, *, public=False):
    data = RankingSerializer(ranking, context={'request': request}).data
    scope = deepcopy(data.get('scope') or {})
    editorial = scope.get('editorial')
    if isinstance(editorial, dict):
        editorial['entries'] = {}
        for order in editorial.get('orders', {}).values():
            if isinstance(order, dict):
                order['item_ids'] = []
    data['scope'] = scope
    if public:
        for key in ['owner', 'criteria', 'preference', 'share_url', 'order_status']:
            data.pop(key, None)
        data.update(can_edit=False, criteria=[], preference=None,
                    owner=None, share_url=None,
                    scope={'group_by': 'country'} if ranking.scope.get('group_by') == 'country' else {})
    return data


def ranking_index(queryset, request):
    """Opt-in 24-card index; legacy list callers retain their existing contract."""
    from .views import CatalogPagination
    params = request.query_params
    mode = params.get('mode', '')
    if mode == 'all':
        queryset = queryset.filter(origin='curated').exclude(slug='classical-education-guide')
    elif mode == 'classical-education':
        queryset = queryset.filter(slug='classical-education-guide')
    elif mode == 'published':
        queryset = queryset.filter(origin='external', presentation='ranked')
    elif mode == 'collections':
        queryset = queryset.filter(origin='external').exclude(presentation='ranked')
    elif mode in ['my-lists', 'saved']:
        if not request.user.is_authenticated:
            queryset = queryset.none()
        elif mode == 'my-lists':
            queryset = queryset.filter(owner=request.user)
        else:
            queryset = queryset.filter(preferences__user=request.user, preferences__bookmarked=True)
    elif mode:
        raise ValidationError('Choose a known ranking section.')
    countries = sorted({country for values in queryset.values_list('scope__countries', flat=True)
                        if isinstance(values, list) for country in values}, key=str.casefold)
    if field := params.get('field'):
        queryset = queryset.filter(slug='comics-graphic-novels-all-time') if field == 'graphic_novels' else queryset.filter(domain=field)
    if country := params.get('country'):
        if connection.vendor == 'sqlite':
            from .library_queries import JsonArrayContains
            queryset = queryset.filter(JsonArrayContains(F('scope__countries'), Value(country)))
        else:
            queryset = queryset.filter(scope__countries__contains=[country])
    if search := params.get('search', '').strip()[:300]:
        queryset = queryset.filter(Q(title__icontains=search) | Q(description__icontains=search) | Q(publisher__icontains=search))
    order = params.get('ordering', 'title')
    queryset = queryset.order_by('-updated_at', 'pk') if order == 'updated' else queryset.order_by(
        F('last_researched_at').asc(nulls_first=True), 'pk') if order == 'age' else queryset.order_by('title', 'pk')
    paginator = CatalogPagination()
    page = paginator.paginate_queryset(queryset, request)
    response = paginator.get_paginated_response(RankingSerializer(page, many=True,
        context={'request': request, 'summary': True}).data)
    response.data['facets'] = {'countries': countries}
    return response


def browse_page(ranking, request, *, scores=None, public=False):
    from .views import CatalogPagination
    params = request.query_params
    lens = params.get('lens', 'standing')
    if lens not in ['standing', 'reading']:
        raise ValidationError('Choose standing or reading as the perspective.')
    view = params.get('view', 'grouped')
    if view not in ['grouped', 'manual']:
        raise ValidationError('Choose country groups or manual order.')
    country_ranking = ranking.scope.get('group_by') == 'country'
    grouped = country_ranking and view == 'grouped' and scores is None
    editorial = ranking.scope.get('editorial', {}) if ranking.origin == 'curated' and ranking.presentation == 'ranked' else {}
    orders = editorial.get('orders', {})
    comparable = bool(orders.get('standing') and orders.get('reading')) and not country_ranking and scores is None
    entries = ranking.entries.filter(is_archived=False)
    if ranking.origin != 'personal':
        entries = entries.filter(Q(work__isnull=True) | Q(work__is_archived=False)).filter(Q(person__isnull=True) | Q(person__is_archived=False))
    item_key = 'work_id' if ranking.item_type == 'work' else 'person_id'

    def metadata():
        rows = list(entries.order_by('position', 'pk').values('pk', item_key, 'position', 'source_rank', 'groupings'))
        if country_ranking:
            countries = {g['country'] for row in rows for g in row['groupings'] if g.get('country')}
        else:
            countries = {country for values in entries.values_list(
                'work__countries' if ranking.item_type == 'work' else 'person__countries', flat=True)
                         if values for country in values}
        genres = Tag.objects.filter(is_archived=False, kind='genre', work__rankingentry__in=entries).values_list('name', flat=True).distinct()
        return {'rows': rows, 'countries': sorted(countries, key=str.casefold), 'genres': sorted(genres, key=str.casefold),
                'standing': position_map(orders.get('standing', {})) if not country_ranking else {},
                'reading': position_map(orders.get('reading', {})) if not country_ranking else {}}

    shared = cached_catalog(('ranking-pages', ranking.pk, ranking.revision, ranking.updated_at), metadata) if ranking.origin != 'personal' else metadata()
    standing, reading = shared['standing'], shared['reading']
    item_ids = {row[item_key] for row in shared['rows']}
    compared_ids = item_ids & standing.keys() & reading.keys()
    different_ids = {item for item in compared_ids if standing[item] != reading[item]}
    if search := params.get('search', '').strip()[:300]:
        from .search import search_catalog
        entries = entries.filter(Q(work_id__in=search_catalog(Work.objects.all(), search, kind='work', order=False).values('pk'))
            | Q(person_id__in=search_catalog(Person.objects.all(), search, kind='person', order=False).values('pk')))
    if form := params.get('form'):
        entries = entries.filter(work__form=form)
    if genre := params.get('genre'):
        entries = entries.filter(work__tags__is_archived=False, work__tags__kind='genre', work__tags__name=genre[:100])
    country = params.get('country')
    if country:
        if country_ranking:
            ids = [row['pk'] for row in shared['rows'] if any(g.get('country') == country for g in row['groupings'])]
        else:
            ids = [pk for pk, values in entries.values_list('pk', 'work__countries' if ranking.item_type == 'work' else 'person__countries') if country in (values or [])]
        entries = entries.filter(pk__in=ids)
    if params.get('differences') == 'yes':
        entries = entries.filter(**{f'{item_key}__in': different_ids})
    eligible = set(entries.values_list('pk', flat=True).distinct())
    rows = [row for row in shared['rows'] if row['pk'] in eligible]
    order = standing if lens == 'standing' else reading
    order_spec = orders.get(lens, {})
    has_saved_order = not country_ranking and isinstance(order_spec, dict) and isinstance(order_spec.get('item_ids'), list)
    scored = {row['entry_id']: row for row in scores or []}
    scored_order = {row['entry_id']: index for index, row in enumerate(scores or [], 1)}
    if scores is not None:
        rows.sort(key=lambda row: scored_order.get(row['pk'], len(scored_order) + 1))
    elif order:
        rows.sort(key=lambda row: (order.get(row[item_key], max(order.values()) + 1), row['position'], row['pk']))
    locators = []
    if grouped:
        country_order = {}
        for row in shared['rows']:
            for group in row['groupings']:
                name = group['country']
                country_order[name] = min(country_order.get(name, group['section_index']), group['section_index'])
        for row in rows:
            for group in row['groupings']:
                if not country or country == group['country']:
                    locators.append({'pk': row['pk'], 'grouping': group, 'position': row['position']})
            if not row['groupings'] and not country:
                locators.append({'pk': row['pk'], 'grouping': None, 'position': row['position']})
        locators.sort(key=lambda row: (
            country_order[row['grouping']['country']] if row['grouping'] else -1,
            row['grouping']['country'] if row['grouping'] else '',
            row['position'] if ranking.origin == 'personal' or not row['grouping'] else row['grouping']['local_rank'], row['pk']))
    else:
        locators = [{'pk': row['pk'], 'grouping': None, 'position': row['position']} for row in rows]
    paginator = CatalogPagination()
    selected = paginator.paginate_queryset(locators, request)
    objects = list(entries.filter(pk__in={row['pk'] for row in selected}).select_related(
        'work__default_edition', 'person').prefetch_related('work__authors', 'work__tags').distinct())
    work_ids = [row.work_id for row in objects if row.work_id]
    context = {}
    if not public and request.user.is_authenticated and work_ids:
        saved = {row['work_id']: row for row in LibraryItem.objects.filter(user=request.user, work_id__in=work_ids).values('work_id', 'rating', 'status')}
        completed = set(LibraryItem.objects.filter(user=request.user, work_id__in=work_ids, status='finished').values_list('work_id', flat=True))
        completed.update(ReadingAttempt.objects.filter(user=request.user, work_id__in=work_ids, status='finished').values_list('work_id', flat=True))
        memberships = membership_rows(request.user, work_ids)
        context = {item: {'rating': saved.get(item, {}).get('rating'), 'status': saved.get(item, {}).get('status'),
                          'read': item in completed, 'lists': memberships.get(item, [])} for item in work_ids}
    serialized = {row['id']: row for row in RankingBrowseEntrySerializer(objects, many=True, context={'request': request}).data}
    manual_ids = [row['pk'] for row in shared['rows']]
    results = []
    for locator in selected:
        row = dict(serialized[locator['pk']])
        item = row['work'] or row['person']
        score = scored.get(row['id'])
        display_position = None
        if scores is not None:
            display_position = scored_order.get(row['id']) if score and score['score'] is not None else None
        elif ranking.presentation != 'unranked':
            display_position = (locator['grouping']['local_rank'] if locator['grouping'] and ranking.origin != 'personal'
                else None if (grouped and locator['grouping']) or (country_ranking and ranking.origin != 'personal') else row['position'] if ranking.origin == 'personal'
                else order.get(item) if has_saved_order else row['source_rank'] if row['source_rank'] is not None else row['position'])
        row.update(display_position=display_position, grouping=locator['grouping'], score=score,
            explanation=None if public else editorial.get('entries', {}).get(str(item)), context=context.get(item) if row['work'] else None,
            comparison={'standing_rank': standing.get(item), 'reading_rank': reading.get(item),
                        'delta': standing[item] - reading[item] if item in compared_ids else None} if comparable and not public else None,
            can_move_up=bool(not public and ranking.origin == 'personal' and manual_ids and row['id'] != manual_ids[0]),
            can_move_down=bool(not public and ranking.origin == 'personal' and manual_ids and row['id'] != manual_ids[-1]))
        if public:
            row.update(rationale='', assessments={})
        results.append(row)
    response = paginator.get_paginated_response(results)
    response.data.update(revision=ranking.revision, grouped=grouped, count_unit='placements' if grouped else 'entries',
        facets={'countries': shared['countries'], 'genres': shared['genres']},
        comparison={'available': comparable and not public, 'identical': bool(compared_ids) and comparable
            and orders['standing'].get('item_ids') == orders['reading'].get('item_ids'),
            'compared': len(compared_ids), 'different': len(different_ids),
            'unpositioned': len(item_ids - compared_ids) if comparable else 0,
            'status': order_status(ranking) if comparable else 'This list preserves its source order or collection sequence.'})
    response['Cache-Control'] = 'private, no-store'
    return response
