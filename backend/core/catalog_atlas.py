"""Read-only geography/period exploration of saved catalog metadata.

Only public catalog facts are cached. Reading overlays are recomputed for the
requesting account and never enter the shared cache. A country's label is an
association recorded on the work, not a claim about birthplace or borders.
"""
from collections import defaultdict
from dataclasses import dataclass

from django.db.models import Prefetch
from rest_framework import permissions, serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .catalog_cache import cached_catalog
from .models import LibraryItem, Person, ReadingAttempt, Work
from .serializers import WorkCardSerializer


UNKNOWN_COUNTRY = '__unknown__'
UNKNOWN_CENTURY = 'unknown'


class AtlasFacetSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    count = serializers.IntegerField()
    saved = serializers.IntegerField()
    read = serializers.IntegerField()


class AtlasSummarySerializer(serializers.Serializer):
    catalog = serializers.IntegerField()
    saved = serializers.IntegerField()
    read = serializers.IntegerField()
    undated = serializers.IntegerField()
    unlocated = serializers.IntegerField()
    invalid_year = serializers.IntegerField()
    invalid_countries = serializers.IntegerField()


class AtlasWorkSerializer(serializers.Serializer):
    book = WorkCardSerializer()
    original_year = serializers.IntegerField(allow_null=True)
    century = serializers.CharField()
    date_status = serializers.ChoiceField(choices=['known', 'missing', 'invalid'])
    saved = serializers.BooleanField()
    read = serializers.BooleanField()
    status = serializers.CharField(allow_null=True)


class CatalogAtlasSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = AtlasWorkSerializer(many=True)
    summary = AtlasSummarySerializer()
    countries = AtlasFacetSerializer(many=True)
    centuries = AtlasFacetSerializer(many=True)
    authenticated = serializers.BooleanField()


class AtlasParameters(serializers.Serializer):
    country = serializers.CharField(max_length=1000, allow_blank=True, default='', trim_whitespace=False)
    century = serializers.CharField(max_length=12, allow_blank=True, default='')
    overlay = serializers.ChoiceField(choices=['all', 'saved', 'read'], default='all')
    q = serializers.CharField(max_length=300, allow_blank=True, default='')
    field = serializers.ChoiceField(choices=['', 'literature', 'philosophy', 'nonfiction', 'manga'], default='')

    def validate_century(self, value):
        if value in {'', UNKNOWN_CENTURY}:
            return value
        try:
            century = int(value)
        except ValueError as error:
            raise serializers.ValidationError('Choose a century or the unknown-date group.') from error
        # Match the supported saved-work year range, with no year/century zero.
        if not -100 <= century <= 30 or century == 0:
            raise serializers.ValidationError('Choose a century between 100 BCE and 30 CE, without zero.')
        return str(century)


class AtlasPagination(PageNumberPagination):
    page_size = 24
    page_size_query_param = None


