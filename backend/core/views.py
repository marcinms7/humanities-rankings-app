import json
import uuid
from datetime import date
from django.conf import settings
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q, Count, Prefetch, F, OuterRef, Subquery, IntegerField
from django.db.models.functions import Coalesce
from rest_framework.pagination import PageNumberPagination
from .mutations import MutationGuardMixin, VersionedEditMixin, mutation_guard, require_current
from .models import ReadingAttempt, ReadingGoal
from django.http import JsonResponse, FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_protect
from django.views.decorators.http import require_http_methods
from rest_framework import viewsets, permissions, serializers
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.response import Response
from backend.domain.planning import month_range, suggest_plan
from backend.domain.reading_capacity import CAPACITY_VERSION, effort_per_page
from .reading_calendar import reading_budget
from backend.domain.scoring import weighted_score
from .models import (Person, Tag, Work, Edition, Ranking, RankingEntry, RankingRevision, ResearchSource,
                     RankingPreference, LibraryItem, PlanItem)
from .serializers import (UserSerializer, PersonSerializer, WorkSerializer, EditionSerializer, RankingSerializer,
                          EntrySerializer, SourceSerializer, PreferenceSerializer, LibrarySerializer, PlanSerializer)


@ensure_csrf_cookie
@csrf_protect
@require_http_methods(['GET', 'POST'])
def session_view(request):
    User = get_user_model()
    if request.method == 'POST':
        from .accounts import limited
        if limited(request, 'session', 30):
            return JsonResponse({'detail': 'Too many attempts. Please try again in 15 minutes.'}, status=429)
        try:
            data = json.loads(request.body)
            if not isinstance(data, dict):
                raise ValueError()
        except (ValueError, TypeError):
            return JsonResponse({'detail': 'Send a JSON object.'}, status=400)
        if data.get('action') == 'logout':
            logout(request)
        elif data.get('action') == 'setup':
            if not settings.DEBUG or User.objects.exists():
                return JsonResponse({'detail': 'Initial setup has already been completed or is disabled.'}, status=403)
            username = str(data.get('username', '')).strip()
            password = str(data.get('password', ''))
            user = User(username=username, display_name=str(data.get('display_name', ''))[:100], is_staff=True, is_superuser=True)
            try:
                user.full_clean(exclude=['password'])
                validate_password(password, user)
            except DjangoValidationError as error:
                return JsonResponse({'detail': error.messages}, status=400)
            user.set_password(password)
            user.save()
            login(request, user)
        elif data.get('action') == 'login':
            if not isinstance(data.get('username'), str) or not isinstance(data.get('password'), str):
                return JsonResponse({'detail': 'Enter a username and password.'}, status=400)
            user = authenticate(request, username=data.get('username'), password=data.get('password'))
            if user is None:
                return JsonResponse({'detail': 'The username or password is incorrect.'}, status=400)
            login(request, user)
        else:
            return JsonResponse({'detail': 'Unknown session action.'}, status=400)
    return JsonResponse({'user': UserSerializer(request.user).data if request.user.is_authenticated else None,
                         'setup_required': settings.DEBUG and not User.objects.exists()})


