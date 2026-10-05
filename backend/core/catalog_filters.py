"""Multi-choice catalog filters and distinct, prospective result counts.

JSON-array query values preserve commas and historical country labels. Missing
``*_any`` inherits a legacy singular value/preset; ``[]`` deliberately clears it.
"""
import json
from collections import defaultdict

from django.db import connection
from django.db.models import BooleanField, F, Func, Q, Value
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from .models import Tag, Work


FACETS = ('field', 'form', 'country', 'genre')
FIELDS = ('literature', 'philosophy', 'nonfiction', 'manga')
MAX_SELECTIONS = 50


class CatalogFacetOptionSerializer(serializers.Serializer):
    value = serializers.CharField()
    include_count = serializers.IntegerField(min_value=0)
    exclude_count = serializers.IntegerField(min_value=0)


class CatalogFacetSerializer(serializers.Serializer):
    include = serializers.ListField(child=serializers.CharField())
    exclude = serializers.ListField(child=serializers.CharField())
    inherited = serializers.BooleanField()
    options = CatalogFacetOptionSerializer(many=True)


class CatalogFacetGroupsSerializer(serializers.Serializer):
    field = CatalogFacetSerializer()
    form = CatalogFacetSerializer()
    country = CatalogFacetSerializer()
    genre = CatalogFacetSerializer()


class CatalogFacetsSerializer(serializers.Serializer):
    countries = serializers.ListField(child=serializers.CharField())
    genres = serializers.ListField(child=serializers.CharField())
    genre_catalog = serializers.ListField(child=serializers.CharField())
    result_count = serializers.IntegerField(min_value=0)
    facets = CatalogFacetGroupsSerializer()


class _CountryContains(Func):
    output_field = BooleanField()

    def as_sqlite(self, compiler, connection, **extra_context):
        column, column_params = compiler.compile(self.source_expressions[0])
        value, value_params = compiler.compile(self.source_expressions[1])
        return (
            f"(json_type({column}) = 'array' AND EXISTS (SELECT 1 FROM json_each({column}) "
            f"AS catalog_country WHERE catalog_country.value = {value}))",
            [*column_params, *column_params, *value_params],
        )


def _array(params, key):
    raw = params.get(key)
    if raw is None:
        return None
    if len(raw) > 16000:
        raise ValidationError({key: 'Choose at most 50 values.'})
    try:
        values = json.loads(raw)
    except (ValueError, TypeError):
        raise ValidationError({key: 'Use a JSON array of filter values.'})
    if not isinstance(values, list) or len(values) > MAX_SELECTIONS or any(
        not isinstance(value, str) or not value.strip() or len(value) > 300
        for value in values
    ):
        raise ValidationError({key: 'Choose at most 50 nonempty filter values (300 characters each).'})
    return list(dict.fromkeys(values))


def catalog_base(works, user, params):
    """Resolve saved private constraints once, leaving the four facets separate."""
    saved = {}
    if params.get('saved_filter'):
        from .saved_discovery import effective_filters, apply_discovery_filters
        # Multi-values supersede a singular override as well as the preset. Do
        # not feed JSON arrays into the existing single-value preset serializer.
        legacy = params.copy()
        for name in ('field', 'country', 'genre'):
            if f'{name}_any' in params:
                legacy[name] = ''
        saved = effective_filters(user, legacy)
        fixed = {**saved, 'field': '', 'country': '', 'genre': ''}
        works = apply_discovery_filters(works, user, fixed)
    elif term := params.get('search'):
        from .search import search_catalog
        works = search_catalog(works, term)
    if author := params.get('author'):
        if not author.isdigit():
            raise ValidationError('Author must be an ID.')
        works = works.filter(authors__id=author)

    selections = {}
    for name in FACETS:
        included = _array(params, f'{name}_any')
        inherited = included is None and name not in params and bool(saved.get(name))
        if included is None:
            singular = params.get(name, saved.get(name, ''))
            included = [singular] if singular and singular != 'all' else []
        excluded = _array(params, f'{name}_not') or []
        if name in ('field', 'form'):
            allowed = FIELDS if name == 'field' else Work.FORMS
            if any(value not in allowed for value in included + excluded):
                raise ValidationError({name: 'Choose a supported catalog value.'})
        if any(value in excluded for value in included):
            raise ValidationError({name: 'A value cannot be both included and excluded.'})
        selections[name] = {'include': included, 'exclude': excluded, 'inherited': inherited}
    return works, selections


