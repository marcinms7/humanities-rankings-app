import uuid
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models import F, Q


class User(AbstractUser):
    home_page = models.CharField(max_length=20, default='explore', choices=[('explore', 'Explore'), ('today', 'Today')])
    registration_pending = models.BooleanField(default=False)
    display_name = models.CharField(max_length=100, blank=True)
    pages_per_day = models.PositiveIntegerField(default=25, validators=[MinValueValidator(1), MaxValueValidator(2000)])
    reading_target_period = models.CharField(max_length=10, default='week', choices=[('day', 'Reading day'), ('week', 'Week'), ('month', 'Month')])
    pages_per_week = models.PositiveIntegerField(default=175, validators=[MinValueValidator(1), MaxValueValidator(14000)])
    pages_per_month = models.PositiveIntegerField(default=750, validators=[MinValueValidator(1), MaxValueValidator(62000)])
    reading_days_per_week = models.PositiveIntegerField(default=4, validators=[MinValueValidator(1), MaxValueValidator(7)])
    difficulty_aware_planning = models.BooleanField(default=True)
    words_per_minute = models.PositiveIntegerField(default=250, validators=[MinValueValidator(20), MaxValueValidator(2000)])
    theme = models.CharField(max_length=10, default='system', choices=[(v, v) for v in ['system', 'light', 'dark']])


class Timestamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True


class ClassicalStudyProfile(Timestamped):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    state = models.JSONField(default=dict, blank=True)


class StudyRecord(Timestamped):
    """One growing note/essay/exercise with its existing revision history intact."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='study_records')
    record_key = models.CharField(max_length=64)
    path = models.JSONField()
    value = models.JSONField(default=dict, null=True, blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'record_key'], name='unique_private_study_record')]


class MutationReceipt(models.Model):
    """Private replay receipt; keys never authorize access without the account."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    key = models.CharField(max_length=128)
    request_hash = models.CharField(max_length=64)
    status_code = models.PositiveSmallIntegerField()
    response = models.JSONField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'key'], name='unique_private_mutation_key')]
        indexes = [models.Index(fields=['created_at'], name='mutation_receipt_created_idx')]


class Person(Timestamped):
    is_archived = models.BooleanField(default=False)
    name = models.CharField(max_length=240)
    biography = models.TextField(blank=True)
    countries = models.JSONField(default=list, blank=True)
    portrait = models.ImageField(upload_to='portraits/%Y/%m/', blank=True)
    image_attribution = models.CharField(max_length=500, blank=True)
    source_url = models.URLField(blank=True)
    class Meta:
        ordering = ['name', 'id']
    def __str__(self):
        return self.name


class Tag(models.Model):
    GENRES = [
        'Action', 'Adventure', 'Arts & Artists', 'Autobiographical', "Boys' Love", "Children's", 'Comedy', 'Coming of Age',
        'Crime', 'Cyberpunk', 'Dark Fantasy', 'Drama', 'Dystopian', 'Ecchi', 'Erotica', 'Fantasy', 'Food',
        'Family', 'Gekiga', "Girls' Love", 'Gothic', 'Historical Fiction', 'Horror', 'Isekai', 'Literary Fiction',
        'Magical Girl', 'Magical Realism', 'Martial Arts', 'Mecha', 'Music', 'Mystery', 'Myth & Folklore',
        'Performing Arts', 'Post-Apocalyptic', 'Psychological', 'Romance', 'Satire', 'School Life', 'Science Fiction',
        'Slice of Life', 'Sports', 'Superhero', 'Supernatural', 'Surrealism', 'Thriller', 'War', 'Western', 'Workplace',
    ]
    is_archived = models.BooleanField(default=False)
    name = models.CharField(max_length=100, unique=True)
    kind = models.CharField(max_length=30, default='topic')
    class Meta:
        indexes = [models.Index(fields=['kind', 'name'], name='tag_kind_name_idx')]
    def __str__(self):
        return self.name


