"""Account-owned discovery filters, shared by catalog, library and planner queries."""
from django.db import connection, transaction, IntegrityError
from django.db.models import Case, Count, Exists, F, IntegerField, OuterRef, Q, Subquery, Value, When
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, NullIf
from django.shortcuts import get_object_or_404
from rest_framework import permissions, serializers, viewsets
from rest_framework.exceptions import NotAuthenticated, ValidationError

from .mutations import MutationGuardMixin
from .models import LibraryItem, RankingEntry, RankingPreference, ReadingAttempt, SavedDiscoveryFilter, Work
from .reading_insights import shared_lists


class DiscoveryFiltersSerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True, max_length=300, default='')
    field = serializers.ChoiceField(required=False, choices=['', 'literature', 'philosophy', 'nonfiction', 'manga'], default='')
    genre = serializers.CharField(required=False, allow_blank=True, max_length=100, default='')
    country = serializers.CharField(required=False, allow_blank=True, max_length=100, default='')
    minimum = serializers.IntegerField(required=False, min_value=0, max_value=1000, default=0)
    max_pages = serializers.IntegerField(required=False, min_value=0, max_value=100000, default=0)
    unread = serializers.ChoiceField(required=False, choices=['', 'yes'], default='')
    wishlist = serializers.ChoiceField(required=False, choices=['', 'yes'], default='')
    new_authors = serializers.ChoiceField(required=False, choices=['', 'yes'], default='')
    bookmarked = serializers.ChoiceField(required=False, choices=['', 'yes'], default='')

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise ValidationError({'non_field_errors': ['Filters must be an object.']})
        unknown = set(data) - set(self.fields)
        if unknown:
            raise ValidationError({'non_field_errors': [f'Unsupported filters: {", ".join(sorted(unknown))}.']})
        return super().to_internal_value(data)


FILTER_KEYS = tuple(DiscoveryFiltersSerializer().fields)


def effective_filters(user, params):
    """Resolve an owned preset, then override only explicitly supplied supported keys."""
    data = {}
    if saved_id := params.get('saved_filter'):
        if not user.is_authenticated:
            raise NotAuthenticated('Sign in to use your saved filters.')
        try:
            saved_id = int(saved_id)
            if saved_id < 1:
                raise ValueError
        except (ValueError, TypeError):
            raise ValidationError('Choose a saved filter.')
        saved = get_object_or_404(SavedDiscoveryFilter.objects.filter(user=user), pk=saved_id)
        data.update(saved.filters)
    data.update({key: params.get(key) for key in FILTER_KEYS if key in params})
    serializer = DiscoveryFiltersSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    filters = serializer.validated_data
    if not user.is_authenticated and any(filters[key] for key in ['unread', 'wishlist', 'new_authors', 'bookmarked']):
        raise NotAuthenticated('Sign in to filter using your reading history or bookmarks.')
    return filters


