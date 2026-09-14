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
from backend.domain.reading_capacity import effort_per_page, reading_budget
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
def profile(request):
    if request.method == 'PATCH':
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


class WorkViewSet(viewsets.ModelViewSet):
    pagination_class = CatalogPagination
    serializer_class = WorkSerializer
    permission_classes = [CatalogPermission]
    queryset = Work.objects.filter(is_archived=False).select_related('default_edition').prefetch_related('authors', 'tags')

    def get_queryset(self):
        qs = super().get_queryset()
        if term := self.request.query_params.get('search'):
            qs = qs.filter(Q(title__icontains=term) | Q(authors__name__icontains=term) | Q(tags__name__icontains=term)).distinct()
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


class PersonViewSet(viewsets.ModelViewSet):
    pagination_class = CatalogPagination
    serializer_class = PersonSerializer
    permission_classes = [CatalogPermission]
    queryset = Person.objects.filter(is_archived=False)

    def get_queryset(self):
        qs = super().get_queryset()
        if search := self.request.query_params.get('search'):
            qs = qs.filter(name__icontains=search)
        return qs


class EditionViewSet(viewsets.ModelViewSet):
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
    if not user.is_authenticated or not (ranking.owner_id == user.pk or (user.is_staff and ranking.owner_id is None)):
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