class Work(Timestamped):
    is_archived = models.BooleanField(default=False)
    FORMS = ['book', 'essay', 'short_story', 'poem', 'play', 'collection']
    title = models.CharField(max_length=300)
    authors = models.ManyToManyField(Person, related_name='works', blank=True)
    form = models.CharField(max_length=20, default='book', choices=[(v, v) for v in FORMS])
    field = models.CharField(max_length=30, default='literature', choices=[(v, v) for v in ['literature', 'philosophy', 'nonfiction', 'manga']])
    original_year = models.IntegerField(null=True, blank=True)
    original_language = models.CharField(max_length=60, blank=True)
    countries = models.JSONField(default=list, blank=True)
    tags = models.ManyToManyField(Tag, blank=True)
    description = models.TextField(blank=True)
    reading_load = models.CharField(max_length=30, default='classic_literature', choices=[(v, v) for v in ['leisure', 'classic_literature', 'demanding_literature', 'philosophy']])
    reading_effort_override = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0.25), MaxValueValidator(10)])
    default_edition = models.ForeignKey('Edition', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    contained_in = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='contents')
    class Meta:
        ordering = ['title', 'id']
        indexes = [models.Index(fields=['field', 'form']), models.Index(fields=['original_year'])]
    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        if self.original_year == 0:
            raise ValidationError({'original_year': 'There is no year zero.'})
        if self.default_edition_id and self.default_edition.work_id != self.pk:
            raise ValidationError({'default_edition': 'Choose an edition belonging to this work.'})
        ancestor = self.contained_in
        seen = {self.pk} if self.pk else set()
        while ancestor:
            if ancestor.pk in seen:
                raise ValidationError({'contained_in': 'Work collections cannot contain a cycle.'})
            seen.add(ancestor.pk)
            ancestor = ancestor.contained_in


class Edition(Timestamped):
    pages_basis = models.CharField(max_length=40, default='unknown', choices=[
        ('unknown', 'Basis not recorded'), ('isbn_matched', 'ISBN-matched provider record'),
        ('estimated_across_editions', 'Estimate across editions'), ('manually_recorded', 'Manually recorded')])
    pages_source_url = models.URLField(max_length=1000, blank=True)
    cover_source_url = models.URLField(max_length=1000, blank=True)
    cover_basis = models.CharField(max_length=40, default='unknown', choices=[
        ('unknown', 'Basis not recorded'), ('representative_work', 'Representative work image'),
        ('edition_matched', 'Edition-matched image'), ('manually_supplied', 'Manually supplied')])
    is_archived = models.BooleanField(default=False)
    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name='editions')
    language = models.CharField(max_length=60, default='English')
    translator = models.CharField(max_length=240, blank=True)
    publisher = models.CharField(max_length=240, blank=True)
    isbn = models.CharField(max_length=30, blank=True)
    pages = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    word_count = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    abridged = models.BooleanField(default=False)
    translation_notes = models.TextField(blank=True)
    source_url = models.URLField(blank=True)
    cover = models.ImageField(upload_to='covers/%Y/%m/', blank=True)
    image_attribution = models.CharField(max_length=500, blank=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(pages__isnull=True) | Q(pages__gte=1), name='edition_pages_positive'),
                       models.CheckConstraint(condition=Q(word_count__isnull=True) | Q(word_count__gte=1), name='edition_words_positive')]
    def __str__(self):
        return f'{self.work} — {self.language} {self.translator}'

    def clean(self):
        super().clean()
        if self.pk and Edition.objects.filter(pk=self.pk).exclude(work_id=self.work_id).exists():
            raise ValidationError({'work': 'An edition cannot be reassigned to another work.'})


class Ranking(Timestamped):
    is_archived = models.BooleanField(default=False)
    slug = models.SlugField(unique=True, max_length=160)
    title = models.CharField(max_length=240)
    description = models.TextField(blank=True)
    domain = models.CharField(max_length=30, default='literature')
    item_type = models.CharField(max_length=10, default='work', choices=[('work', 'Work'), ('person', 'Person')])
    presentation = models.CharField(max_length=20, default='ranked', choices=[(v, v) for v in ['ranked', 'unranked', 'reading_sequence']])
    origin = models.CharField(max_length=20, default='curated', choices=[(v, v) for v in ['curated', 'external', 'personal']])
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE)
    is_public = models.BooleanField(default=False)
    share_token = models.UUIDField(default=uuid.uuid4, editable=False)
    sharing_enabled = models.BooleanField(default=False)
    scope = models.JSONField(default=dict, blank=True)
    target_size = models.PositiveIntegerField(default=100)
    status = models.CharField(max_length=50, default='awaiting_research')
    source_url = models.URLField(blank=True)
    publisher = models.CharField(max_length=200, blank=True)
    last_researched_at = models.DateTimeField(null=True, blank=True)
    last_sources_checked_at = models.DateTimeField(null=True, blank=True)
    criteria = models.JSONField(default=list, blank=True)
    revision = models.PositiveIntegerField(default=1)
    class Meta:
        ordering = ['title', 'id']
        constraints = [models.CheckConstraint(
            condition=(Q(origin='personal', owner__isnull=False, is_public=False)
                       | (~Q(origin='personal') & Q(owner__isnull=True, sharing_enabled=False))),
            name='ranking_ownership_and_visibility')]
    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        if not isinstance(self.criteria, list) or len(self.criteria) > 20:
            raise ValidationError({'criteria': 'Use a list of at most 20 criteria.'})
        ids = []
        for criterion in self.criteria:
            if (not isinstance(criterion, dict) or not isinstance(criterion.get('id'), str)
                    or not isinstance(criterion.get('label'), str) or not criterion['id'].strip()
                    or len(criterion['id']) > 60 or not criterion['label'].strip() or len(criterion['label']) > 100):
                raise ValidationError({'criteria': 'Every criterion needs a short, nonempty id and label.'})
            ids.append(criterion['id'])
        if len(ids) != len(set(ids)):
            raise ValidationError({'criteria': 'Criterion IDs must be unique.'})
        if not isinstance(self.scope, dict):
            raise ValidationError({'scope': 'Scope must be an object.'})
        if self.origin == 'curated' and self.status in {'published', 'research_complete', 'complete'}:
            count = self.sources.filter(eligible=True, is_archived=False).count() if self.pk else 0
            if count < 50:
                raise ValidationError({'status': 'A curated research target needs at least 50 eligible sources before completion or publication.'})