@api_view(['GET', 'PATCH'])
@mutation_guard
def profile(request):
    if request.method == 'PATCH':
        with transaction.atomic():
            request.user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
            serializer = UserSerializer(request.user, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
    return Response(UserSerializer(request.user).data)


class CatalogPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method == 'DELETE':
            return False
        return request.method in permissions.SAFE_METHODS or (request.user.is_authenticated and request.user.is_staff)


class CatalogPagination(PageNumberPagination):
    page_size = 24
    page_size_query_param = 'page_size'
    max_page_size = 100


class WorkViewSet(MutationGuardMixin, VersionedEditMixin, viewsets.ModelViewSet):
    pagination_class = CatalogPagination
    serializer_class = WorkSerializer
    permission_classes = [CatalogPermission]
    queryset = Work.objects.filter(is_archived=False).select_related('default_edition').prefetch_related('authors', 'tags')

    def get_serializer_class(self):
        if self.action == 'list' and self.request.query_params.get('compact') == '1':
            from .serializers import WorkCardSerializer
            return WorkCardSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == 'list' and self.request.query_params.get('saved_filter'):
            from .saved_discovery import apply_discovery_filters
            qs = apply_discovery_filters(qs, self.request.user, self.request.query_params)
        if (term := self.request.query_params.get('search')) and not (self.action == 'list' and self.request.query_params.get('saved_filter')):
            from .search import search_catalog
            qs = search_catalog(qs, term)
        for name in ['form', 'field']:
            if self.request.query_params.get(name):
                qs = qs.filter(**{name: self.request.query_params[name]})
        if genre := self.request.query_params.get('genre'):
            qs = qs.filter(tags__kind='genre', tags__is_archived=False, tags__name=genre).distinct()
        if author := self.request.query_params.get('author'):
            if not author.isdigit():
                raise ValidationError('Author must be an ID.')
            qs = qs.filter(authors__id=author)
        if country := self.request.query_params.get('country'):
            from django.db import connection
            if connection.vendor == 'sqlite':
                qs = qs.extra(where=['EXISTS (SELECT 1 FROM json_each(core_work.countries) WHERE value = %s)'], params=[country])
            else:
                qs = qs.filter(countries__contains=[country])
        if self.action == 'list' and self.request.query_params.get('compact') == '1':
            qs = qs.defer('description', 'default_edition__translation_notes').prefetch_related(None).prefetch_related(
                Prefetch('authors', queryset=Person.objects.only('id', 'name')), 'tags')
        return qs

    @action(detail=False, methods=['get'])
    def facets(self, request):
        works = Work.objects.filter(is_archived=False)
        if field := request.query_params.get('field'):
            works = works.filter(field=field)
        genres = Tag.objects.filter(is_archived=False, kind='genre', work__in=works).values_list('name', flat=True).distinct()
        return Response({'countries': sorted({c for row in works.values_list('countries', flat=True) for c in row}),
                         'genres': sorted(genres, key=str.casefold), 'genre_catalog': Tag.GENRES})

    @action(detail=True, methods=['get'])
    def editions(self, request, pk=None):
        return Response(EditionSerializer(self.get_object().editions.filter(is_archived=False), many=True, context={'request': request}).data)

    @action(detail=True, methods=['get'])
    def rankings(self, request, pk=None):
        from .reading_insights import membership_rows
        work = self.get_object()
        return Response(membership_rows(request.user, [work.pk]).get(work.pk, []))


class PersonViewSet(MutationGuardMixin, VersionedEditMixin, viewsets.ModelViewSet):
    pagination_class = CatalogPagination
    serializer_class = PersonSerializer
    permission_classes = [CatalogPermission]
    queryset = Person.objects.filter(is_archived=False)

    def get_queryset(self):
        qs = super().get_queryset()
        if search := self.request.query_params.get('search'):
            from .search import search_catalog
            qs = search_catalog(qs, search, kind='person')
        return qs


class EditionViewSet(MutationGuardMixin, VersionedEditMixin, viewsets.ModelViewSet):
    serializer_class = EditionSerializer
    permission_classes = [CatalogPermission]
    queryset = Edition.objects.filter(is_archived=False).select_related('work')

    def perform_update(self, serializer):
        if serializer.validated_data.get('work', serializer.instance.work) != serializer.instance.work:
            raise ValidationError('An edition cannot be reassigned to a different work.')
        serializer.save()


def ranking_queryset(user):
    access = Q(is_public=True)
    prefs = RankingPreference.objects.none()
    if user.is_authenticated:
        access |= Q(owner=user)
        prefs = RankingPreference.objects.filter(user=user)
        if user.is_staff:
            access |= Q(owner__isnull=True)
    return Ranking.objects.filter(access, is_archived=False).annotate(
        entry_count=Coalesce(Subquery(RankingEntry.objects.filter(ranking_id=OuterRef('pk'), is_archived=False).order_by().values('ranking_id').annotate(n=Count('pk')).values('n')), 0, output_field=IntegerField()),
        source_count=Coalesce(Subquery(ResearchSource.objects.filter(ranking_id=OuterRef('pk'), eligible=True, is_archived=False).order_by().values('ranking_id').annotate(n=Count('pk')).values('n')), 0, output_field=IntegerField())
    ).prefetch_related(Prefetch('preferences', queryset=prefs, to_attr='viewer_prefs')).order_by('title', 'id')


def edit_permission(ranking, user):
    from .ranking_policy import can_edit_ranking
    if not can_edit_ranking(ranking, user):
        raise PermissionDenied('This ranking is read-only. Make a personal copy to edit it.')


class RevisionConflict(APIException):
    status_code = 409
    default_detail = 'This ranking changed since you opened it. Reload it before saving.'


def check_revision(ranking, request):
    expected = request.data.get('expected_revision') if isinstance(request.data, dict) else None
    if expected is not None:
        if type(expected) is not int or expected < 1:
            raise ValidationError('Expected revision must be a positive integer.')
        if expected != ranking.revision:
            raise RevisionConflict()


def revision_snapshot(ranking):
    return {'title': ranking.title, 'description': ranking.description, 'criteria': ranking.criteria, 'scope': ranking.scope,
            'presentation': ranking.presentation, 'status': ranking.status, 'domain': ranking.domain,
            'item_type': ranking.item_type, 'source_url': ranking.source_url,
            'entries': list(ranking.entries.values('work_id', 'person_id', 'position', 'source_rank', 'rationale', 'assessments', 'groupings', 'is_archived'))}


def ensure_revision(ranking):
    RankingRevision.objects.get_or_create(ranking=ranking, number=ranking.revision,
        defaults={'note': 'Initial saved version', 'snapshot': revision_snapshot(ranking)})


def save_revision(ranking, note, initial=False):
    if not initial:
        ranking.revision += 1
    ranking.save()
    RankingRevision.objects.create(ranking=ranking, number=ranking.revision, note=note, snapshot=revision_snapshot(ranking))


def positive_id(value, field):
    if type(value) is bool:
        raise ValidationError({field: 'Use a positive integer ID.'})
    return serializers.IntegerField(min_value=1).run_validation(value)


class RankingViewSet(MutationGuardMixin, viewsets.ModelViewSet):
    serializer_class = RankingSerializer
    permission_classes = [permissions.AllowAny]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.method not in permissions.SAFE_METHODS and not isinstance(request.data, dict):
            raise ValidationError('Send a JSON object.')

    def get_queryset(self):
        queryset = ranking_queryset(self.request.user)
        group = self.request.query_params.get('group')
        if group == 'research':
            return queryset.filter(origin='curated')
        if group == 'published':
            return queryset.filter(origin='external', presentation='ranked')
        if group == 'collections':
            return queryset.filter(origin='external').exclude(presentation='ranked')
        return queryset

    def list(self, request, *args, **kwargs):
        if request.query_params.get('paged') == '1':
            from .ranking_queries import ranking_index
            return ranking_index(self.get_queryset(), request)
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        if request.query_params.get('compact') == '1':
            from .ranking_queries import compact_ranking
            return Response(compact_ranking(self.get_object(), request))
        return super().retrieve(request, *args, **kwargs)

    @action(detail=True, methods=['get'])
    def candidates(self, request, pk=None):
        ranking = self.get_object()
        edit_permission(ranking, request.user)
        field = 'work' if ranking.item_type == 'work' else 'person'
        queryset = (Work if field == 'work' else Person).objects.filter(is_archived=False).exclude(
            pk__in=ranking.entries.values(f'{field}_id'))
        search = request.query_params.get('search', '').strip()[:300]
        if field == 'work':
            if ranking.scope.get('forms'):
                queryset = queryset.filter(form__in=ranking.scope['forms'])
            if search:
                from .search import search_catalog
                queryset = search_catalog(queryset, search, kind='work', order=False)
            rows = queryset.order_by('title', 'pk').values('id', 'title')
        else:
            if search:
                from .search import search_catalog
                queryset = search_catalog(queryset, search, kind='person', order=False)
            rows = queryset.order_by('name', 'pk').values('id', title=F('name'))
        paginator = CatalogPagination()
        return paginator.get_paginated_response(list(paginator.paginate_queryset(rows, request)))

    @action(detail=False, methods=['get'])
    def explore(self, request):
        slugs = ['books-all-time', 'literature-all-time', 'philosophy-books-all-time', 'philosophers-all-time']
        rows = list(self.get_queryset().filter(slug__in=slugs))
        count = RankingPreference.objects.filter(user=request.user, bookmarked=True,
            ranking__in=self.get_queryset()).count() if request.user.is_authenticated else 0
        return Response({'rankings': RankingSerializer(rows, many=True,
            context={**self.get_serializer_context(), 'summary': True}).data, 'bookmarked_count': count})

    def perform_create(self, serializer):
        if not self.request.user.is_authenticated:
            raise PermissionDenied('Sign in to create a list.')
        title = serializer.validated_data['title']
        with transaction.atomic():
            ranking = serializer.save(owner=self.request.user, origin='personal', status='personal',
                                      slug=f'{slugify(title)[:100]}-{uuid.uuid4().hex[:10]}')
            save_revision(ranking, 'Created personal list', initial=True)

    def update(self, request, *args, **kwargs):
        existing = self.get_object()
        edit_permission(existing, request.user)
        with transaction.atomic():
            current = Ranking.objects.select_for_update().get(pk=existing.pk)
            check_revision(current, request)
            serializer = self.get_serializer(current, data=request.data, partial=kwargs.get('partial', False))
            serializer.is_valid(raise_exception=True)
            if current.entries.exists() and any(key in serializer.validated_data and serializer.validated_data[key] != getattr(current, key)
                                                for key in ['item_type', 'presentation']):
                raise ValidationError('Create a new list to change the type or presentation of a populated list.')
            ensure_revision(current)
            ranking = serializer.save()
            save_revision(ranking, 'Updated list definition')
        return Response(self.get_serializer(self.get_queryset().get(pk=ranking.pk)).data)

    def perform_destroy(self, instance):
        edit_permission(instance, self.request.user)
        if instance.origin != 'personal':
            raise ValidationError('Shared ranking templates are managed through administration.')
        instance.delete()

    @action(detail=True, methods=['get', 'post', 'delete'])
    def entries(self, request, pk=None):
        ranking = self.get_object()
        if request.method == 'POST':
            edit_permission(ranking, request.user)
            with transaction.atomic():
                ranking = Ranking.objects.select_for_update().get(pk=ranking.pk)
                check_revision(ranking, request)
                serializer = EntrySerializer(data=request.data, context={'request': request, 'ranking': ranking})
                serializer.is_valid(raise_exception=True)
                values = serializer.validated_data
                if ranking.entries.filter(work=values.get('work'), person=values.get('person')).exists():
                    raise ValidationError('This item is already on the list.')
                ensure_revision(ranking)
                serializer.save(ranking=ranking, position=ranking.entries.count() + 1)
                save_revision(ranking, 'Added entry')
        elif request.method == 'DELETE':
            if ranking.origin != 'personal':
                raise PermissionDenied('Shared entries cannot be deleted. Use the editorial archive workflow.')
            edit_permission(ranking, request.user)
            entry_id = positive_id(request.data.get('entry_id'), 'entry_id')
            with transaction.atomic():
                ranking = Ranking.objects.select_for_update().get(pk=ranking.pk)
                check_revision(ranking, request)
                entry = get_object_or_404(ranking.entries, pk=entry_id)
                ensure_revision(ranking)
                entry.delete()
                # Position is display order; publisher source_rank remains unchanged.
                for position, item in enumerate(ranking.entries.all(), 1):
                    RankingEntry.objects.filter(pk=item.pk).update(position=position)
                save_revision(ranking, 'Removed entry')
        if request.method != 'GET' and request.query_params.get('compact') == '1':
            return Response({'detail': 'Entry added.' if request.method == 'POST' else 'Entry removed.', 'revision': ranking.revision})
        if request.method == 'GET' and request.query_params.get('paged') == '1':
            from .ranking_queries import browse_page
            return browse_page(ranking, request)
        entries = ranking.entries.filter(is_archived=False).select_related('work__default_edition', 'person').prefetch_related('work__authors', 'work__tags')
        return Response(EntrySerializer(entries, many=True, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def reorder(self, request, pk=None):
        ranking = self.get_object()
        edit_permission(ranking, request.user)
        if ranking.origin == 'external':
            raise ValidationError('Make a personal copy to change publisher order.')
        ids = request.data.get('entry_ids')
        move = None
        if 'entry_id' in request.data:
            from .ranking_contracts import RankingMoveSerializer
            command = RankingMoveSerializer(data=request.data)
            command.is_valid(raise_exception=True)
            move = command.validated_data
        with transaction.atomic():
            ranking = Ranking.objects.select_for_update().get(pk=ranking.pk)
            check_revision(ranking, request)
            current = list(ranking.entries.order_by('position', 'pk').values_list('id', flat=True))
            if move:
                active = list(ranking.entries.filter(is_archived=False).order_by('position', 'pk').values_list('id', flat=True))
                if move['entry_id'] not in active:
                    raise ValidationError('Choose an active entry from this list.')
                index = active.index(move['entry_id'])
                neighbor = index + int(move['direction'])
                if not 0 <= neighbor < len(active):
                    return Response({'detail': 'The entry is already at the edge of the list.', 'revision': ranking.revision})
                left, right = current.index(active[index]), current.index(active[neighbor])
                ids = list(current)
                ids[left], ids[right] = ids[right], ids[left]
            if not isinstance(ids, list) or len(ids) != len(current) or any(type(i) is not int for i in ids) or set(ids) != set(current):
                raise ValidationError('Submit every entry once, in its new order.')
            ensure_revision(ranking)
            for position, entry_id in enumerate(ids, 1):
                RankingEntry.objects.filter(pk=entry_id, ranking=ranking).update(position=position)
            save_revision(ranking, 'Changed manual order')
        return Response({'detail': 'Order saved.', 'revision': ranking.revision})

    @action(detail=True, methods=['post'])
    def copy(self, request, pk=None):
        if not request.user.is_authenticated:
            raise PermissionDenied('Sign in to make a personal copy.')
        original = self.get_object()
        with transaction.atomic():
            original = Ranking.objects.select_for_update().get(pk=original.pk)
            entries = list(original.entries.filter(is_archived=False))
            lens = request.data.get('editorial_lens')
            editorial = original.scope.get('editorial', {}) if original.origin == 'curated' else {}
            positions = {}
            if lens is not None:
                if not isinstance(lens, str) or lens not in {'standing', 'reading'} or lens not in editorial.get('orders', {}):
                    raise ValidationError('Choose an available editorial perspective.')
                item_ids = editorial['orders'][lens]['item_ids']
                if len(item_ids) != len(entries) or set(item_ids) != {e.work_id or e.person_id for e in entries}:
                    raise ValidationError('This perspective needs editorial review before copying.')
                positions = {item_id: index for index, item_id in enumerate(item_ids, 1)}
            from .ranking_policy import copy_scope
            copied = Ranking.objects.create(title=f'My {original.title}'[:240], slug=f'personal-{uuid.uuid4().hex}',
                description=original.description, domain=original.domain, item_type=original.item_type,
                presentation=original.presentation, origin='personal', owner=request.user, status='personal',
                scope={**copy_scope(original),
                       **({'copied_editorial_lens': lens} if lens else {})}, criteria=original.criteria)
            for entry in entries:
                item_id = entry.work_id or entry.person_id
                rationale = editorial.get('entries', {}).get(str(item_id), {}).get(lens, entry.rationale) if lens else entry.rationale
                RankingEntry.objects.create(ranking=copied, work=entry.work, person=entry.person,
                                            position=positions.get(item_id, entry.position),
                                            source_rank=entry.source_rank, rationale=rationale, assessments=entry.assessments,
                                            groupings=entry.groupings)
            save_revision(copied, f'Copied source revision {original.revision}', initial=True)
        return Response(self.get_serializer(self.get_queryset().get(pk=copied.pk)).data, status=201)

    @action(detail=True, methods=['get', 'patch'])
    def preference(self, request, pk=None):
        if not request.user.is_authenticated:
            raise PermissionDenied('Sign in to save preferences.')
        ranking = self.get_object()
        with transaction.atomic():
            ranking = Ranking.objects.select_for_update().get(pk=ranking.pk)
            pref = RankingPreference.objects.filter(user=request.user, ranking=ranking).first()
            if request.method == 'PATCH':
                serializer = PreferenceSerializer(pref, data=request.data, partial=True, context={'ranking': ranking})
                serializer.is_valid(raise_exception=True)
                pref = serializer.save(user=request.user, ranking=ranking)
            elif pref is None:
                pref = RankingPreference(user=request.user, ranking=ranking)
        return Response(PreferenceSerializer(pref).data)

    @action(detail=True, methods=['post'])
    def refresh(self, request, pk=None):
        if not request.user.is_authenticated:
            raise PermissionDenied('Sign in to request a refresh.')
        ranking = self.get_object()
        pref, _ = RankingPreference.objects.get_or_create(user=request.user, ranking=ranking)
        if pref.refresh_requested_at is None or (ranking.last_researched_at and pref.refresh_requested_at <= ranking.last_researched_at):
            pref.refresh_requested_at = timezone.now()
            pref.save()
        return Response({'detail': 'Refresh request saved for later research. No automated research job has started.',
                         'requested_at': pref.refresh_requested_at})

    @action(detail=True, methods=['get'])
    def sources(self, request, pk=None):
        sources = self.get_object().sources.filter(is_archived=False).order_by('source_id')
        if request.query_params.get('paged') == '1':
            paginator = CatalogPagination()
            page = paginator.paginate_queryset(sources, request)
            return paginator.get_paginated_response(SourceSerializer(page, many=True).data)
        page = self.paginate_queryset(sources)
        return self.get_paginated_response(SourceSerializer(page, many=True).data)

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        return Response(list(self.get_object().revisions.order_by('-number').values('number', 'created_at', 'note')[:50]))

    @action(detail=True, methods=['post'])
    def preview(self, request, pk=None):
        if not request.user.is_authenticated:
            raise PermissionDenied('Sign in to calculate a personal ranking.')
        ranking = self.get_object()
        serializer = PreferenceSerializer(data=request.data, context={'ranking': ranking})
        serializer.is_valid(raise_exception=True)
        pref = RankingPreference.objects.filter(user=request.user, ranking=ranking).first()
        weights = serializer.validated_data.get('weights', pref.weights if pref else {})
        overrides = serializer.validated_data.get('overrides', pref.overrides if pref else {})
        rows = [{'entry_id': entry['pk'], **weighted_score(entry['assessments'], weights, overrides.get(str(entry['pk'])))}
                for entry in ranking.entries.filter(is_archived=False).values('pk', 'assessments')]
        rows.sort(key=lambda row: (row['score'] is None, -(row['score'] or 0), row['entry_id']))
        if request.query_params.get('paged') == '1':
            from .ranking_queries import browse_page
            return browse_page(ranking, request, scores=rows)
        return Response(rows)

    @action(detail=True, methods=['post'])
    def sharing(self, request, pk=None):
        ranking = self.get_object()
        if not request.user.is_authenticated or ranking.owner_id != request.user.pk:
            raise PermissionDenied('Only the owner can share a personal list.')
        enabled = request.data.get('enabled')
        if type(enabled) is not bool:
            raise ValidationError('Enabled must be true or false.')
        ranking.sharing_enabled = enabled
        if not enabled:
            ranking.share_token = uuid.uuid4()
        ranking.save(update_fields=['sharing_enabled', 'share_token', 'updated_at'])
        return Response({'share_url': f'/shared/{ranking.share_token}' if enabled else None})

    @action(detail=False, methods=['get'])
    def recommendations(self, request):
        if not request.user.is_authenticated:
            raise PermissionDenied('Sign in to see recommendations.')
        try:
            limit = int(request.query_params.get('limit', 12))
        except (ValueError, TypeError) as error:
            raise ValidationError('Limit must be between 1 and 50.') from error
        if not 1 <= limit <= 50:
            raise ValidationError('Limit must be between 1 and 50.')
        excluded = LibraryItem.objects.filter(user=request.user, status__in=['reading', 'finished']).values('work_id')
        preferences = {pref.ranking_id: pref for pref in RankingPreference.objects.filter(user=request.user)
                       if any(value > 0 for value in pref.weights.values())}
        candidates = {}
        for ranking in self.get_queryset().filter(status='published', item_type='work', pk__in=preferences).values('pk', 'title'):
            pref = preferences[ranking['pk']]
            entries = RankingEntry.objects.filter(ranking_id=ranking['pk'], is_archived=False, work__is_archived=False,
                work__editions__is_archived=False, work__editions__language__iexact='English').exclude(work_id__in=excluded).distinct()
            entries = entries.values('pk', 'work_id', 'work__title', 'assessments')
            for entry in entries:
                score = weighted_score(entry['assessments'], pref.weights, pref.overrides.get(str(entry['pk'])))
                if score['score'] is None:
                    continue
                candidate = {'entry_id': entry['pk'], 'ranking_id': ranking['pk'], 'ranking_title': ranking['title'],
                             'work_id': entry['work_id'], 'title': entry['work__title'], **score}
                existing = candidates.get(entry['work_id'])
                if existing is None or candidate['score'] > existing['score']:
                    candidates[entry['work_id']] = candidate
        rows = sorted(candidates.values(), key=lambda row: (-row['score'], row['title'], row['work_id']))[:limit]
        winning_works = Work.objects.filter(pk__in=[row['work_id'] for row in rows]).select_related('default_edition').prefetch_related('authors', 'tags')
        from .serializers import WorkCardSerializer
        serializer_class = WorkCardSerializer if request.query_params.get('compact') == '1' else WorkSerializer
        serialized = {work['id']: work for work in serializer_class(winning_works, many=True, context={'request': request}).data}
        for row in rows:
            row['book'] = serialized[row.pop('work_id')]
            row.pop('title')
        return Response({'results': rows, 'detail': 'Suggestions use your saved weights and overrides on published rankings with English editions. '
                         'Each score uses the named ranking’s own criteria; scores from different criteria are not universal quality ratings.'})


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def shared_list(request, token):
    ranking = get_object_or_404(Ranking, share_token=token, sharing_enabled=True, origin='personal', is_archived=False)
    if request.query_params.get('compact') == '1':
        from .ranking_queries import compact_ranking
        data = compact_ranking(ranking, request, public=True)
        data['entry_count'] = ranking.entries.filter(is_archived=False).count()
        response = Response(data)
        response['Cache-Control'] = 'private, no-store'
        return response
    if request.query_params.get('paged') == '1':
        from .ranking_queries import browse_page, compact_ranking
        page = browse_page(ranking, request, public=True)
        data = compact_ranking(ranking, request, public=True)
        data['entry_count'] = ranking.entries.filter(is_archived=False).count()
        response = Response({'ranking': data, 'page': page.data})
        response['Cache-Control'] = 'private, no-store'
        return response
    # List sharing exposes the selected contents, never a reader's private assessments or notes.
    data = {key: value for key, value in RankingSerializer(ranking, context={'request': request}).data.items()
            if key not in {'owner', 'criteria', 'scope', 'preference', 'share_url'}}
    from .ranking_policy import display_scope
    rows = list(ranking.entries.filter(is_archived=False).select_related('work__default_edition', 'person').prefetch_related('work__authors', 'work__tags'))
    data.update({'preference': None, 'can_edit': False, 'criteria': [], 'scope': display_scope(ranking, rows)})
    entries = EntrySerializer(rows,
                              many=True, context={'request': request}).data
    data['entries'] = [{key: value for key, value in entry.items() if key not in {'rationale', 'assessments'}} for entry in entries]
    data['entry_count'] = len(entries)
    return Response(data)


def snapshot_attempt(item):
    from .reading_basis import capture_edition
    basis = item.reading_basis or capture_edition(item.edition or item.work.default_edition)
    ReadingAttempt.objects.create(user=item.user, work=item.work, edition_id=basis.get('edition_id'), reading_basis=basis,
        **{key: getattr(item, key) for key in ['status', 'current_page', 'rating', 'notes', 'started_on', 'finished_on']})


class LibraryViewSet(MutationGuardMixin, VersionedEditMixin, viewsets.ModelViewSet):
    serializer_class = LibrarySerializer

    @action(detail=True, methods=['post'], url_path='edition-change')
    def edition_change(self, request, pk=None):
        from .edition_changes import EditionChangeCommand, transition
        command = EditionChangeCommand(data=request.data)
        command.is_valid(raise_exception=True)
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            item = self.get_object()
            return Response(transition(item, command.validated_data, request))

    def get_queryset(self):
        from .library_queries import filter_library, library_queryset
        qs = library_queryset(self.request.user, compact=self.action == 'list' and self.request.query_params.get('compact') == '1')
        if self.action != 'list':
            return qs
        return filter_library(qs, self.request.user, self.request.query_params)

    def list(self, request, *args, **kwargs):
        if request.query_params.get('compact') != '1':
            return super().list(request, *args, **kwargs)
        from .serializers import LibrarySummarySerializer
        paginator = CatalogPagination()
        page = paginator.paginate_queryset(self.get_queryset(), request)
        return paginator.get_paginated_response(LibrarySummarySerializer(page, many=True, context={'request': request}).data)

    @action(detail=False, methods=['get'])
    def facets(self, request):
        from .library_queries import library_facets
        return Response(library_facets(request.user, request.query_params))

    @action(detail=False, methods=['get'])
    def selector(self, request):
        from .library_queries import filter_library
        rows = filter_library(LibraryItem.objects.filter(user=request.user), request.user, request.query_params).values(
            'id', 'work_id', 'work__title', 'status', 'current_page', 'reading_basis', 'edition_id',
            'edition__pages', 'work__default_edition__pages')
        return Response([{'id': row['id'], 'work': row['work_id'], 'title': row['work__title'], 'status': row['status'],
                          'current_page': row['current_page'], 'pages': row['reading_basis'].get('pages') if row['reading_basis']
                          else row['edition__pages'] if row['edition_id'] else row['work__default_edition__pages']} for row in rows])

    @action(detail=False, methods=['get'], url_path='read-next')
    def read_next(self, request):
        from .library_queries import filter_library, library_queryset
        from .serializers import LibrarySummarySerializer
        queue = LibraryItem.objects.filter(user=request.user, read_next_position__isnull=False).order_by('read_next_position', 'pk')
        rows = filter_library(library_queryset(request.user, compact=True).filter(read_next_position__isnull=False),
                              request.user, request.query_params).order_by('read_next_position', 'pk')
        paginator = CatalogPagination()
        page = paginator.paginate_queryset(rows, request)
        response = paginator.get_paginated_response(LibrarySummarySerializer(page, many=True, context={'request': request}).data)
        response.data['first_id'] = queue.values_list('pk', flat=True).first()
        response.data['last_id'] = queue.values_list('pk', flat=True).last()
        return response

    @action(detail=False, methods=['get'])
    def overview(self, request):
        from .library_queries import library_queryset
        from .serializers import LibrarySummarySerializer
        rows = library_queryset(request.user, compact=True)
        reading = rows.filter(status='reading')
        return Response({'count': rows.count(), 'reading_count': reading.count(),
            'currently_reading': LibrarySummarySerializer(reading[:3], many=True, context={'request': request}).data})

    @action(detail=False, methods=['get'])
    def history(self, request):
        rows = ReadingAttempt.objects.filter(user=request.user)
        if work := request.query_params.get('work'):
            rows = rows.filter(work_id=positive_id(work, 'work'))
        if request.query_params.get('paged') == '1':
            paginator = CatalogPagination()
            from django.db.models import BooleanField, Case, Value, When
            rows = rows.annotate(has_notes=Case(When(notes='', then=Value(False)), default=Value(True), output_field=BooleanField()))
            page = paginator.paginate_queryset(rows.values('id', 'work_id', 'work__title', 'status', 'current_page',
                'rating', 'started_on', 'finished_on', 'has_notes'), request)
            return paginator.get_paginated_response(page)
        return Response(list(rows.values('id', 'work_id', 'work__title', 'edition_id', 'status', 'current_page', 'rating', 'notes', 'started_on', 'finished_on', 'created_at', 'reading_basis')))

    @action(detail=False, methods=['get'], url_path=r'history/(?P<attempt_id>[0-9]+)')
    def history_detail(self, request, attempt_id=None):
        row = get_object_or_404(ReadingAttempt.objects.filter(user=request.user).values(
            'id', 'work_id', 'work__title', 'edition_id', 'status', 'current_page', 'rating', 'notes',
            'started_on', 'finished_on', 'created_at', 'reading_basis'), pk=attempt_id)
        return Response(row)

    @action(detail=True, methods=['post'])
    def reread(self, request, pk=None):
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            item = self.get_object()
            if item.status not in ['finished', 'abandoned']:
                raise ValidationError('Finish or abandon the current attempt before starting another.')
            snapshot_attempt(item)
            from .reading_basis import capture_edition
            item.reading_basis = capture_edition(item.edition or item.work.default_edition)
            item.status, item.current_page, item.rating, item.notes = 'reading', 0, None, ''
            item.started_on, item.finished_on = timezone.localdate(), None
            item.save()
        return Response(self.get_serializer(item).data)

    def perform_destroy(self, instance):
        with transaction.atomic():
            snapshot_attempt(instance)
            instance.delete()

    def destroy(self, request, *args, **kwargs):
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            return super().destroy(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        if not isinstance(request.data, dict):
            raise ValidationError('Send a JSON object.')
        work_id = positive_id(request.data.get('work'), 'work')
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            existing = self.get_queryset().filter(work_id=work_id).first()
            if existing:
                require_current(request, existing, self.get_serializer_class())
            serializer = self.get_serializer(existing, data=request.data, partial=existing is not None)
            serializer.is_valid(raise_exception=True)
            serializer.save(user=request.user)
        return Response(serializer.data, status=200 if existing else 201)

    def update(self, request, *args, **kwargs):
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            return super().update(request, *args, **kwargs)


class PlanViewSet(MutationGuardMixin, VersionedEditMixin, viewsets.ModelViewSet):
    serializer_class = PlanSerializer

    def get_serializer_class(self):
        if self.action == 'list' and self.request.query_params.get('compact') == '1':
            from .serializers import PlanSummarySerializer
            return PlanSummarySerializer
        return super().get_serializer_class()

    def get_queryset(self):
        from django.db.models import Exists, OuterRef
        from .models import PlanCarryover
        queryset = PlanItem.objects.filter(user=self.request.user).annotate(
            _has_incoming_carryover=Exists(PlanCarryover.objects.filter(target_plan_id=OuterRef('pk'))),
        ).select_related('work__default_edition').prefetch_related('work__authors', 'work__tags')
        if self.action == 'list' and self.request.query_params.get('start_month'):
            try:
                start = date.fromisoformat(self.request.query_params['start_month'])
                months = month_range(start, int(self.request.query_params.get('months', '3')))
            except (TypeError, ValueError) as error:
                raise ValidationError(str(error)) from error
            queryset = queryset.filter(month__in=months)
        return queryset

    def create(self, request, *args, **kwargs):
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def update(self, request, *args, **kwargs):
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            return super().destroy(request, *args, **kwargs)

    def perform_destroy(self, instance):
        from .reading_workflow import allocation_has_history
        if instance.locked:
            raise ValidationError('Unlock this item before removing it.')
        if allocation_has_history(instance):
            raise ValidationError('This allocation preserves recorded reading or carryover history. Clear an erroneous reading total first, or carry unfinished pages forward.')
        instance.delete()

    @action(detail=False, methods=['get'])
    def capacity(self, request):
        try:
            start = date.fromisoformat(request.query_params.get('start_month', ''))
            months = month_range(start, int(request.query_params.get('months', '3')))
        except (ValueError, TypeError) as error:
            raise ValidationError(str(error)) from error
        items = list(self.get_queryset().filter(month__in=months))
        from .reading_workflow import capacity_summary
        return Response([capacity_summary(request.user, month, [item for item in items if item.month == month])
                         for month in months])

    @action(detail=False, methods=['post'])
    def suggest(self, request):
        try:
            if not isinstance(request.data, dict):
                raise ValueError('Send a JSON object.')
            start = date.fromisoformat(request.data.get('start_month', ''))
            count = request.data.get('months', 3)
            if type(count) is not int:
                raise ValueError('Month count must be a whole number.')
            for key in ['apply', 'confirm_replace']:
                if key in request.data and type(request.data[key]) is not bool:
                    raise ValueError(f'{key} must be true or false.')
            if start.day != 1:
                raise ValueError('Use the first day of the start month.')
            months = month_range(start, count)
            work_ids = request.data.get('work_ids', [])
            if not isinstance(work_ids, list) or any(type(i) is not int or i < 1 for i in work_ids) or len(set(work_ids)) != len(work_ids):
                raise ValueError('Choose each library work once.')
            with transaction.atomic():
                request.user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
                from .reading_basis import plan_effort, capture_edition, length_edition, comparable
                from .plan_previews import preview_token, require_preview
                from .reading_workflow import allocation_has_history, allocation_remaining
                library = {item.work_id: item for item in LibraryItem.objects.filter(user=request.user, work_id__in=work_ids).select_related('work__default_edition', 'edition')}
                if len(library) != len(work_ids):
                    raise ValueError('Choose books saved in your library.')
                bases = {}
                books = []
                for pk in work_ids:
                    item = library[pk]
                    edition = length_edition(item)
                    basis = dict(item.reading_basis) if item.reading_basis else capture_edition(edition)
                    basis.update(effort_multiplier=effort_per_page(item.work, edition), allocated_at=timezone.now().isoformat())
                    bases[pk] = basis
                    pages = max(0, edition.pages - item.current_page) if edition and edition.pages is not None else None
                    books.append({'id': pk, 'remaining_pages': 0 if item.status == 'finished' else pages,
                                  'effort_per_page': basis['effort_multiplier'] if request.user.difficulty_aware_planning else 1})
                allocations = list(self.get_queryset().filter(month__in=months))
                preserved = [row for row in allocations if row.locked or allocation_has_history(row)]
                blocked = {(row.work_id, row.month) for row in preserved}
                locked = []
                for row in preserved:
                    committed = row.pages - row.carried_pages if row.pages is not None else None
                    if committed == 0:
                        continue
                    locked.append({'work': row.work_id, 'month': row.month, 'pages': committed,
                                   'remaining_pages': allocation_remaining(row),
                                   'effort_per_page': plan_effort(row, request.user)})
                budgets = {m: reading_budget(request.user, m)['budget'] for m in months}
                result = suggest_plan(books, months, request.user.pages_per_day, locked,
                                      month_budgets=budgets, blocked_pairs=blocked)
                result['budget_unit'] = 'baseline_pages' if request.user.difficulty_aware_planning else 'pages'
                result['algorithm_version'] = CAPACITY_VERSION
                state = {'months': months, 'work_ids': work_ids, 'proposal': result,
                         'library': [{'id': library[pk].pk, 'updated_at': library[pk].updated_at,
                                      'reading_basis': library[pk].reading_basis} for pk in work_ids],
                         'bases': {pk: {**comparable(bases[pk]), 'effort_multiplier': bases[pk]['effort_multiplier']}
                                   for pk in work_ids},
                         'allocations': [{key: getattr(row, key) for key in (
                             'id', 'work_id', 'month', 'position', 'pages', 'locked', 'reading_basis',
                             'pages_read', 'carried_pages', '_has_incoming_carryover', 'updated_at')}
                             for row in allocations]}
                if request.data.get('apply') is True:
                    if request.data.get('confirm_replace') is not True:
                        raise ValueError('Confirm replacement of allocations without locks or reading history in the selected months.')
                    require_preview(request.data.get('preview_token'), request.user, 'suggest', state)
                    self.get_queryset().filter(month__in=months).exclude(pk__in=[row.pk for row in preserved]).delete()
                    positions = {month: max((row.position for row in preserved if row.month == month), default=0)
                                 for month in months}
                    additions = []
                    for item in result['items']:
                        month = date.fromisoformat(item['month'])
                        positions[month] += 1
                        additions.append(PlanItem(user=request.user, work_id=item['work'], month=month,
                                                  pages=item['pages'], position=positions[month], reading_basis=bases[item['work']]))
                    PlanItem.objects.bulk_create(additions)
                else:
                    result['preview_token'] = preview_token(request.user, 'suggest', state)
        except (ValueError, TypeError) as error:
            raise ValidationError(str(error)) from error
        return Response(result)


@api_view(['GET'])
def export_library(request):
    from .private_export import export_response
    return export_response(request)


def app_index(request, path=''):
    index = settings.BASE_DIR / 'backend/static/app/index.html'
    if not index.exists():
        return JsonResponse({'detail': 'Frontend build missing. Run the setup instructions in README.md.'}, status=503)
    response = FileResponse(index.open('rb'), content_type='text/html')
    response['Cache-Control'] = 'no-cache'
    return response


@require_http_methods(['GET'])
def health_live(request):
    return JsonResponse({'status': 'ok'})


@require_http_methods(['GET'])
def health_ready(request):
    from django.db import connection
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        ready = (settings.BASE_DIR / 'backend/static/app/index.html').is_file()
    except Exception:
        ready = False
    return JsonResponse({'status': 'ok' if ready else 'unavailable'}, status=200 if ready else 503)