class RankingViewSet(viewsets.ModelViewSet):
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
        entries = ranking.entries.filter(is_archived=False).select_related('work__default_edition', 'person').prefetch_related('work__authors', 'work__tags')
        return Response(EntrySerializer(entries, many=True, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def reorder(self, request, pk=None):
        ranking = self.get_object()
        edit_permission(ranking, request.user)
        if ranking.origin == 'external':
            raise ValidationError('Make a personal copy to change publisher order.')
        ids = request.data.get('entry_ids')
        with transaction.atomic():
            ranking = Ranking.objects.select_for_update().get(pk=ranking.pk)
            check_revision(ranking, request)
            current = list(ranking.entries.values_list('id', flat=True))
            if not isinstance(ids, list) or len(ids) != len(current) or any(type(i) is not int for i in ids) or set(ids) != set(current):
                raise ValidationError('Submit every entry once, in its new order.')
            ensure_revision(ranking)
            for position, entry_id in enumerate(ids, 1):
                RankingEntry.objects.filter(pk=entry_id, ranking=ranking).update(position=position)
            save_revision(ranking, 'Changed manual order')
        return Response({'detail': 'Order saved.'})

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
            copied = Ranking.objects.create(title=f'My {original.title}'[:240], slug=f'personal-{uuid.uuid4().hex}',
                description=original.description, domain=original.domain, item_type=original.item_type,
                presentation=original.presentation, origin='personal', owner=request.user, status='personal',
                scope={**original.scope, 'copied_from': original.pk, 'copied_revision': original.revision,
                       **({'copied_editorial_lens': lens} if lens else {})}, criteria=original.criteria)
            for entry in entries:
                item_id = entry.work_id or entry.person_id
                rationale = editorial.get('entries', {}).get(str(item_id), {}).get(lens, entry.rationale) if lens else entry.rationale
                RankingEntry.objects.create(ranking=copied, work=entry.work, person=entry.person,
                                            position=positions.get(item_id, entry.position),
                                            source_rank=entry.source_rank, rationale=rationale, assessments=entry.assessments)
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
        rows = [{'entry_id': entry.pk, **weighted_score(entry.assessments, weights, overrides.get(str(entry.pk)))} for entry in ranking.entries.filter(is_archived=False)]
        rows.sort(key=lambda row: (row['score'] is None, -(row['score'] or 0), row['entry_id']))
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
        candidates = {}
        for ranking in self.get_queryset().filter(status='published', item_type='work'):
            pref = ranking.viewer_prefs[0] if ranking.viewer_prefs else None
            if not pref or not any(v > 0 for v in pref.weights.values()):
                continue
            entries = ranking.entries.filter(is_archived=False, work__is_archived=False, work__editions__is_archived=False, work__editions__language__iexact='English').exclude(work_id__in=excluded).distinct()
            entries = entries.select_related('work__default_edition').prefetch_related('work__authors', 'work__tags')
            for entry in entries:
                score = weighted_score(entry.assessments, pref.weights, pref.overrides.get(str(entry.pk)))
                if score['score'] is None:
                    continue
                candidate = {'entry_id': entry.pk, 'ranking_id': ranking.pk, 'ranking_title': ranking.title,
                             'book': WorkSerializer(entry.work, context={'request': request}).data, **score}
                existing = candidates.get(entry.work_id)
                if existing is None or candidate['score'] > existing['score']:
                    candidates[entry.work_id] = candidate
        rows = sorted(candidates.values(), key=lambda row: (-row['score'], row['book']['title'], row['book']['id']))[:limit]
        return Response({'results': rows, 'detail': 'Suggestions use your saved weights and overrides on published rankings with English editions. '
                         'Each score uses the named ranking’s own criteria; scores from different criteria are not universal quality ratings.'})


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def shared_list(request, token):
    ranking = get_object_or_404(Ranking, share_token=token, sharing_enabled=True, origin='personal')
    # List sharing exposes the selected contents, never a reader's private assessments or notes.
    data = {key: value for key, value in RankingSerializer(ranking, context={'request': request}).data.items()
            if key not in {'owner', 'criteria', 'scope', 'preference', 'share_url'}}
    data.update({'preference': None, 'can_edit': False, 'criteria': [], 'scope': {}})
    entries = EntrySerializer(ranking.entries.filter(is_archived=False).select_related('work__default_edition', 'person').prefetch_related('work__authors', 'work__tags'),
                              many=True, context={'request': request}).data
    data['entries'] = [{key: value for key, value in entry.items() if key not in {'rationale', 'assessments'}} for entry in entries]
    data['entry_count'] = len(entries)
    return Response(data)


def snapshot_attempt(item):
    ReadingAttempt.objects.create(user=item.user, work=item.work, edition=item.edition or item.work.default_edition,
        **{key: getattr(item, key) for key in ['status', 'current_page', 'rating', 'notes', 'started_on', 'finished_on']})


class LibraryViewSet(viewsets.ModelViewSet):
    serializer_class = LibrarySerializer

    def get_queryset(self):
        qs = LibraryItem.objects.filter(user=self.request.user).select_related('edition', 'work__default_edition').prefetch_related('work__authors', 'work__tags')
        if self.action != 'list':
            return qs
        for key in ['work', 'status']:
            if value := self.request.query_params.get(key):
                qs = qs.filter(**{key: positive_id(value, key) if key == 'work' else value})
        if genre := self.request.query_params.get('genre'):
            qs = qs.filter(work__tags__kind='genre', work__tags__is_archived=False, work__tags__name=genre).distinct()
        if value := self.request.query_params.get('rating'):
            if value == 'unrated':
                qs = qs.filter(rating__isnull=True)
            else:
                qs = qs.filter(rating=serializers.IntegerField(min_value=1, max_value=10).run_validation(value))
        order = self.request.query_params.get('ordering')
        if order in ['rating', '-rating']:
            return qs.order_by(F('rating').desc(nulls_last=True) if order == '-rating' else F('rating').asc(nulls_last=True), 'work__title', 'id')
        if order == 'title':
            return qs.order_by('work__title', 'id')
        return qs

    @action(detail=False, methods=['get'])
    def history(self, request):
        rows = ReadingAttempt.objects.filter(user=request.user)
        if work := request.query_params.get('work'):
            rows = rows.filter(work_id=positive_id(work, 'work'))
        return Response(list(rows.values('id', 'work_id', 'work__title', 'edition_id', 'status', 'current_page', 'rating', 'notes', 'started_on', 'finished_on', 'created_at')))

    @action(detail=True, methods=['post'])
    def reread(self, request, pk=None):
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            item = self.get_object()
            if item.status not in ['finished', 'abandoned']:
                raise ValidationError('Finish or abandon the current attempt before starting another.')
            snapshot_attempt(item)
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
            serializer = self.get_serializer(existing, data=request.data, partial=existing is not None)
            serializer.is_valid(raise_exception=True)
            serializer.save(user=request.user)
        return Response(serializer.data, status=200 if existing else 201)

    def update(self, request, *args, **kwargs):
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            return super().update(request, *args, **kwargs)


class PlanViewSet(viewsets.ModelViewSet):
    serializer_class = PlanSerializer

    def get_queryset(self):
        return PlanItem.objects.filter(user=self.request.user).select_related('work__default_edition').prefetch_related('work__authors', 'work__tags')

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
        if instance.locked:
            raise ValidationError('Unlock this item before removing it.')
        instance.delete()

    @action(detail=False, methods=['get'])
    def capacity(self, request):
        try:
            start = date.fromisoformat(request.query_params.get('start_month', ''))
            months = month_range(start, int(request.query_params.get('months', '3')))
        except (ValueError, TypeError) as error:
            raise ValidationError(str(error)) from error
        items = list(self.get_queryset().filter(month__in=months))
        serialized = PlanSerializer(items, many=True, context={'request': request}).data
        result = []
        for month in months:
            budget = reading_budget(request.user, month)
            allocations = [row for row in serialized if row['month'] == month.isoformat()]
            budget.update({'used': round(sum(row['effort_pages'] or 0 for row in allocations), 2),
                           'physical_pages': sum(row['pages'] or 0 for row in allocations),
                           'unknown_allocations': sum(row['pages'] is None for row in allocations)})
            result.append(budget)
        return Response(result)

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
            library = {item.work_id: item for item in LibraryItem.objects.filter(user=request.user, work_id__in=work_ids).select_related('work__default_edition', 'edition')}
            if len(library) != len(work_ids):
                raise ValueError('Choose books saved in your library.')
            books = []
            for pk in work_ids:
                item = library[pk]
                edition = item.edition or item.work.default_edition
                pages = max(0, edition.pages - item.current_page) if edition and edition.pages is not None else None
                books.append({'id': pk, 'remaining_pages': 0 if item.status == 'finished' else pages,
                              'effort_per_page': effort_per_page(item.work, edition, request.user.difficulty_aware_planning)})
            with transaction.atomic():
                get_user_model().objects.select_for_update().get(pk=request.user.pk)
                locked = list(self.get_queryset().filter(locked=True, month__in=months).values('work', 'month', 'pages'))
                for allocation in locked:
                    work = Work.objects.select_related('default_edition').get(pk=allocation['work'])
                    saved = LibraryItem.objects.filter(user=request.user, work=work).select_related('edition').first()
                    edition = saved.edition if saved and saved.edition else work.default_edition
                    allocation['effort_per_page'] = effort_per_page(work, edition, request.user.difficulty_aware_planning)
                budgets = {m: reading_budget(request.user, m)['budget'] for m in months}
                result = suggest_plan(books, months, request.user.pages_per_day, locked, month_budgets=budgets)
                result['budget_unit'] = 'baseline_pages' if request.user.difficulty_aware_planning else 'pages'
                result['algorithm_version'] = 'reading-capacity-v1-provisional'
                if request.data.get('apply') is True:
                    if request.data.get('confirm_replace') is not True:
                        raise ValueError('Confirm replacement of unlocked allocations in the selected months.')
                    self.get_queryset().filter(month__in=months, locked=False).delete()
                    PlanItem.objects.bulk_create([PlanItem(user=request.user, work_id=item['work'], month=item['month'], pages=item['pages'], position=i + 1) for i, item in enumerate(result['items'])])
        except (ValueError, TypeError) as error:
            raise ValidationError(str(error)) from error
        return Response(result)


@api_view(['GET'])
def export_library(request):
    data = {'exported_at': timezone.now().isoformat(), 'profile': UserSerializer(request.user).data,
            'library': list(LibraryItem.objects.filter(user=request.user).values('work_id', 'edition_id', 'status', 'current_page', 'rating', 'notes', 'started_on', 'finished_on', 'shelves', 'personal_tags', 'read_next_position')),
            'reading_goals': list(ReadingGoal.objects.filter(user=request.user).values('year', 'books', 'pages')),
            'reading_history': list(ReadingAttempt.objects.filter(user=request.user).values('work_id', 'edition_id', 'status', 'current_page', 'rating', 'notes', 'started_on', 'finished_on', 'created_at')),
            'plan': list(PlanItem.objects.filter(user=request.user).values('work_id', 'month', 'position', 'pages', 'locked')),
            'preferences': list(RankingPreference.objects.filter(user=request.user).values('ranking_id', 'bookmarked', 'weights', 'overrides', 'refresh_interval_days')),
            'lists': [{'title': r.title, 'scope': r.scope, 'criteria': r.criteria,
                       'entries': list(r.entries.values('work_id', 'person_id', 'position', 'rationale', 'assessments'))} for r in Ranking.objects.filter(owner=request.user)]}
    response = Response(data)
    response['Content-Disposition'] = 'attachment; filename="humanities-library.json"'
    return response


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
