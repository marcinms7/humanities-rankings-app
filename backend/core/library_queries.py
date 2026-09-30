"""Small, account-owned library queries shared by lists and selectors."""
from django.db import connection
from django.db.models import BooleanField, Count, F, Func, Prefetch, Q, Value
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from .models import LibraryItem, Person, Work

STATUSES = ('want_to_read', 'reading', 'paused', 'finished', 'abandoned')


class JsonArrayContains(Func):
    """Exact SQLite array membership with ORM-resolved aliases and bound values."""
    output_field = BooleanField()

    def as_sqlite(self, compiler, connection, **extra_context):
        column, column_params = compiler.compile(self.source_expressions[0])
        value, value_params = compiler.compile(self.source_expressions[1])
        return f'EXISTS (SELECT 1 FROM json_each({column}) AS library_label WHERE library_label.value = {value})', [*column_params, *value_params]


def library_queryset(user, *, compact=False):
    queryset = LibraryItem.objects.filter(user=user).select_related('edition', 'work__default_edition')
    authors = Person.objects.only('id', 'name') if compact else Person.objects.all()
    queryset = queryset.prefetch_related(Prefetch('work__authors', queryset=authors), 'work__tags')
    if compact:
        queryset = queryset.defer('notes', 'work__description', 'work__default_edition__translation_notes')
    return queryset


def filter_library(queryset, user, params, *, omit=()):
    if params.get('saved_filter'):
        from .saved_discovery import apply_discovery_filters
        matching = apply_discovery_filters(Work.objects.all(), user, params)
        queryset = queryset.filter(work_id__in=matching.values('pk'))
    if 'work' not in omit and params.get('work'):
        queryset = queryset.filter(work_id=serializers.IntegerField(min_value=1).run_validation(params['work']))
    if 'status' not in omit and params.get('status'):
        status = params['status']
        if status not in STATUSES:
            raise ValidationError({'status': 'Choose a reading status.'})
        queryset = queryset.filter(status=status)
    if 'search' not in omit and not params.get('saved_filter') and (search := params.get('search', '').strip()[:300]):
        from .search import search_catalog
        matching = search_catalog(Work.objects.all(), search, order=False)
        queryset = queryset.filter(work_id__in=matching.values('pk'))
    if 'genre' not in omit and (genre := params.get('genre')):
        queryset = queryset.filter(work__tags__kind='genre', work__tags__is_archived=False, work__tags__name=genre).distinct()
    if 'rating' not in omit and (rating := params.get('rating')):
        queryset = queryset.filter(rating__isnull=True) if rating == 'unrated' else queryset.filter(
            rating=serializers.IntegerField(min_value=1, max_value=10).run_validation(rating))
    for parameter, column in [('shelf', 'shelves'), ('tag', 'personal_tags')]:
        if parameter not in omit and (value := params.get(parameter)):
            if len(value) > 100:
                raise ValidationError({parameter: 'Use a saved label up to 100 characters.'})
            if connection.vendor == 'sqlite':
                queryset = queryset.filter(JsonArrayContains(F(column), Value(value)))
            else:
                queryset = queryset.filter(**{f'{column}__contains': [value]})
    order = params.get('ordering')
    if order in ['rating', '-rating']:
        queryset = queryset.order_by(F('rating').desc(nulls_last=True) if order == '-rating' else F('rating').asc(nulls_last=True), 'work__title', 'id')
    elif order == 'title':
        queryset = queryset.order_by('work__title', 'id')
    else:
        queryset = queryset.order_by('-updated_at', '-id')
    return queryset


def library_facets(user, params):
    # Facets scan only saved labels. Notes, books, editions and image fields are
    # not loaded to build dropdowns or reading-status counts.
    counted = filter_library(LibraryItem.objects.filter(user=user), user, params, omit=('status',))
    counts = {row['status']: row['total'] for row in counted.order_by().values('status').annotate(total=Count('pk', distinct=True))}
    base = filter_library(LibraryItem.objects.filter(user=user), user, params, omit=('status', 'shelf', 'tag'))
    shelves, tags = set(), set()
    for row_shelves, row_tags in base.order_by().values_list('shelves', 'personal_tags').distinct():
        shelves.update(row_shelves)
        tags.update(row_tags)
    return {'total': sum(counts.values()), 'statuses': {status: counts.get(status, 0) for status in STATUSES},
            'shelves': sorted(shelves, key=str.casefold), 'tags': sorted(tags, key=str.casefold)}