class RankingEntry(models.Model):
    is_archived = models.BooleanField(default=False)
    ranking = models.ForeignKey(Ranking, on_delete=models.CASCADE, related_name='entries')
    work = models.ForeignKey(Work, null=True, blank=True, on_delete=models.CASCADE)
    person = models.ForeignKey(Person, null=True, blank=True, on_delete=models.CASCADE)
    position = models.PositiveIntegerField(default=1)
    source_rank = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    rationale = models.TextField(blank=True)
    assessments = models.JSONField(default=dict, blank=True)
    # Optional target-local placements for rankings whose structure is not a
    # single global order.  The country anthology uses this to retain one
    # catalog identity while allowing the same work to appear in more than one
    # country section with an independent local rank and note.
    groupings = models.JSONField(default=list, blank=True)
    class Meta:
        ordering = ['position', 'id']
        indexes = [models.Index(fields=['work', 'is_archived', 'position'], name='rank_entry_work_live_pos')]
        constraints = [models.CheckConstraint(condition=(Q(work__isnull=False, person__isnull=True) | Q(work__isnull=True, person__isnull=False)), name='entry_exactly_one_target'),
                       models.UniqueConstraint(fields=['ranking', 'work'], name='unique_ranking_work'),
                       models.UniqueConstraint(fields=['ranking', 'person'], name='unique_ranking_person'),
                       models.CheckConstraint(condition=Q(position__gte=1), name='entry_position_positive'),
                       models.CheckConstraint(condition=Q(source_rank__isnull=True) | Q(source_rank__gte=1), name='entry_rank_positive')]

    def clean(self):
        super().clean()
        if not self.ranking_id:
            return
        if ((self.ranking.item_type == 'work' and (not self.work_id or self.person_id))
                or (self.ranking.item_type == 'person' and (not self.person_id or self.work_id))):
            raise ValidationError('The entry must match the ranking item type.')
        if self.ranking.presentation != 'ranked' and self.source_rank is not None:
            raise ValidationError({'source_rank': 'Collections and reading sequences have no merit rank.'})
        if self.work_id and self.ranking.scope.get('forms') and self.work.form not in self.ranking.scope['forms']:
            raise ValidationError({'work': 'The work form is outside this ranking scope.'})
        if not isinstance(self.groupings, list):
            raise ValidationError({'groupings': 'Grouped placements must be a list.'})
        seen = set()
        for grouping in self.groupings:
            if (not isinstance(grouping, dict) or not isinstance(grouping.get('country'), str)
                    or not grouping['country'].strip() or len(grouping['country']) > 100
                    or type(grouping.get('local_rank')) is not int
                    or grouping['local_rank'] not in {1, 2, 3}):
                raise ValidationError({'groupings': 'Each grouped placement needs a country and local rank from 1 to 3.'})
            key = (grouping['country'].casefold(), grouping['local_rank'])
            if key in seen:
                raise ValidationError({'groupings': 'Grouped placements cannot repeat a country and local rank.'})
            seen.add(key)
        from backend.domain.scoring import validate_scores
        try:
            validate_scores(self.assessments, [c['id'] for c in self.ranking.criteria], 10)
        except (ValueError, KeyError, TypeError) as error:
            raise ValidationError({'assessments': str(error)}) from error


