"""Private, explainable discovery using saved signals, never invented merit scores."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response

from .mutations import mutation_guard
from .models import (LibraryItem, RankingEntry, RankingPreference, ReadingAttempt,
                     RecommendationFeedback, SavedDiscoveryFilter, Tag, Work)
from .reading_basis import length_edition
from .reading_insights import membership_rows, shared_lists
from .saved_discovery import apply_discovery_filters
from .serializers import reading_estimate


SLOTS = ('familiar', 'new_author', 'short')
ACTIONS = ('neutral', 'more_like', 'not_interested', 'later')
FIELDS = ('literature', 'philosophy', 'nonfiction', 'manga')
NOTE = ('Suggestions use your explicit interests, More like feedback, bookmarked rankings and wishlist, '
        'in that order; ties use title. They do not compare scores or change source order. '
        'Finished books and current reads are excluded. Author familiarity uses recorded reading history, '
        'not ratings. Time estimates are provisional and edition-dependent.')


class RecommendationConflict(APIException):
    status_code = 409
    default_detail = 'These preferences changed in another window. Refresh before saving again.'


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise ValidationError({'non_field_errors': ['Send an object.']})
        unknown = set(data) - set(self.fields)
        if unknown:
            raise ValidationError({'non_field_errors': [f'Unsupported fields: {", ".join(sorted(unknown))}.']})
        return super().to_internal_value(data)


class RecommendationPreferencesCommandSerializer(StrictSerializer):
    expected_revision = serializers.IntegerField(min_value=0)
    fields = serializers.ListField(child=serializers.ChoiceField(choices=FIELDS), max_length=4)
    genres = serializers.ListField(child=serializers.CharField(max_length=100), max_length=12)
    topics = serializers.ListField(child=serializers.CharField(max_length=60), max_length=8)
    short_pages = serializers.IntegerField(min_value=25, max_value=1000)
    saved_filter = serializers.IntegerField(min_value=1, allow_null=True)

    def validate_genres(self, value):
        names = list(dict.fromkeys(v.strip() for v in value if v.strip()))
        existing = set(Tag.objects.filter(kind='genre', is_archived=False, name__in=names).values_list('name', flat=True))
        if set(names) - existing:
            raise ValidationError('Choose genres present in the catalog.')
        return names

    def validate_topics(self, value):
        return list(dict.fromkeys(v.strip() for v in value if v.strip()))

    def validate_saved_filter(self, value):
        if value is not None and not SavedDiscoveryFilter.objects.filter(user=self.context['request'].user, pk=value).exists():
            raise ValidationError('Choose one of your own saved filters.')
        return value


class RecommendationPreferencesSerializer(serializers.Serializer):
    revision = serializers.IntegerField()
    fields = serializers.ListField(child=serializers.ChoiceField(choices=FIELDS))
    genres = serializers.ListField(child=serializers.CharField())
    topics = serializers.ListField(child=serializers.CharField())
    short_pages = serializers.IntegerField()
    saved_filter = serializers.IntegerField(allow_null=True)
    saved_filter_name = serializers.CharField(allow_blank=True)
    missing_saved_filter = serializers.BooleanField()


class RecommendationFeedbackCommandSerializer(StrictSerializer):
    work = serializers.IntegerField(min_value=1)
    action = serializers.ChoiceField(choices=ACTIONS)
    expected_revision = serializers.IntegerField(min_value=0)
    days = serializers.IntegerField(min_value=1, max_value=365, required=False, default=30)


class RecommendationFeedbackSerializer(serializers.Serializer):
    work = serializers.IntegerField()
    title = serializers.CharField()
    archived = serializers.BooleanField()
    action = serializers.ChoiceField(choices=ACTIONS)
    revision = serializers.IntegerField()
    deferred_until = serializers.DateField(allow_null=True)
    active = serializers.BooleanField()


class RecommendationFeedbackPageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    pages = serializers.IntegerField()
    results = RecommendationFeedbackSerializer(many=True)


class RecommendationEstimateSerializer(serializers.Serializer):
    status = serializers.CharField()
    estimated_hours = serializers.FloatField(allow_null=True)
    low_hours = serializers.FloatField(allow_null=True)
    high_hours = serializers.FloatField(allow_null=True)
    length_basis = serializers.CharField(allow_null=True)
    load_multiplier = serializers.FloatField()
    algorithm_version = serializers.CharField()
    calibrated = serializers.BooleanField()
    assumptions = serializers.ListField(child=serializers.CharField())
    page_count_basis = serializers.CharField()


class RecommendationListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    kind = serializers.CharField()
    slug = serializers.CharField()
    origin = serializers.CharField()
    presentation = serializers.CharField()
    position = serializers.IntegerField(allow_null=True)
    source_rank = serializers.IntegerField(allow_null=True)


class RecommendationCandidateSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    authors = serializers.ListField(child=serializers.CharField())
    reasons = serializers.ListField(child=serializers.CharField())
    pages = serializers.IntegerField(allow_null=True)
    page_basis = serializers.CharField()
    edition_basis = serializers.CharField()
    estimate = RecommendationEstimateSerializer()
    lists = RecommendationListSerializer(many=True)
    feedback = serializers.ChoiceField(choices=ACTIONS)
    feedback_revision = serializers.IntegerField()


class RecommendationSlotSerializer(serializers.Serializer):
    key = serializers.ChoiceField(choices=SLOTS)
    title = serializers.CharField()
    explanation = serializers.CharField()
    selected = RecommendationCandidateSerializer(allow_null=True)
    alternatives = RecommendationCandidateSerializer(many=True)


class RecommendationCommitmentSerializer(serializers.Serializer):
    books = serializers.IntegerField()
    known_pages = serializers.IntegerField()
    unknown_pages = serializers.IntegerField()
    known_estimated_hours = serializers.FloatField()
    known_low_hours = serializers.FloatField()
    known_high_hours = serializers.FloatField()
    unknown_estimates = serializers.IntegerField()


class RecommendationBundleSerializer(serializers.Serializer):
    note = serializers.CharField()
    personalized = serializers.BooleanField()
    needs_preferences_review = serializers.BooleanField()
    preferences = RecommendationPreferencesSerializer()
    slots = RecommendationSlotSerializer(many=True)
    commitment = RecommendationCommitmentSerializer()


def private_response(data, serializer_class, status=200):
    response = Response(serializer_class(data).data, status=status)
    response['Cache-Control'] = 'private, no-store'
    return response


def preferences_payload(row):
    details = row.details if row else {}
    saved = row.saved_filter if row and row.saved_filter_id else None
    return {'revision': row.revision if row else 0,
            'fields': details.get('fields', []), 'genres': details.get('genres', []),
            'topics': details.get('topics', []), 'short_pages': details.get('short_pages', 250),
            'saved_filter': saved.pk if saved else None,
            'saved_filter_name': saved.name if saved else details.get('saved_filter_name', ''),
            'missing_saved_filter': bool(details.get('saved_filter_id') and not saved)}


@api_view(['GET', 'PATCH'])
@permission_classes([permissions.IsAuthenticated])
@mutation_guard
def recommendation_preferences(request):
    if request.method == 'GET':
        row = RecommendationFeedback.objects.filter(user=request.user, work__isnull=True).select_related('saved_filter').first()
        return private_response(preferences_payload(row), RecommendationPreferencesSerializer)
    command = RecommendationPreferencesCommandSerializer(data=request.data, context={'request': request})
    command.is_valid(raise_exception=True)
    values = command.validated_data
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        row = RecommendationFeedback.objects.select_for_update().filter(user=request.user, work__isnull=True).first()
        if values['expected_revision'] != (row.revision if row else 0):
            raise RecommendationConflict()
        # Recheck ownership inside the same transaction as the write.
        saved = get_object_or_404(SavedDiscoveryFilter.objects.filter(user=request.user), pk=values['saved_filter']) if values['saved_filter'] else None
        if row is None:
            row = RecommendationFeedback(user=request.user, action='preferences')
        else:
            row.revision += 1
        row.saved_filter = saved
        row.details = {key: values[key] for key in ('fields', 'genres', 'topics', 'short_pages')}
        row.details.update(saved_filter_id=saved.pk if saved else None, saved_filter_name=saved.name if saved else '')
        row.save()
        payload = preferences_payload(row)
    return private_response(payload, RecommendationPreferencesSerializer)


def feedback_payload(row):
    return {'work': row.work_id, 'title': row.work.title, 'archived': row.work.is_archived,
            'action': row.action, 'revision': row.revision, 'deferred_until': row.deferred_until,
            'active': row.action != 'neutral' and (row.action != 'later' or row.deferred_until > timezone.localdate())}


@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
@mutation_guard
def recommendation_feedback(request):
    if request.method == 'GET':
        try:
            page = int(request.query_params.get('page', 1))
            if not 1 <= page <= 100000:
                raise ValueError
        except (TypeError, ValueError):
            raise ValidationError('Choose a valid feedback page.')
        rows = RecommendationFeedback.objects.filter(user=request.user, work__isnull=False).exclude(action='neutral').select_related('work').order_by('-updated_at', 'pk')
        count = rows.count()
        return private_response({'count': count, 'page': page, 'pages': max(1, (count + 23) // 24),
            'results': [feedback_payload(row) for row in rows[(page - 1) * 24:page * 24]]}, RecommendationFeedbackPageSerializer)
    command = RecommendationFeedbackCommandSerializer(data=request.data)
    command.is_valid(raise_exception=True)
    values = command.validated_data
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        row = RecommendationFeedback.objects.select_for_update().filter(user=request.user, work_id=values['work']).select_related('work').first()
        if values['expected_revision'] != (row.revision if row else 0):
            raise RecommendationConflict('This feedback changed in another window. Refresh before choosing again.')
        if row is None:
            work = get_object_or_404(Work.objects.filter(is_archived=False), pk=values['work'])
            row = RecommendationFeedback(user=request.user, work=work)
        else:
            row.revision += 1
        row.action = values['action']
        row.deferred_until = timezone.localdate() + timedelta(days=values['days']) if row.action == 'later' else None
        row.save()
        payload = feedback_payload(row)
    return private_response(payload, RecommendationFeedbackSerializer)


def candidate_query(user, prefs):
    params = {'unread': 'yes'}
    if prefs['saved_filter']:
        params['saved_filter'] = prefs['saved_filter']
    works = apply_discovery_filters(Work.objects.filter(is_archived=False), user, params)
    started = Q(status__in=['reading', 'paused', 'finished', 'abandoned']) | Q(current_page__gt=0) | Q(started_on__isnull=False)
    current = LibraryItem.objects.filter(started, user=user)
    attempted = ReadingAttempt.objects.filter(started, user=user)
    works = works.exclude(pk__in=current.values('work_id'))
    seen = Work.objects.filter(Q(pk__in=current.values('work_id')) | Q(pk__in=attempted.values('work_id')))
    author_links = Work.authors.through.objects.filter(work_id=OuterRef('pk'))
    known_authors = author_links.exclude(person__name__istartswith='anonymous').exclude(person__name__istartswith='unknown').exclude(person__name__istartswith='various').exclude(person__name='').filter(person__is_archived=False)
    mine = RecommendationFeedback.objects.filter(user=user, work__isnull=False)
    hidden = mine.filter(Q(action='not_interested') | Q(action='later', deferred_until__gt=timezone.localdate()))
    works = works.exclude(pk__in=hidden.values('work_id'))
    seeds = mine.filter(action='more_like', work__is_archived=False)
    seed_authors = Work.authors.through.objects.filter(work_id__in=seeds.values('work_id')).values('person_id')
    seed_tags = Work.tags.through.objects.filter(work_id__in=seeds.values('work_id'), tag__is_archived=False).values('tag_id')
    related = Work.objects.filter(pk=OuterRef('pk')).filter(Q(authors__pk__in=seed_authors) | Q(tags__pk__in=seed_tags))
    interest = Q(pk__in=[])
    if prefs['fields']:
        interest |= Q(field__in=prefs['fields'])
    if prefs['genres']:
        interest |= Q(tags__name__in=prefs['genres'], tags__kind='genre', tags__is_archived=False)
    for term in prefs['topics']:
        interest |= Q(title__icontains=term) | Q(tags__name__icontains=term, tags__is_archived=False)
    bookmarks = RankingPreference.objects.filter(user=user, bookmarked=True).values('ranking_id')
    entries = RankingEntry.objects.filter(ranking__in=shared_lists(user), ranking__presentation='ranked',
        ranking_id__in=bookmarks, is_archived=False, work_id=OuterRef('pk'))
    works = works.annotate(
        _interest=Exists(Work.objects.filter(interest, pk=OuterRef('pk'))),
        _related=Exists(related), _bookmarked=Exists(entries),
        _wishlist=Exists(LibraryItem.objects.filter(user=user, status='want_to_read', work_id=OuterRef('pk'))),
        _familiar=Exists(known_authors.filter(person_id__in=seen.values('authors__pk'))),
        _known_author=Exists(known_authors))
    return works.order_by('-_interest', '-_related', '-_bookmarked', '-_wishlist', 'title', 'pk')


def commitment_for(selected):
    return {'books': len(selected), 'known_pages': sum(row['pages'] or 0 for row in selected),
        'unknown_pages': sum(row['pages'] is None for row in selected),
        'known_estimated_hours': round(sum(row['estimate']['estimated_hours'] or 0 for row in selected), 2),
        'known_low_hours': round(sum(row['estimate']['low_hours'] or 0 for row in selected), 2),
        'known_high_hours': round(sum(row['estimate']['high_hours'] or 0 for row in selected), 2),
        'unknown_estimates': sum(row['estimate']['estimated_hours'] is None for row in selected)}


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def recommendations(request):
    row = RecommendationFeedback.objects.filter(user=request.user, work__isnull=True).select_related('saved_filter').first()
    prefs = preferences_payload(row)
    if prefs['missing_saved_filter']:
        return private_response({'note': 'Your selected saved filter was deleted. Choose another filter or explicitly clear it to rebuild this bundle.',
            'personalized': False, 'needs_preferences_review': True, 'preferences': prefs,
            'slots': [], 'commitment': commitment_for([])}, RecommendationBundleSerializer)
    base = candidate_query(request.user, prefs)
    # Each slot has a bounded shortlist. Distinct work IDs and varied credited
    # authors are selected without introducing numerical merit assessments.
    familiar = list(base.filter(_familiar=True).prefetch_related('authors', 'tags').select_related('default_edition')[:20])
    fallback = not familiar
    scopes = {'familiar': base if fallback else base.filter(_familiar=True),
              'new_author': base.filter(_known_author=True, _familiar=False),
              'short': base.filter(discovery_pages__gte=1, discovery_pages__lte=prefs['short_pages'])}
    pools = {key: familiar if key == 'familiar' and not fallback else list(scope.prefetch_related('authors', 'tags').select_related('default_edition')[:20]) for key, scope in scopes.items()}
    selected = {}
    for key in SLOTS:
        if request.query_params.get(key):
            try:
                work_id = int(request.query_params[key])
            except (ValueError, TypeError):
                raise ValidationError('Choose a valid substitute.')
            work = scopes[key].filter(pk=work_id).prefetch_related('authors', 'tags').select_related('default_edition').first()
            if work is None or work_id in {item.pk for item in selected.values()}:
                raise ValidationError('A bundle choice is no longer eligible. Refresh the bundle before substituting.')
            selected[key] = work
    # Fill the most restricted slot first so a plentiful slot does not consume
    # the only available short book or new author.
    for key in sorted(SLOTS, key=lambda slot: len(pools[slot])):
        if key in selected:
            continue
        used = {item.pk for item in selected.values()}
        used_authors = {author.pk for item in selected.values() for author in item.authors.all()}
        options = [work for work in pools[key] if work.pk not in used]
        varied = [work for work in options if not {a.pk for a in work.authors.all()} & used_authors]
        if varied or options:
            selected[key] = (varied or options)[0]
    used = {work.pk for work in selected.values()}
    alternatives = {key: [work for work in pools[key] if work.pk not in used][:4] for key in SLOTS}
    all_works = {work.pk: work for work in [*selected.values(), *(w for values in alternatives.values() for w in values)]}
    saved = {item.work_id: item for item in LibraryItem.objects.filter(user=request.user, work_id__in=all_works).select_related('edition', 'work__default_edition')}
    feedback = {item.work_id: item for item in RecommendationFeedback.objects.filter(user=request.user, work_id__in=all_works)}
    memberships = membership_rows(request.user, all_works)
    bookmarks = set(RankingPreference.objects.filter(user=request.user, bookmarked=True).values_list('ranking_id', flat=True))
    author_ids = {author.pk for work in all_works.values() for author in work.authors.all()}
    tag_ids = {tag.pk for work in all_works.values() for tag in work.tags.all() if not tag.is_archived}
    positive = RecommendationFeedback.objects.filter(user=request.user, action='more_like').values('work_id')
    # Preview concrete connections in one bounded batch; a reader may have an
    # arbitrarily large feedback history without loading it all into memory.
    seeds = list(Work.objects.filter(pk__in=positive, is_archived=False).filter(
        Q(authors__pk__in=author_ids) | Q(tags__pk__in=tag_ids)).distinct().prefetch_related('authors', 'tags').order_by('title', 'pk')[:48])
    rendered = {}
    for pk, work in all_works.items():
        tags = [tag for tag in work.tags.all() if not tag.is_archived]
        reasons = []
        if work.field in prefs['fields']:
            reasons.append(f'Matches your interest in {work.field}.')
        genres = [tag.name for tag in tags if tag.kind == 'genre' and tag.name in prefs['genres']]
        if genres:
            reasons.append(f'Matches your selected genres: {", ".join(genres)}.')
        topics = [term for term in prefs['topics'] if term.casefold() in work.title.casefold() or any(term.casefold() in tag.name.casefold() for tag in tags)]
        if topics:
            reasons.append(f'Your topic terms occur in the saved title or tags: {", ".join(topics)}.')
        if work._related:
            connections = []
            work_authors = {author.pk for author in work.authors.all()}
            work_tags = {tag.pk for tag in tags}
            for seed in seeds:
                names = [author.name for author in seed.authors.all() if author.pk in work_authors]
                matching_tags = [tag.name for tag in seed.tags.all() if tag.pk in work_tags]
                if names or matching_tags:
                    connection = 'author ' + ', '.join(names) if names else 'tag ' + ', '.join(matching_tags[:3])
                    connections.append(f'Your More like signal for “{seed.title}” connects through {connection}.')
                if len(connections) == 2:
                    break
            reasons.extend(connections or ['Shares a catalog author or tag with a book you marked More like.'])
        matched = [entry for entry in memberships.get(pk, []) if entry['id'] in bookmarks and entry['presentation'] == 'ranked']
        if matched:
            reasons.append('Appears in your bookmarked rankings: ' + '; '.join(entry['title'] for entry in matched[:3]) + '.')
        if work._wishlist:
            reasons.append('Already on your wishlist, with no reading progress recorded.')
        if work._familiar:
            reasons.append('Shares an author with your recorded reading history.')
        if prefs['saved_filter']:
            reasons.append(f'Fits your saved filter “{prefs["saved_filter_name"]}”.')
        if not reasons:
            reasons.append('Catalog starting point within the current scope; no matching personal signal yet.')
        item = saved.get(pk)
        edition = length_edition(item) if item else work.default_edition
        signal = feedback.get(pk)
        estimate = reading_estimate(work, edition, request)
        estimate['page_count_basis'] = estimate['page_count_basis'] or 'unknown'
        rendered[pk] = {'id': pk, 'title': work.title, 'authors': [a.name for a in work.authors.all()],
            'reasons': reasons, 'pages': edition.pages if edition else None,
            'page_basis': (getattr(edition, 'pages_basis', None) if edition else None) or 'unknown',
            'edition_basis': 'Your saved reading edition and frozen length' if item else 'Current default catalog edition',
            'estimate': estimate, 'lists': matched[:3],
            'feedback': signal.action if signal else 'neutral', 'feedback_revision': signal.revision if signal else 0}
    titles = {'familiar': 'A familiar direction' if fallback else 'An author you have explored',
              'new_author': 'An author to discover', 'short': f'A shorter read · up to {prefs["short_pages"]} pages'}
    explanations = {'familiar': 'Uses your saved signals where available. No unread book by a previously explored author fits this scope.' if fallback else 'An unread book by an author in your recorded reading history.',
        'new_author': 'No identified author on this book appears in your recorded reading history. A wishlist save alone does not count as explored; anonymous and unknown credits do not establish familiarity.',
        'short': 'Only books with a recorded positive page count within your chosen limit qualify. Length and time refer to the edition shown.'}
    slots = [{'key': key, 'title': titles[key], 'explanation': explanations[key],
              'selected': rendered[selected[key].pk] if key in selected else None,
              'alternatives': [rendered[work.pk] for work in alternatives[key]]} for key in SLOTS]
    personalized = bool(prefs['saved_filter'] or any(w._interest or w._related or w._bookmarked or w._wishlist or w._familiar for w in selected.values()))
    return private_response({'note': NOTE, 'personalized': personalized, 'needs_preferences_review': False,
        'preferences': prefs, 'slots': slots, 'commitment': commitment_for([rendered[work.pk] for work in selected.values()])}, RecommendationBundleSerializer)
