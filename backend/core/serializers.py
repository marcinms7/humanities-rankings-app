from dataclasses import asdict
from math import isfinite
from backend.domain.reading_capacity import effort_per_page
from django.db import transaction
from rest_framework import serializers
from backend.domain.reading_time import ReadingMaterial, ReadingLoad, ReaderProfile, estimate_reading_time, difficulty_multiplier
from backend.domain.scoring import validate_scores
from .models import (User, Person, Tag, Work, Edition, Ranking, RankingEntry, ResearchSource,
                     RankingPreference, LibraryItem, PlanItem)
from .reading_basis import length_edition, needs_review, capture_plan, plan_effort, plan_needs_review, LABELS


def reading_estimate(work, edition, request, remaining_page=None, finished=False):
    rate = request.user.words_per_minute if request and request.user.is_authenticated else 250
    words = edition.word_count if edition else None
    pages = edition.pages if edition else None
    if finished:
        words, pages = 0, 0
    elif remaining_page is not None:
        if pages:
            fraction = max(0, pages - remaining_page) / pages
            words = round(words * fraction) if words else None
            pages = max(0, pages - remaining_page)
        elif remaining_page:
            # Page progress cannot be converted to a fraction without the edition length.
            words, pages = None, None
    result = asdict(estimate_reading_time(ReadingMaterial(word_count=words, page_count=pages,
                  load=ReadingLoad(work.reading_load), load_multiplier_override=work.reading_effort_override), ReaderProfile(rate)))
    result['assumptions'] = list(result['assumptions'])
    result['page_count_basis'] = getattr(edition, 'pages_basis', 'unknown') if edition else 'unknown'
    if edition and edition.pages:
        result['assumptions'].append(LABELS.get(result['page_count_basis'], LABELS['unknown']))
    return result


class EditableSerializer(serializers.ModelSerializer):
    edit_version = serializers.SerializerMethodField()

    def get_edit_version(self, obj):
        from .mutations import edit_version
        return edit_version(obj)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'display_name', 'is_staff', 'home_page', 'pages_per_day', 'pages_per_week', 'pages_per_month',
                  'reading_target_period', 'reading_days_per_week', 'difficulty_aware_planning', 'words_per_minute', 'theme']
        read_only_fields = ['id', 'username', 'is_staff']


def validate_image(image):
    if image.size > 8 * 1024 * 1024:
        raise serializers.ValidationError('Images must be smaller than 8 MB.')
    if image.image.format not in {'JPEG', 'PNG', 'WEBP'}:
        raise serializers.ValidationError('Use a JPEG, PNG or WebP image.')
    return image


def string_list(value):
    if not isinstance(value, list) or len(value) > 50 or any(not isinstance(v, str) or len(v) > 100 for v in value):
        raise serializers.ValidationError('Use a list of up to 50 short names.')
    return list(dict.fromkeys(v.strip() for v in value if v.strip()))


class PersonSerializer(EditableSerializer):
    portrait_thumbnail = serializers.SerializerMethodField()

    def get_portrait_thumbnail(self, obj):
        from .thumbnails import thumbnail_url
        return thumbnail_url(obj.portrait, 240)

    class Meta:
        model = Person
        fields = ['id', 'edit_version', 'name', 'biography', 'countries', 'portrait', 'portrait_thumbnail', 'image_attribution', 'source_url']
    validate_countries = staticmethod(string_list)
    validate_portrait = staticmethod(validate_image)


class EditionSerializer(EditableSerializer):
    cover_thumbnail = serializers.SerializerMethodField()

    def get_cover_thumbnail(self, obj):
        from .thumbnails import thumbnail_url
        return thumbnail_url(obj.cover, 240)

    class Meta:
        model = Edition
        fields = ['id', 'edit_version', 'work', 'language', 'translator', 'publisher', 'isbn', 'pages', 'word_count', 'abridged',
                  'translation_notes', 'source_url', 'cover', 'image_attribution', 'pages_basis', 'pages_source_url',
                  'cover_basis', 'cover_source_url', 'cover_thumbnail']
    validate_cover = staticmethod(validate_image)

    def validate(self, attrs):
        if 'pages' in attrs and (not self.instance or attrs['pages'] != self.instance.pages):
            attrs.setdefault('pages_basis', 'manually_recorded' if attrs['pages'] else 'unknown')
            attrs.setdefault('pages_source_url', '')
        if 'cover' in attrs:
            attrs.setdefault('cover_basis', 'manually_supplied')
        return attrs