def year_metadata(year):
    if year is None:
        return None, UNKNOWN_CENTURY, 'missing'
    if type(year) is not int or year == 0 or not -10000 <= year <= 3000:
        return None, UNKNOWN_CENTURY, 'invalid'
    century = ((abs(year) - 1) // 100 + 1) * (-1 if year < 0 else 1)
    return year, str(century), 'known'


def country_metadata(value):
    if not isinstance(value, list):
        return (), True
    valid = tuple(dict.fromkeys(label for label in value if isinstance(label, str) and label.strip()))
    invalid = any(not isinstance(label, str) or not label.strip() for label in value)
    return valid, invalid


def century_label(key):
    if key == UNKNOWN_CENTURY:
        return 'Unknown date'
    century = int(key)
    value = abs(century)
    suffix = 'th' if 11 <= value % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(value % 10, 'th')
    return f'{value}{suffix} century {"BCE" if century < 0 else "CE"}'


@dataclass(frozen=True)
class CatalogRecord:
    id: int
    title: str
    field: str
    original_year: int | None
    century: str
    date_status: str
    countries: tuple[str, ...]
    invalid_countries: bool


def catalog_records():
    def load():
        records = []
        rows = Work.objects.filter(is_archived=False).order_by().values_list(
            'pk', 'title', 'field', 'original_year', 'countries')
        for pk, title, field, year, countries in rows.iterator(chunk_size=2000):
            normalized_year, century, date_status = year_metadata(year)
            labels, invalid = country_metadata(countries)
            records.append(CatalogRecord(pk, title, field, normalized_year, century, date_status, labels, invalid))
        return tuple(sorted(records, key=lambda record: (record.title.casefold(), record.id)))

    return cached_catalog('catalog-atlas-metadata-v1', load, copy=False)


def matches_country(record, country):
    if country == UNKNOWN_COUNTRY:
        return not record.countries
    return not country or country in record.countries


def facet_counts(records, saved, read, *, kind):
    counts = defaultdict(lambda: {'count': 0, 'saved': 0, 'read': 0})
    for record in records:
        labels = (record.countries or (UNKNOWN_COUNTRY,)) if kind == 'country' else (record.century,)
        for label in labels:
            counts[label]['count'] += 1
            counts[label]['saved'] += record.id in saved
            counts[label]['read'] += record.id in read
    if kind == 'country':
        keys = sorted(counts, key=lambda key: (key == UNKNOWN_COUNTRY, key.casefold(), key))
    else:
        keys = sorted(counts, key=lambda key: (key == UNKNOWN_CENTURY, int(key) if key != UNKNOWN_CENTURY else 0))
    return [{'key': key, 'label': ('Unknown association' if key == UNKNOWN_COUNTRY else key)
             if kind == 'country' else century_label(key), **counts[key]} for key in keys]


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def catalog_atlas(request):
    parameters = AtlasParameters(data=request.query_params)
    parameters.is_valid(raise_exception=True)
    params = parameters.validated_data
    authenticated = request.user.is_authenticated
    if not authenticated and params['overlay'] != 'all':
        raise ValidationError({'overlay': 'Sign in to explore your saved or read books.'})

    # These account-owned sets must never be included in catalog_records' cache.
    saved = dict(LibraryItem.objects.filter(user=request.user).values_list('work_id', 'status')) if authenticated else {}
    read = {pk for pk, status in saved.items() if status == 'finished'}
    if authenticated:
        read.update(ReadingAttempt.objects.filter(user=request.user, status='finished').values_list('work_id', flat=True))

    records = catalog_records()
    if params['field']:
        records = tuple(record for record in records if record.field == params['field'])
    if params['q']:
        from .search import search_catalog
        matching = set(search_catalog(Work.objects.filter(is_archived=False), params['q'], order=False).values_list('pk', flat=True))
        records = tuple(record for record in records if record.id in matching)

    by_country = tuple(record for record in records if matches_country(record, params['country']))
    by_century = tuple(record for record in records if not params['century'] or record.century == params['century'])
    selected = tuple(record for record in by_country if not params['century'] or record.century == params['century'])
    summary = {
        'catalog': len(selected),
        'saved': sum(record.id in saved for record in selected),
        'read': sum(record.id in read for record in selected),
        'undated': sum(record.century == UNKNOWN_CENTURY for record in selected),
        'unlocated': sum(not record.countries for record in selected),
        'invalid_year': sum(record.date_status == 'invalid' for record in selected),
        'invalid_countries': sum(record.invalid_countries for record in selected),
    }
    if params['overlay'] != 'all':
        included = saved if params['overlay'] == 'saved' else read
        selected = tuple(record for record in selected if record.id in included)

    paginator = AtlasPagination()
    page = paginator.paginate_queryset(selected, request)
    works = Work.objects.filter(pk__in=[record.id for record in page], is_archived=False).select_related('default_edition').prefetch_related(
        Prefetch('authors', queryset=Person.objects.filter(is_archived=False).only('id', 'name')), 'tags')
    books = {}
    for work in works:
        if work.default_edition and work.default_edition.is_archived:
            work.default_edition = None
        books[work.pk] = work
    results = []
    for record in page:
        work = books.get(record.id)
        if work is None:  # A concurrent archive must not expose a stale card.
            continue
        book = dict(WorkCardSerializer(work, context={'request': request}).data)
        book['countries'] = list(record.countries)
        results.append({'book': book, 'original_year': record.original_year,
                        'century': record.century, 'date_status': record.date_status,
                        'saved': record.id in saved, 'read': record.id in read,
                        'status': saved.get(record.id)})
    response = Response({
        'count': paginator.page.paginator.count,
        'next': paginator.get_next_link(), 'previous': paginator.get_previous_link(),
        'results': results, 'summary': summary,
        'countries': facet_counts(by_century, saved, read, kind='country'),
        'centuries': facet_counts(by_country, saved, read, kind='century'),
        'authenticated': authenticated,
    })
    response['Cache-Control'] = 'private, no-store'
    return response