def _country_condition(values):
    condition = Q()
    for value in values:
        if connection.vendor == 'sqlite':
            condition |= Q(_CountryContains(F('countries'), Value(value)))
        else:
            condition |= Q(countries__contains=[value])
    return condition


def apply_catalog_selections(works, selections):
    for name, selection in selections.items():
        for mode in ('include', 'exclude'):
            values = selection[mode]
            if not values:
                continue
            if name == 'country':
                condition = _country_condition(values)
            elif name == 'genre':
                memberships = Work.tags.through.objects.filter(
                    tag__kind='genre', tag__is_archived=False, tag__name__in=values)
                condition = Q(pk__in=memberships.values('work_id'))
            else:
                condition = Q(**{f'{name}__in': values})
            works = works.filter(condition) if mode == 'include' else works.exclude(condition)
    return works


def catalog_facets(works, selections):
    """Calculate all toggles in memory from two bounded SQL reads, not N queries.

    Sets deduplicate books with overlapping country/genre associations. Each
    number is the full result total after that button is toggled, preserving
    every other active constraint; it is never a sum of overlapping buckets.
    """
    rows = list(works.order_by().values_list('pk', 'field', 'form', 'countries'))
    universe = {row[0] for row in rows}
    groups = {name: defaultdict(set) for name in FACETS}
    for pk, field, form, countries in rows:
        groups['field'][field].add(pk)
        groups['form'][form].add(pk)
        for country in countries if isinstance(countries, list) else []:
            if isinstance(country, str) and country.strip():
                groups['country'][country].add(pk)
    memberships = Work.tags.through.objects.filter(
        work_id__in=works.order_by().values('pk'), tag__kind='genre', tag__is_archived=False
    ).values_list('work_id', 'tag__name')
    for pk, genre in memberships:
        groups['genre'][genre].add(pk)

    def union(name, values):
        result = set()
        for value in values:
            result.update(groups[name].get(value, set()))
        return result

    def matches(name, include, exclude):
        return (union(name, include) if include else universe) - union(name, exclude)

    current = {name: matches(name, selection['include'], selection['exclude'])
               for name, selection in selections.items()}
    total = universe.intersection(*current.values())
    facets = {}
    for name, selection in selections.items():
        other = universe.intersection(*(ids for key, ids in current.items() if key != name))
        values = set(groups[name]) | set(selection['include']) | set(selection['exclude'])
        if name == 'field':
            values.update(FIELDS)
        if name == 'form':
            values.update(Work.FORMS)
        options = []
        for value in sorted(values, key=str.casefold):
            counts = {}
            for mode in ('include', 'exclude'):
                include, exclude = set(selection['include']), set(selection['exclude'])
                target, opposite = (include, exclude) if mode == 'include' else (exclude, include)
                if value in target:
                    target.remove(value)
                else:
                    target.add(value)
                    opposite.discard(value)
                counts[f'{mode}_count'] = len(other & matches(name, include, exclude))
            options.append({'value': value, **counts})
        facets[name] = {**selection, 'options': options}
    return {
        'countries': sorted((value for value, ids in groups['country'].items() if ids & total), key=str.casefold),
        'genres': sorted((value for value, ids in groups['genre'].items() if ids & total), key=str.casefold),
        'genre_catalog': Tag.GENRES,
        'result_count': len(total),
        'facets': facets,
    }