class RankingRevision(models.Model):
    ranking = models.ForeignKey(Ranking, on_delete=models.CASCADE, related_name='revisions')
    number = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    note = models.CharField(max_length=300)
    snapshot = models.JSONField(default=dict)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['ranking', 'number'], name='unique_ranking_revision')]


class ResearchSource(Timestamped):
    is_archived = models.BooleanField(default=False)
    ranking = models.ForeignKey(Ranking, on_delete=models.CASCADE, related_name='sources')
    source_id = models.CharField(max_length=80)
    title = models.CharField(max_length=500)
    url = models.URLField(max_length=1000)
    family = models.CharField(max_length=80)
    publisher = models.CharField(max_length=240, blank=True)
    evidence = models.TextField(blank=True)
    limitations = models.TextField(blank=True)
    consulted_on = models.DateField(null=True, blank=True)
    eligible = models.BooleanField(default=False)
    underlying_source_id = models.CharField(max_length=200)
    metadata = models.JSONField(default=dict, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['ranking', 'underlying_source_id'], name='unique_target_source'),
                       models.UniqueConstraint(fields=['ranking', 'source_id'], name='unique_target_source_id'),
                       models.CheckConstraint(condition=Q(eligible=False) | (Q(consulted_on__isnull=False) & ~Q(evidence='')),
                                              name='eligible_source_has_consulted_evidence')]

    def clean(self):
        super().clean()
        if self.eligible and (not self.consulted_on or not self.evidence.strip()):
            raise ValidationError('An eligible source needs a consultation date and relevant evidence for this ranking.')


class RankingPreference(Timestamped):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    ranking = models.ForeignKey(Ranking, on_delete=models.CASCADE, related_name='preferences')
    bookmarked = models.BooleanField(default=False)
    refresh_interval_days = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(3650)])
    refresh_requested_at = models.DateTimeField(null=True, blank=True)
    weights = models.JSONField(default=dict, blank=True)
    overrides = models.JSONField(default=dict, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'ranking'], name='unique_ranking_preference')]


class LibraryItem(Timestamped):
    reading_basis = models.JSONField(default=dict, blank=True)
    shelves = models.JSONField(default=list, blank=True)
    personal_tags = models.JSONField(default=list, blank=True)
    read_next_position = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    started_on = models.DateField(null=True, blank=True)
    finished_on = models.DateField(null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    work = models.ForeignKey(Work, on_delete=models.CASCADE)
    edition = models.ForeignKey(Edition, null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=20, default='want_to_read', choices=[(v, v) for v in ['want_to_read', 'reading', 'paused', 'finished', 'abandoned']])
    current_page = models.PositiveIntegerField(default=0)
    rating = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(10)])
    notes = models.TextField(blank=True)
    def save(self, *args, **kwargs):
        if not self.reading_basis:
            from .reading_basis import capture_edition
            self.reading_basis = capture_edition(self.edition or self.work.default_edition)
            if kwargs.get('update_fields') is not None:
                kwargs['update_fields'] = set(kwargs['update_fields']) | {'reading_basis'}
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-updated_at']
        constraints = [models.UniqueConstraint(fields=['user', 'work'], name='unique_library_work'),
                       models.CheckConstraint(condition=Q(rating__isnull=True) | Q(rating__gte=1, rating__lte=10),
                                              name='library_rating_1_to_10')]


class ReadingGoal(Timestamped):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    year = models.PositiveIntegerField(validators=[MinValueValidator(1900), MaxValueValidator(2200)])
    books = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    pages = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'year'], name='unique_reading_goal_year')]


class AuthRateLimit(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)


class ReadingAttempt(Timestamped):
    reading_basis = models.JSONField(default=dict, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    work = models.ForeignKey(Work, on_delete=models.PROTECT)
    edition = models.ForeignKey(Edition, null=True, blank=True, on_delete=models.PROTECT)
    status = models.CharField(max_length=20)
    current_page = models.PositiveIntegerField(default=0)
    rating = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(10)])
    notes = models.TextField(blank=True)
    started_on = models.DateField(null=True, blank=True)
    finished_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [models.CheckConstraint(condition=Q(rating__isnull=True) | Q(rating__gte=1, rating__lte=10), name='attempt_rating_range')]


