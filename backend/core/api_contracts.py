"""Explicit response shapes for computed fields and action endpoints.

These schemas are shared by generated TypeScript and boundary validation; JSON
whose structure is intentionally open remains unknown instead of fabricated.
"""
from rest_framework import serializers as s


class EstimateContract(s.Serializer):
    status = s.CharField()
    estimated_hours = s.FloatField(allow_null=True)
    low_hours = s.FloatField(allow_null=True)
    high_hours = s.FloatField(allow_null=True)
    length_basis = s.CharField(allow_null=True)
    load_multiplier = s.FloatField()
    algorithm_version = s.CharField()
    calibrated = s.BooleanField()
    assumptions = s.ListField(child=s.CharField())
    page_count_basis = s.CharField()


class StudyChangeContract(s.Serializer):
    path = s.ListField(child=s.CharField(), min_length=1)
    value = s.JSONField(required=False, allow_null=True)
    remove = s.BooleanField(required=False)


class StudyDeltaContract(s.Serializer):
    updated_at = s.CharField(allow_null=True)
    changes = StudyChangeContract(many=True)
    path = s.ChoiceField(choices=['light', 'rigorous'])
    pace = s.IntegerField()
    completed = s.ListField(child=s.CharField())
    ready = s.ListField(child=s.CharField())
    total_hours = s.FloatField()
    total_weeks = s.IntegerField()
    remaining_hours = s.FloatField()
    route = s.JSONField()
    classical_plans = s.ListField(child=s.JSONField())
    learning_summary = s.JSONField()


class PlannedWorkContract(s.Serializer):
    work = s.IntegerField()
    month = s.DateField()
    pages = s.IntegerField(allow_null=True)
    locked = s.BooleanField()


class UnscheduledContract(s.Serializer):
    work = s.IntegerField()
    reason = s.CharField()


class PlanSuggestionContract(s.Serializer):
    preview_token = s.CharField()
    items = PlannedWorkContract(many=True)
    unscheduled = UnscheduledContract(many=True)
    warnings = s.ListField(child=s.CharField())
    capacity_remaining = s.DictField(child=s.FloatField())


class MonthCapacityContract(s.Serializer):
    month = s.DateField()
    budget = s.FloatField()
    base_budget = s.FloatField()
    paused_days = s.IntegerField()
    available_days = s.IntegerField()
    calendar_days = s.IntegerField()
    month_percent = s.IntegerField()
    calendar_adjusted = s.BooleanField()
    used = s.FloatField()
    physical_pages = s.IntegerField()
    unknown_allocations = s.IntegerField()
    per_reading_day = s.FloatField()
    weekly_equivalent = s.FloatField()
    unit = s.CharField()
    algorithm_version = s.CharField()
    pages_read = s.IntegerField()
    carried_pages = s.IntegerField()
    remaining_pages = s.IntegerField()
    remaining_effort = s.FloatField()
    unrecorded_allocations = s.IntegerField()


class AllocationCapacityContract(s.Serializer):
    budget = s.FloatField()
    used = s.FloatField()
    unit = s.CharField()
    unknown_allocations = s.IntegerField()


class OtherAllocationContract(s.Serializer):
    month = s.DateField()
    pages = s.IntegerField(allow_null=True)
    pages_read = s.IntegerField(allow_null=True)
    remaining_pages = s.IntegerField(allow_null=True)
    locked = s.BooleanField()
    same_reading_basis = s.BooleanField()


class AllocationPreviewContract(s.Serializer):
    applied = s.BooleanField()
    preview_token = s.CharField()
    title = s.CharField()
    month = s.DateField()
    pages = s.IntegerField(allow_null=True)
    effort_pages = s.FloatField(allow_null=True)
    remaining_pages = s.IntegerField(allow_null=True)
    over_capacity = s.FloatField()
    capacity = AllocationCapacityContract()
    warnings = s.ListField(child=s.CharField())
    other_allocations = OtherAllocationContract(many=True)


class EditConflictContract(s.Serializer):
    detail = s.CharField()
    code = s.ChoiceField(choices=['edit_conflict'])
    current = s.DictField(child=s.JSONField())


