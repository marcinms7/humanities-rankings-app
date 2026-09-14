"""Read-only, permission-scoped discovery. Never synthesizes a universal score."""
from collections import defaultdict
from django.db.models import CharField, Count, OuterRef, Q, Subquery, Value
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Coalesce, NullIf
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .models import RankingEntry, ResearchSource, Work
from .reading_insights import shared_lists


@api_view(['GET'])
@permission_classes([AllowAny])
def placements(request, pk):
    work = get_object_or_404(Work, pk=pk, is_archived=False)
    totals = RankingEntry.objects.filter(ranking_id=OuterRef('ranking_id'), is_archived=False).order_by().values('ranking_id').annotate(n=Count('pk')).values('n')
    entries = RankingEntry.objects.filter(work=work, is_archived=False, ranking__in=shared_lists(request.user)).annotate(total=Subquery(totals))
    rows = []
    for e in entries.values('ranking_id', 'ranking__title', 'ranking__slug', 'ranking__origin', 'ranking__presentation',
                            'ranking__domain', 'ranking__publisher', 'ranking__revision', 'ranking__last_researched_at',
                            'ranking__scope__editorial__orders__standing__item_ids', 'position', 'source_rank', 'groupings', 'total'):
        position = e['source_rank'] or e['position']
        order = e['ranking__scope__editorial__orders__standing__item_ids']
        if e['ranking__origin'] == 'curated' and isinstance(order, list) and work.pk in order:
            position = order.index(work.pk) + 1
        rows.append(dict(id=e['ranking_id'], title=e['ranking__title'], slug=e['ranking__slug'],
            origin=e['ranking__origin'], presentation=e['ranking__presentation'], domain=e['ranking__domain'],
            publisher=e['ranking__publisher'], revision=e['ranking__revision'], updated=e['ranking__last_researched_at'],
            position=position if e['ranking__presentation'] != 'unranked' and not e['groupings'] else None, total=e['total'], groupings=e['groupings']))
    response = Response({'work': work.pk, 'placements': rows, 'note': 'Placements keep their original scope and order. Collections are not merit rankings; no average, percentile or universal score is computed.'})
    response['Cache-Control'] = 'private, no-store'
    return response


def metadata_text(*keys):
    return Coalesce(*(NullIf(NullIf(KeyTextTransform(key, 'metadata'), Value('null')), Value('')) for key in keys), Value(''), output_field=CharField())


@api_view(['GET'])
def source_explorer(request):
    from .views import CatalogPagination
    base = ResearchSource.objects.filter(is_archived=False, ranking__in=shared_lists(request.user))
    repeated = base.filter(url=OuterRef('url')).order_by().values('url').annotate(n=Count('ranking_id', distinct=True)).values('n')
    qs = base.annotate(language_label=metadata_text('language', 'report_language'),
                       geography_label=metadata_text('country', 'region', 'region_language', 'report_language_region'),
                       access_label=metadata_text('report_access_status', 'access_level', 'report_access'),
                       reuse_count=Subquery(repeated))
    p = request.query_params
    if search := p.get('search', '').strip()[:300]:
        qs = qs.filter(Q(title__icontains=search) | Q(publisher__icontains=search) | Q(source_id__icontains=search) | Q(url__icontains=search))
    if publisher := p.get('publisher', '').strip()[:240]:
        qs = qs.filter(publisher__icontains=publisher)
    if family := p.get('family', '').strip()[:80]:
        qs = qs.filter(family=family)
    if language := p.get('language', '').strip()[:120]:
        if language == 'unknown':
            qs = qs.filter(language_label='')
        else:
            aliases = {'english': 'en', 'japanese': 'ja', 'chinese': 'zh', 'polish': 'pl', 'french': 'fr', 'german': 'de', 'spanish': 'es', 'italian': 'it', 'arabic': 'ar', 'russian': 'ru'}
            qs = qs.filter(Q(language_label__icontains=language) | Q(language_label__iexact=aliases.get(language.lower(), language)) | Q(geography_label__icontains=language))
    if country := p.get('country', '').strip()[:120]:
        qs = qs.filter(geography_label='') if country == 'unknown' else qs.filter(geography_label__icontains=country)
    if p.get('status') in ('consulted', 'lead'):
        qs = qs.filter(eligible=p['status'] == 'consulted')
    if ranking := p.get('ranking', ''):
        from .views import positive_id
        qs = qs.filter(ranking_id=positive_id(ranking, 'ranking'))
    if p.get('reused') == 'yes':
        reused_urls = base.order_by().values('url').annotate(n=Count('ranking_id', distinct=True)).filter(n__gt=1).values('url')
        qs = qs.filter(url__in=reused_urls)
    if url := p.get('url', ''):
        qs = qs.filter(url=url[:1000])
    paginator = CatalogPagination()
    page = paginator.paginate_queryset(qs.select_related('ranking').defer('metadata', 'ranking__scope').order_by('title', 'ranking__title', 'pk'), request)
    uses = defaultdict(dict)
    for item in base.filter(url__in={s.url for s in page}).values('url', 'ranking_id', 'ranking__title', 'eligible'):
        saved = uses[item['url']].setdefault(item['ranking_id'], dict(id=item['ranking_id'], title=item['ranking__title'], eligible=False))
        saved['eligible'] = saved['eligible'] or item['eligible']
    rows = [dict(id=s.pk, source_id=s.source_id, title=s.title, url=s.url, publisher=s.publisher,
        family=s.family, language=s.language_label, geography=s.geography_label, access=s.access_label,
        eligible=s.eligible, evidence=s.evidence, limitations=s.limitations, consulted_on=s.consulted_on,
        ranking=dict(id=s.ranking_id, title=s.ranking.title), reuse_count=s.reuse_count,
        reused_in=list(uses[s.url].values())) for s in page]
    response = paginator.get_paginated_response(rows)
    response.data['families'] = list(base.order_by('family').values_list('family', flat=True).distinct())
    response.data['rankings'] = list(shared_lists(request.user).filter(sources__is_archived=False).values('id', 'title').distinct().order_by('title'))
    response.data['note'] = 'One record per target. Consultation labels reproduce saved ledgers, including owner-reported access; they are not a fresh verification. Reuse means the exact saved URL occurs in multiple visible rankings, not independent votes. Unrecorded language/geography stays unknown; a source’s topic or target country is not its publication country.'
    response['Cache-Control'] = 'private, no-store'
    return response