class PlanItem(Timestamped):
    pages_read = models.PositiveIntegerField(null=True, blank=True, default=None)
    carried_pages = models.PositiveIntegerField(default=0, editable=False)
    reading_basis = models.JSONField(default=dict, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    work = models.ForeignKey(Work, on_delete=models.CASCADE)
    month = models.DateField(help_text='First day of the month')
    position = models.PositiveIntegerField(default=1)
    pages = models.PositiveIntegerField(null=True, blank=True)
    locked = models.BooleanField(default=False)
    def save(self, *args, **kwargs):
        if not self.reading_basis:
            from .reading_basis import capture_plan
            self.reading_basis = capture_plan(self.work, self.user_id)
            if kwargs.get('update_fields') is not None:
                kwargs['update_fields'] = set(kwargs['update_fields']) | {'reading_basis'}
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['month', 'position', 'id']
        constraints = [models.UniqueConstraint(fields=['user', 'work', 'month'], name='unique_plan_work_month'),
                       models.CheckConstraint(condition=Q(month__day=1), name='plan_month_first_day'),
                       models.CheckConstraint(condition=Q(position__gte=1), name='plan_position_positive'),
                       models.CheckConstraint(condition=Q(pages__isnull=True) | Q(pages__gte=1), name='plan_pages_positive'),
                       models.CheckConstraint(condition=Q(carried_pages=0) | Q(pages__isnull=False, pages__gte=F('carried_pages')), name='plan_carry_within_pages'),
                       models.CheckConstraint(condition=Q(pages_read__isnull=True) | Q(pages__isnull=False, pages_read__lte=F('pages') - F('carried_pages')), name='plan_read_within_pages')]


class ReadingAdjustment(models.Model):
    """Edition/progress adjustments are not completed reading attempts."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    work = models.ForeignKey(Work, on_delete=models.PROTECT)
    library_item = models.ForeignKey(LibraryItem, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    method = models.CharField(max_length=30)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)


class SavedDiscoveryFilter(Timestamped):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='saved_discovery_filters')
    name = models.CharField(max_length=100)
    filters = models.JSONField(default=dict)

    class Meta:
        ordering = ['name', 'id']
        constraints = [models.UniqueConstraint(fields=['user', 'name'], name='unique_user_discovery_filter')]


class PlanCarryover(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    source_plan = models.ForeignKey(PlanItem, null=True, on_delete=models.SET_NULL, related_name='carryovers_out')
    target_plan = models.ForeignKey(PlanItem, null=True, on_delete=models.SET_NULL, related_name='carryovers_in')
    work = models.ForeignKey(Work, on_delete=models.PROTECT)
    source_month = models.DateField()
    target_month = models.DateField()
    pages = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    reading_basis = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class CatalogReviewDecision(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    batch_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    entity_type = models.CharField(max_length=10)
    entity_id = models.PositiveIntegerField()
    issue = models.CharField(max_length=40)
    fingerprint = models.CharField(max_length=64)
    action = models.CharField(max_length=24)
    note = models.TextField(blank=True)
    evidence_url = models.URLField(max_length=1000, blank=True)
    deferred_until = models.DateField(null=True, blank=True)
    snapshot = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['entity_type', 'entity_id', 'issue', 'created_at'], name='catalog_review_entity_idx')]


class RecommendationFeedback(Timestamped):
    """Owned suggestion signals; they never change merit scores or list order."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='recommendation_feedback')
    work = models.ForeignKey(Work, null=True, blank=True, on_delete=models.PROTECT)
    saved_filter = models.ForeignKey(SavedDiscoveryFilter, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=24, choices=[(value, value) for value in (
        'preferences', 'neutral', 'more_like', 'not_interested', 'later')])
    details = models.JSONField(default=dict, blank=True)
    deferred_until = models.DateField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'work'], name='unique_recommendation_work_feedback'),
            models.UniqueConstraint(fields=['user'], condition=Q(work__isnull=True), name='unique_recommendation_preferences'),
            models.CheckConstraint(condition=(Q(work__isnull=True, action='preferences') | Q(work__isnull=False, saved_filter__isnull=True, action__in=['neutral', 'more_like', 'not_interested', 'later'])), name='recommendation_feedback_target'),
            models.CheckConstraint(condition=(Q(action='later', deferred_until__isnull=False) | (~Q(action='later') & Q(deferred_until__isnull=True))), name='recommendation_deferral_consistent'),
        ]
        indexes = [models.Index(fields=['user', 'action'], name='recommendation_user_action')]


class ReadingCalendar(Timestamped):
    """Private temporary exceptions; baseline reading targets and plans stay intact."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reading_calendar')
    pauses = models.JSONField(default=list, blank=True)
    month_targets = models.JSONField(default=list, blank=True)
    revision = models.PositiveIntegerField(default=1)