def computed_fields(serializer):
    from .serializers import EditionSerializer
    fields = {}
    names = {cls.__name__ for cls in type(serializer).__mro__}
    if names & {'WorkSerializer', 'PersonSerializer'}:
        fields['countries'] = s.ListField(child=s.CharField())
    if 'WorkSerializer' in names:
        fields.update(tags=s.ListField(child=s.CharField()), genres=s.ListField(child=s.CharField()),
                      reading_time=EstimateContract())
    if 'EditableSerializer' in names:
        fields['edit_version'] = s.CharField()
    if 'PersonSerializer' in names:
        fields['portrait_thumbnail'] = s.CharField(allow_null=True)
    if 'EditionSerializer' in names:
        fields['cover_thumbnail'] = s.CharField(allow_null=True)
    if 'LibrarySerializer' in names:
        fields.update(selected_edition=EditionSerializer(allow_null=True), reading_time=EstimateContract(),
                      remaining_reading_time=EstimateContract(), shelves=s.ListField(child=s.CharField()),
                      personal_tags=s.ListField(child=s.CharField()), basis_needs_review=s.BooleanField())
    if 'PlanSerializer' in names:
        fields.update(effort_multiplier=s.FloatField(), effort_pages=s.FloatField(allow_null=True),
                      basis_needs_review=s.BooleanField(), has_history=s.BooleanField(), has_incoming_carryover=s.BooleanField())
    return fields


def contract_registry():
    from .catalog_atlas import CatalogAtlasSerializer
    from .published_comparison import PublishedComparisonSerializer
    from .reading_calendar import CalendarStateContract, CalendarPreviewContract, CalendarCommand
    from .study_store import StudyRecordsPageContract
    class StudyHistoryPageContract(StudyRecordsPageContract):
        results = s.ListField(child=s.JSONField())
    from .serializers import (UserSerializer, PersonSerializer, EditionSerializer, WorkSerializer,
                             WorkCardSerializer, LibrarySerializer, LibrarySummarySerializer,
                             PlanSerializer, PlanSummarySerializer)
    from .saved_discovery import SavedDiscoveryFilterSerializer, DiscoveryFiltersSerializer
    from .ranking_contracts import (RankingBrowsePageSerializer, RankingMoveSerializer,
                                    RankingMutationSerializer, RankingCandidateSerializer)
    from .recommendations import (RecommendationBundleSerializer, RecommendationPreferencesSerializer,
        RecommendationFeedbackSerializer, RecommendationFeedbackPageSerializer,
        RecommendationPreferencesCommandSerializer, RecommendationFeedbackCommandSerializer)
    return dict(ApiCatalogAtlas=CatalogAtlasSerializer, ApiPublishedComparison=PublishedComparisonSerializer,
        ApiCalendarState=CalendarStateContract, ApiCalendarPreview=CalendarPreviewContract,
        ApiCalendarCommand=CalendarCommand, ApiUser=UserSerializer, ApiPerson=PersonSerializer, ApiEdition=EditionSerializer,
        ApiWork=WorkSerializer, ApiWorkCard=WorkCardSerializer, ApiLibrary=LibrarySerializer,
        ApiLibrarySummary=LibrarySummarySerializer, ApiPlan=PlanSerializer, ApiPlanSummary=PlanSummarySerializer,
        ApiSavedDiscoveryFilter=SavedDiscoveryFilterSerializer, ApiDiscoveryFilters=DiscoveryFiltersSerializer,
        ApiRankingBrowsePage=RankingBrowsePageSerializer, ApiRankingMove=RankingMoveSerializer,
        ApiRankingMutation=RankingMutationSerializer, ApiRankingCandidate=RankingCandidateSerializer,
        ApiRecommendationBundle=RecommendationBundleSerializer, ApiRecommendationPreferences=RecommendationPreferencesSerializer,
        ApiRecommendationFeedback=RecommendationFeedbackSerializer, ApiRecommendationFeedbackPage=RecommendationFeedbackPageSerializer,
        ApiRecommendationPreferencesCommand=RecommendationPreferencesCommandSerializer,
        ApiRecommendationFeedbackCommand=RecommendationFeedbackCommandSerializer,
        ApiStudyChange=StudyChangeContract, ApiStudyDelta=StudyDeltaContract,
        ApiStudyRecordsPage=StudyRecordsPageContract, ApiStudyHistoryPage=StudyHistoryPageContract,
        ApiPlanSuggestion=PlanSuggestionContract, ApiMonthCapacity=MonthCapacityContract,
        ApiAllocationPreview=AllocationPreviewContract, ApiEditConflict=EditConflictContract)