class WorkSerializer(EditableSerializer):
    difficulty_factors = serializers.JSONField(write_only=True, required=False)
    authors = PersonSerializer(many=True, read_only=True)
    author_names = serializers.ListField(child=serializers.CharField(max_length=240), write_only=True, required=False)
    author_ids = serializers.PrimaryKeyRelatedField(queryset=Person.objects.all(), many=True, write_only=True, required=False)
    tags = serializers.SerializerMethodField()
    genres = serializers.SerializerMethodField()
    tag_names = serializers.ListField(child=serializers.CharField(max_length=100), write_only=True, required=False)
    genre_names = serializers.ListField(child=serializers.CharField(max_length=100), write_only=True, required=False)
    edition = EditionSerializer(source='default_edition', read_only=True)
    edition_input = serializers.DictField(write_only=True, required=False)
    reading_time = serializers.SerializerMethodField()
    class Meta:
        model = Work
        fields = ['id', 'edit_version', 'title', 'authors', 'author_names', 'author_ids', 'form', 'field', 'original_year', 'original_language',
                  'countries', 'tags', 'tag_names', 'genres', 'genre_names', 'description', 'reading_load', 'reading_effort_override', 'edition', 'edition_input',
                  'reading_time', 'contained_in', 'updated_at', 'difficulty_factors']
        read_only_fields = ['updated_at']
    validate_countries = staticmethod(string_list)

    def get_tags(self, obj):
        return [tag.name for tag in obj.tags.all() if not tag.is_archived and tag.kind != 'genre']

    def get_genres(self, obj):
        return sorted((tag.name for tag in obj.tags.all() if not tag.is_archived and tag.kind == 'genre'), key=str.casefold)

    def validate_genre_names(self, value):
        values = string_list(value)
        canonical = {name.casefold(): name for name in Tag.GENRES}
        unknown = [name for name in values if name.casefold() not in canonical]
        if unknown:
            raise serializers.ValidationError(f"Choose genres from the shared catalog: {', '.join(unknown)}.")
        return list(dict.fromkeys(canonical[name.casefold()] for name in values))

    @staticmethod
    def taxonomy_terms(names, kind):
        terms = []
        for name in names:
            term = Tag.objects.filter(name__iexact=name).first()
            if term is not None and term.kind != kind:
                raise serializers.ValidationError({f'{kind}_names': f'{term.name} is already used as a different category.'})
            if term is None:
                term = Tag.objects.create(name=name, kind=kind)
            terms.append(term)
        return terms

    @classmethod
    def replace_taxonomy_kind(cls, work, names, kind):
        retained = list(work.tags.exclude(kind=kind))
        work.tags.set(retained + cls.taxonomy_terms(names, kind))

    def validate_reading_effort_override(self, value):
        if value is not None and (not isfinite(value) or not 0.25 <= value <= 10):
            raise serializers.ValidationError('Use a finite multiplier between 0.25 and 10, or leave it blank.')
        return value

    def validate_original_year(self, value):
        if value == 0 or (value is not None and not -10000 <= value <= 3000):
            raise serializers.ValidationError('Use a year between 10000 BCE and 3000 CE, without year zero.')
        return value

    def validate_edition_input(self, value):
        serializer = EditionSerializer(self.instance.default_edition if self.instance else None, data=value, partial=True)
        serializer.is_valid(raise_exception=True)
        return {k: v for k, v in serializer.validated_data.items() if k not in {'work', 'cover'}}

    def validate_contained_in(self, value):
        seen = {self.instance.pk} if self.instance else set()
        ancestor = value
        while ancestor:
            if ancestor.pk in seen:
                raise serializers.ValidationError('Work collections cannot contain a cycle.')
            seen.add(ancestor.pk)
            ancestor = ancestor.contained_in
        return value

    def validate(self, attrs):
        factors = attrs.pop('difficulty_factors', None)
        if factors is not None:
            if 'reading_effort_override' in attrs:
                raise serializers.ValidationError('Supply difficulty factors or a direct effort override, not both.')
            if not isinstance(factors, dict) or set(factors) != {'prose', 'concepts', 'structure'}:
                raise serializers.ValidationError({'difficulty_factors': 'Provide prose, concepts and structure ratings from 0 to 4.'})
            try:
                attrs['reading_effort_override'] = difficulty_multiplier(**factors)
            except (ValueError, TypeError) as error:
                raise serializers.ValidationError({'difficulty_factors': str(error)}) from error
        if 'author_ids' in attrs and 'author_names' in attrs:
            raise serializers.ValidationError('Choose authors by ID or by name in one request.')
        for name in attrs.get('author_names', []):
            if Person.objects.filter(name=name.strip()).count() > 1:
                raise serializers.ValidationError('Several authors have that name. Choose the author by ID.')
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        authors = validated_data.pop('author_names', [])
        author_ids = validated_data.pop('author_ids', None)
        tags = validated_data.pop('tag_names', [])
        genres = validated_data.pop('genre_names', [])
        edition = validated_data.pop('edition_input', None)
        work = Work.objects.create(**validated_data)
        work.authors.set(author_ids if author_ids is not None else [Person.objects.get_or_create(name=n.strip())[0] for n in authors if n.strip()])
        work.tags.set(self.taxonomy_terms(tags, 'topic') + self.taxonomy_terms(genres, 'genre'))
        if edition is not None:
            work.default_edition = Edition.objects.create(work=work, **edition)
            work.save(update_fields=['default_edition'])
        return work

    @transaction.atomic
    def update(self, instance, validated_data):
        authors = validated_data.pop('author_names', None)
        author_ids = validated_data.pop('author_ids', None)
        tags = validated_data.pop('tag_names', None)
        genres = validated_data.pop('genre_names', None)
        edition = validated_data.pop('edition_input', None)
        instance = super().update(instance, validated_data)
        if author_ids is not None:
            instance.authors.set(author_ids)
        elif authors is not None:
            instance.authors.set([Person.objects.get_or_create(name=n.strip())[0] for n in authors if n.strip()])
        if tags is not None:
            self.replace_taxonomy_kind(instance, tags, 'topic')
        if genres is not None:
            self.replace_taxonomy_kind(instance, genres, 'genre')
        if edition is not None:
            if instance.default_edition:
                Edition.objects.filter(pk=instance.default_edition_id).update(**edition)
                instance.refresh_from_db()
            else:
                instance.default_edition = Edition.objects.create(work=instance, **edition)
                instance.save(update_fields=['default_edition'])
        return instance

    def get_reading_time(self, obj):
        return reading_estimate(obj, obj.default_edition, self.context.get('request'))


class PreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = RankingPreference
        fields = ['bookmarked', 'refresh_interval_days', 'refresh_requested_at', 'weights', 'overrides']
        read_only_fields = ['refresh_requested_at']

    def validate(self, attrs):
        ranking = self.context['ranking']
        allowed = [c['id'] for c in ranking.criteria]
        try:
            if 'weights' in attrs:
                validate_scores(attrs['weights'], allowed, 100)
            if 'overrides' in attrs:
                overrides = attrs['overrides']
                if not isinstance(overrides, dict):
                    raise ValueError('Overrides must be keyed by ranking entry ID.')
                entries = set(str(pk) for pk in ranking.entries.values_list('pk', flat=True))
                if set(overrides) - entries:
                    raise ValueError('An override references an entry outside this ranking.')
                for values in overrides.values():
                    validate_scores(values, allowed, 10)
        except ValueError as error:
            raise serializers.ValidationError(str(error)) from error
        return attrs


class RankingSerializer(serializers.ModelSerializer):
    def to_representation(self, instance):
        data = super().to_representation(instance)
        view = self.context.get('view')
        request = self.context.get('request')
        if request and request.query_params.get('compact') == '1':
            scope = data.get('scope') or {}
            if isinstance(scope.get('editorial'), dict):
                data['scope'] = {**scope, 'editorial': {**scope['editorial'], 'entries': {}}}
        if self.context.get('summary') or (view and view.action in ['list', 'explore']):
            # Overview cards need scope filters, not full per-book editorial dossiers.
            scope = data.get('scope') or {}
            data['scope'] = {key: value for key, value in scope.items() if key in [
                'countries', 'forms', 'tags', 'group_by', 'position_count', 'source_record_count'
            ]}
            data['has_editorial'] = bool(scope.get('editorial'))
        return data

    order_status = serializers.SerializerMethodField()

    def get_order_status(self, obj):
        from .evidence_provenance import order_status
        return order_status(obj)

    entry_count = serializers.IntegerField(read_only=True, default=0)
    source_count = serializers.IntegerField(read_only=True, default=0)
    preference = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    share_url = serializers.SerializerMethodField()
    class Meta:
        model = Ranking
        fields = ['id', 'slug', 'title', 'description', 'domain', 'item_type', 'presentation', 'origin', 'owner',
                  'is_public', 'scope', 'target_size', 'status', 'source_url', 'publisher', 'criteria', 'revision',
                  'created_at', 'updated_at', 'last_researched_at', 'last_sources_checked_at', 'entry_count',
                  'source_count', 'preference', 'can_edit', 'sharing_enabled', 'share_url', 'order_status']
        read_only_fields = ['slug', 'origin', 'owner', 'is_public', 'status', 'revision', 'created_at', 'updated_at',
                            'last_researched_at', 'last_sources_checked_at', 'sharing_enabled']

    def get_preference(self, obj):
        pref = getattr(obj, 'viewer_prefs', [])
        return PreferenceSerializer(pref[0]).data if pref else None

    def get_can_edit(self, obj):
        from .ranking_policy import can_edit_ranking
        return can_edit_ranking(obj, self.context['request'].user)

    def get_share_url(self, obj):
        user = self.context['request'].user
        return f'/shared/{obj.share_token}' if user.is_authenticated and obj.owner_id == user.pk and obj.sharing_enabled else None

    def validate_criteria(self, value):
        if not isinstance(value, list) or len(value) > 20:
            raise serializers.ValidationError('Use at most 20 criteria.')
        ids = []
        for c in value:
            if not isinstance(c, dict) or not isinstance(c.get('id'), str) or not isinstance(c.get('label'), str):
                raise serializers.ValidationError('Each criterion needs an id and label.')
            if not c['id'].strip() or len(c['id']) > 60 or not c['label'].strip() or len(c['label']) > 100:
                raise serializers.ValidationError('Use short, nonempty criterion IDs and labels.')
            ids.append(c['id'])
        if len(set(ids)) != len(ids):
            raise serializers.ValidationError('Criterion IDs must be unique.')
        return value

    def validate_scope(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError('Scope must be an object.')
        for key in ['forms', 'countries', 'tags']:
            if key in value:
                value[key] = string_list(value[key])
        if set(value.get('forms', [])) - set(Work.FORMS):
            raise serializers.ValidationError('Choose supported work forms.')
        return value

    def validate(self, attrs):
        if not self.instance:
            return attrs
        current_criteria = {c['id'] for c in self.instance.criteria}
        next_criteria = {c['id'] for c in attrs.get('criteria', self.instance.criteria)}
        removed = current_criteria - next_criteria
        if removed:
            # Retain saved shared assessments and every reader's private overrides.
            for entry in self.instance.entries.all():
                if removed & set(entry.assessments):
                    raise serializers.ValidationError('Copy this list before removing criteria with saved assessments.')
            for pref in self.instance.preferences.all():
                if removed & set(pref.weights) or any(removed & set(v) for v in pref.overrides.values()):
                    raise serializers.ValidationError('Copy this list before removing criteria with saved preferences.')
        scope = attrs.get('scope', self.instance.scope)
        if scope.get('forms') and self.instance.entries.filter(work__isnull=False).exclude(work__form__in=scope['forms']).exists():
            raise serializers.ValidationError('Existing entries fall outside the new form scope.')
        return attrs


class EntrySerializer(serializers.ModelSerializer):
    position = serializers.IntegerField(min_value=1, required=False)
    groupings = serializers.JSONField(read_only=True)
    book = WorkSerializer(source='work', read_only=True)
    author = PersonSerializer(source='person', read_only=True)
    class Meta:
        model = RankingEntry
        fields = ['id', 'work', 'person', 'book', 'author', 'position', 'source_rank', 'rationale', 'assessments', 'groupings']

    def validate(self, attrs):
        ranking = self.context['ranking']
        work, person = attrs.get('work'), attrs.get('person')
        if (ranking.item_type == 'work' and (not work or person)) or (ranking.item_type == 'person' and (not person or work)):
            raise serializers.ValidationError('The entry must match this ranking’s item type.')
        if (work and work.is_archived) or (person and person.is_archived):
            raise serializers.ValidationError('Choose an active catalog item.')
        if ranking.presentation != 'ranked' and attrs.get('source_rank') is not None:
            raise serializers.ValidationError('Unranked collections and reading sequences do not have merit ranks.')
        if work and ranking.scope.get('forms') and work.form not in ranking.scope['forms']:
            raise serializers.ValidationError('This work’s form is outside the ranking scope.')
        try:
            validate_scores(attrs.get('assessments', {}), [c['id'] for c in ranking.criteria], 10)
        except ValueError as error:
            raise serializers.ValidationError(str(error)) from error
        return attrs


class SourceSerializer(serializers.ModelSerializer):
    provenance = serializers.SerializerMethodField()

    def get_provenance(self, obj):
        from .evidence_provenance import source_provenance
        return source_provenance(obj)

    class Meta:
        model = ResearchSource
        exclude = ['ranking']


class LibrarySerializer(EditableSerializer):
    basis_needs_review = serializers.SerializerMethodField()
    validate_shelves = staticmethod(string_list)
    validate_personal_tags = staticmethod(string_list)
    rating = serializers.IntegerField(min_value=1, max_value=10, required=False, allow_null=True)
    book = WorkSerializer(source='work', read_only=True)
    selected_edition = serializers.SerializerMethodField()
    reading_time = serializers.SerializerMethodField()
    remaining_reading_time = serializers.SerializerMethodField()
    class Meta:
        model = LibraryItem
        fields = ['id', 'edit_version', 'work', 'book', 'edition', 'selected_edition', 'status', 'current_page', 'rating', 'notes', 'started_on', 'finished_on', 'shelves', 'personal_tags', 'read_next_position',
                  'reading_time', 'remaining_reading_time', 'updated_at', 'reading_basis', 'basis_needs_review']
        read_only_fields = ['updated_at', 'read_next_position', 'reading_basis']

    def validate(self, attrs):
        work = attrs.get('work', self.instance.work if self.instance else None)
        from django.utils import timezone
        if work and work.is_archived and not self.instance:
            raise serializers.ValidationError({'work': 'Choose an active catalog work.'})
        # A submitted rating means the reader has read the work, regardless of
        # which UI submitted it. Clearing a rating does not undo completion.
        if attrs.get('rating') is not None:
            attrs['status'] = 'finished'
        status_change = attrs.get('status')
        previous_status = self.instance.status if self.instance else 'want_to_read'
        if status_change == 'reading' and previous_status != 'reading' and 'started_on' not in attrs and not (self.instance and self.instance.started_on):
            attrs['started_on'] = timezone.localdate()
        if status_change == 'finished' and previous_status != 'finished' and 'finished_on' not in attrs:
            attrs['finished_on'] = timezone.localdate()
        start = attrs.get('started_on', self.instance.started_on if self.instance else None)
        finish = attrs.get('finished_on', self.instance.finished_on if self.instance else None)
        if start and finish and finish < start:
            raise serializers.ValidationError('Finish date cannot precede start date.')
        status = attrs.get('status', self.instance.status if self.instance else 'want_to_read')
        if finish and status != 'finished':
            raise serializers.ValidationError('A finish date requires Finished status. Clear it or start a reread.')
        if self.instance and self.instance.status in ['finished', 'abandoned'] and status not in ['finished', 'abandoned']:
            raise serializers.ValidationError('Use Start reread to preserve the previous reading attempt.')
        if self.instance and work.pk != self.instance.work_id:
            raise serializers.ValidationError('Save the other work as a separate library item.')
        edition = attrs.get('edition', self.instance.edition if self.instance else None)
        if edition and edition.work_id != work.pk:
            raise serializers.ValidationError('Choose an edition of this work.')
        if edition and edition.is_archived and (not self.instance or edition.pk != self.instance.edition_id):
            raise serializers.ValidationError({'edition': 'Choose an active edition of this work.'})
        if self.instance and 'edition' in attrs and not self.context.get('edition_transition'):
            if (edition.pk if edition else None) != self.instance.edition_id:
                raise serializers.ValidationError({'edition': 'Preview and confirm the edition change before saving.'})
        edition = edition or work.default_edition
        if not self.instance and edition and edition.is_archived:
            raise serializers.ValidationError({'edition': 'The default edition is archived. Choose an active edition of this work.'})
        if self.instance and not self.context.get('edition_transition'):
            edition = length_edition(self.instance)
        page = attrs.get('current_page', self.instance.current_page if self.instance else 0)
        if edition and edition.pages and page > edition.pages:
            raise serializers.ValidationError('Progress cannot exceed the edition’s page count.')
        return attrs

    def get_selected_edition(self, obj):
        edition = obj.edition or obj.work.default_edition
        if obj.reading_basis and obj.reading_basis.get('edition_id') != (edition.pk if edition else None):
            if not hasattr(self, '_historical_editions'):
                instances = getattr(self.parent, 'instance', None)
                rows = list(instances) if instances is not None and hasattr(instances, '__iter__') else [obj]
                ids = {item.reading_basis.get('edition_id') for item in rows if item.reading_basis}
                self._historical_editions = Edition.objects.in_bulk([pk for pk in ids if pk])
            edition = self._historical_editions.get(obj.reading_basis.get('edition_id'))
        if not edition:
            return None
        data = EditionSerializer(edition, context=self.context).data
        from .reading_basis import EDITION_FIELDS
        if obj.reading_basis:
            data.update({key: obj.reading_basis.get(key) for key in EDITION_FIELDS})
        return data

    def get_basis_needs_review(self, obj):
        return needs_review(obj)

    def get_reading_time(self, obj):
        return reading_estimate(obj.work, length_edition(obj), self.context.get('request'))

    def get_remaining_reading_time(self, obj):
        return reading_estimate(obj.work, length_edition(obj), self.context.get('request'),
                                remaining_page=obj.current_page, finished=obj.status == 'finished')


class PlanSerializer(EditableSerializer):
    has_history = serializers.SerializerMethodField()
    basis_needs_review = serializers.SerializerMethodField()
    refresh_basis = serializers.BooleanField(write_only=True, required=False)
    classical_study = serializers.SerializerMethodField()
    effort_multiplier = serializers.SerializerMethodField()
    effort_pages = serializers.SerializerMethodField()

    def get_has_history(self, obj):
        from .reading_workflow import allocation_has_history
        return allocation_has_history(obj)

    def get_classical_study(self, obj):
        if not hasattr(self, '_classical_plans'):
            from .models import ClassicalStudyProfile
            state = ClassicalStudyProfile.objects.filter(user=self.context['request'].user).values_list('state', flat=True).first() or {}
            self._classical_plans = state.get('companion', {}).get('plans', {})
        item = self._classical_plans.get(str(obj.pk))
        return {k: item.get(k) for k in ('mode', 'passages', 'done')} if item and item.get('work_id') == obj.work_id else None

    def get_effort_multiplier(self, obj):
        return plan_effort(obj, self.context['request'].user)

    def get_basis_needs_review(self, obj):
        if not hasattr(self, '_basis_cache'):
            self._basis_cache = {}
            # One lookup for the visible page, rather than one per allocation.
            instances = getattr(self.parent, 'instance', None)
            rows = list(instances) if instances is not None and hasattr(instances, '__iter__') else [obj]
            work_ids = {item.work_id for item in rows}
            library = {item.work_id: item for item in LibraryItem.objects.filter(
                user_id=obj.user_id, work_id__in=work_ids).select_related('edition', 'work__default_edition')}
            from .reading_basis import capture_edition
            for row in rows:
                item = library.get(row.work_id)
                edition = length_edition(item) if item else row.work.default_edition
                basis = dict(item.reading_basis) if item and item.reading_basis else capture_edition(edition)
                basis['effort_multiplier'] = effort_per_page(row.work, edition)
                self._basis_cache[row.work_id] = basis
        if obj.work_id not in self._basis_cache:
            self._basis_cache[obj.work_id] = capture_plan(obj.work, obj.user_id)
        return plan_needs_review(obj, self._basis_cache[obj.work_id])

    def update(self, instance, validated_data):
        if validated_data.pop('refresh_basis', False):
            validated_data['reading_basis'] = capture_plan(validated_data.get('work', instance.work), instance.user_id)
        return super().update(instance, validated_data)

    def create(self, validated_data):
        validated_data.pop('refresh_basis', None)
        return super().create(validated_data)

    def get_effort_pages(self, obj):
        return round(obj.pages * self.get_effort_multiplier(obj), 2) if obj.pages is not None else None

    position = serializers.IntegerField(min_value=1, required=False)
    pages = serializers.IntegerField(min_value=1, allow_null=True, required=False)
    book = WorkSerializer(source='work', read_only=True)
    class Meta:
        model = PlanItem
        fields = ['id', 'edit_version', 'work', 'book', 'month', 'position', 'pages', 'locked', 'effort_multiplier', 'effort_pages', 'classical_study',
                  'reading_basis', 'basis_needs_review', 'refresh_basis', 'pages_read', 'carried_pages', 'updated_at', 'has_history']
        read_only_fields = ['reading_basis', 'pages_read', 'carried_pages', 'updated_at']

    def validate_month(self, value):
        if value.day != 1:
            raise serializers.ValidationError('Use the first day of a month.')
        return value

    def validate(self, attrs):
        user = self.context['request'].user
        work = attrs.get('work', self.instance.work if self.instance else None)
        month = attrs.get('month', self.instance.month if self.instance else None)
        existing = PlanItem.objects.filter(user=user, work=work, month=month)
        if self.instance:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError('This work is already planned for that month.')
        if work and not LibraryItem.objects.filter(user=user, work=work).exists():
            raise serializers.ValidationError('Save the work to your library before planning it.')
        if self.instance and self.instance.locked and any(k in attrs and attrs[k] != getattr(self.instance, k) for k in ['work', 'month', 'pages', 'position']):
            raise serializers.ValidationError('Unlock this book before moving or editing its allocation.')
        if self.instance and self.instance.locked and attrs.get('refresh_basis'):
            raise serializers.ValidationError('Unlock this allocation before confirming new edition assumptions.')
        if self.instance:
            from .reading_workflow import allocation_has_history
            if allocation_has_history(self.instance) and (
                    attrs.get('refresh_basis') or any(key in attrs and attrs[key] != getattr(self.instance, key)
                                                     for key in ['work', 'month', 'pages'])):
                raise serializers.ValidationError('This allocation has recorded reading or carryover history. Use carryover for its remaining pages; clear recorded progress first only if it was entered in error.')
        if self.instance and work.pk != self.instance.work_id:
            raise serializers.ValidationError('Create a separate allocation for another work.')
        return attrs


class PersonNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = Person
        fields = ['id', 'name']


class EditionCardSerializer(EditionSerializer):
    class Meta(EditionSerializer.Meta):
        fields = ['id', 'cover', 'cover_thumbnail', 'pages', 'pages_basis', 'image_attribution']


class WorkCardSerializer(WorkSerializer):
    """Book-row fields only; detail/edit serializers retain full metadata."""
    authors = PersonNameSerializer(many=True, read_only=True)
    edition = EditionCardSerializer(source='default_edition', read_only=True)

    class Meta(WorkSerializer.Meta):
        fields = ['id', 'title', 'authors', 'form', 'field', 'genres', 'countries', 'edition', 'reading_time']
        read_only_fields = fields


class LibrarySummarySerializer(LibrarySerializer):
    book = WorkCardSerializer(source='work', read_only=True)

    class Meta(LibrarySerializer.Meta):
        fields = [field for field in LibrarySerializer.Meta.fields if field not in ['notes', 'selected_edition', 'reading_time']]
        read_only_fields = fields


class PlanSummarySerializer(PlanSerializer):
    book = WorkCardSerializer(source='work', read_only=True)