def apply_discovery_filters(works, user, params):
    """Apply identical semantics wherever saved filters are used; returns a Work QS.

    A saved library length is frozen history, including an explicitly unknown length.
    It must never silently fall back to a different catalog edition.
    """
    filters = effective_filters(user, params)
    entries = RankingEntry.objects.filter(
        ranking__in=shared_lists(user), ranking__presentation='ranked', is_archived=False)
    counts = entries.order_by().values('work_id').annotate(n=Count('ranking_id', distinct=True))
    works = works.annotate(ranking_count=Subquery(counts.filter(work_id=OuterRef('pk')).values('n')))
    if user.is_authenticated:
        saved = LibraryItem.objects.filter(user=user, work_id=OuterRef('pk')).annotate(
            snapshot_pages=Case(
                When(reading_basis__has_key='pages', then=Cast(NullIf(
                    KeyTextTransform('pages', 'reading_basis'), Value('null')), IntegerField())),
                default=Case(When(edition__isnull=False, then='edition__pages'),
                             default='work__default_edition__pages', output_field=IntegerField()),
                output_field=IntegerField()))
        works = works.annotate(saved_status=Subquery(saved.values('status')[:1]),
            chosen_edition=Subquery(saved.values('pk')[:1]), chosen_pages=Subquery(saved.values('snapshot_pages')[:1]))
        works = works.annotate(discovery_pages=Case(When(chosen_edition__isnull=False, then='chosen_pages'),
            default='default_edition__pages', output_field=IntegerField()))
    else:
        works = works.annotate(discovery_pages=Case(default='default_edition__pages', output_field=IntegerField()))
    if filters['minimum']:
        works = works.filter(ranking_count__gte=filters['minimum'])
    if filters['max_pages']:
        works = works.filter(discovery_pages__gte=1, discovery_pages__lte=filters['max_pages'])
    if filters['wishlist']:
        works = works.filter(saved_status='want_to_read')
    if filters['unread']:
        works = works.exclude(pk__in=LibraryItem.objects.filter(user=user, status='finished').values('work_id'))
        works = works.exclude(pk__in=ReadingAttempt.objects.filter(user=user, status='finished').values('work_id'))
    if filters['new_authors']:
        attempted = Q(status__in=['reading', 'paused', 'finished', 'abandoned']) | Q(current_page__gt=0) | Q(started_on__isnull=False)
        seen_works = Work.objects.filter(
            Q(pk__in=LibraryItem.objects.filter(attempted, user=user).values('work_id'))
            | Q(pk__in=ReadingAttempt.objects.filter(attempted, user=user).values('work_id')))
        seen_authors = seen_works.filter(authors__isnull=False).values('authors__pk')
        works = works.filter(Exists(Work.authors.through.objects.filter(work_id=OuterRef('pk')))).exclude(authors__pk__in=seen_authors)
    if filters['bookmarked']:
        bookmarked = RankingPreference.objects.filter(user=user, bookmarked=True).values('ranking_id')
        works = works.filter(pk__in=entries.filter(ranking_id__in=bookmarked).values('work_id'))
    if filters['search']:
        from .search import search_catalog
        works = search_catalog(works, filters['search'])
    if filters['field']:
        works = works.filter(field=filters['field'])
    if filters['genre']:
        works = works.filter(tags__kind='genre', tags__is_archived=False, tags__name=filters['genre'])
    if filters['country']:
        if connection.vendor == 'sqlite':
            from .library_queries import JsonArrayContains
            works = works.filter(JsonArrayContains(F('countries'), Value(filters['country'])))
        else:
            works = works.filter(countries__contains=[filters['country']])
    # Correlated subqueries/EXISTS preserve one row per work. The genre name is
    # unique and its through pair is unique; a global DISTINCT forced SQLite to
    # calculate every annotation for the whole catalog before applying LIMIT.
    return works


class SavedDiscoveryFilterSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedDiscoveryFilter
        fields = ['id', 'name', 'filters', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_filters(self, value):
        serializer = DiscoveryFiltersSerializer(data=value)
        serializer.is_valid(raise_exception=True)
        return dict(serializer.validated_data)

    def validate_name(self, value):
        name = value.strip()
        if not name:
            raise ValidationError('Give this filter a name.')
        existing = SavedDiscoveryFilter.objects.filter(user=self.context['request'].user, name=name)
        if self.instance:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise ValidationError('You already have a filter with this name.')
        return name


class SavedDiscoveryFilterViewSet(MutationGuardMixin, viewsets.ModelViewSet):
    serializer_class = SavedDiscoveryFilterSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        return SavedDiscoveryFilter.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        self._save(serializer)

    def perform_update(self, serializer):
        self._save(serializer)

    def _save(self, serializer):
        try:
            with transaction.atomic():
                serializer.save(user=self.request.user)
        except IntegrityError as error:
            raise ValidationError({'name': 'You already have a filter with this name.'}) from error

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        return response
