"""Explicit contracts for bounded ranking reads and adjacent personal-list moves."""
from rest_framework import serializers

from .models import Person
from .serializers import EntrySerializer, PersonSerializer, WorkCardSerializer


class RankingScoreSerializer(serializers.Serializer):
    entry_id = serializers.IntegerField()
    score = serializers.FloatField(allow_null=True)
    reason = serializers.CharField(allow_null=True)
    contributions = serializers.DictField(child=serializers.FloatField())


class RankingPositionsSerializer(serializers.Serializer):
    standing_rank = serializers.IntegerField(allow_null=True)
    reading_rank = serializers.IntegerField(allow_null=True)
    delta = serializers.IntegerField(allow_null=True)


class RankingMembershipSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    kind = serializers.CharField()
    origin = serializers.CharField()
    presentation = serializers.CharField()
    slug = serializers.CharField()
    position = serializers.IntegerField()
    source_rank = serializers.IntegerField(allow_null=True)


class RankingContextSerializer(serializers.Serializer):
    rating = serializers.IntegerField(allow_null=True)
    status = serializers.CharField(allow_null=True)
    read = serializers.BooleanField()
    lists = RankingMembershipSerializer(many=True)


class RankingFacetsSerializer(serializers.Serializer):
    countries = serializers.ListField(child=serializers.CharField())
    genres = serializers.ListField(child=serializers.CharField())


class RankingComparisonSerializer(serializers.Serializer):
    available = serializers.BooleanField()
    identical = serializers.BooleanField()
    compared = serializers.IntegerField()
    different = serializers.IntegerField()
    unpositioned = serializers.IntegerField()
    status = serializers.CharField()


class RankingPersonCardSerializer(PersonSerializer):
    class Meta:
        model = Person
        fields = ['id', 'name', 'portrait', 'portrait_thumbnail', 'countries']


class RankingBrowseEntrySerializer(EntrySerializer):
    book = WorkCardSerializer(source='work', read_only=True)
    author = RankingPersonCardSerializer(source='person', read_only=True)
    display_position = serializers.IntegerField(allow_null=True, read_only=True)
    explanation = serializers.JSONField(allow_null=True, read_only=True)
    context = RankingContextSerializer(allow_null=True, read_only=True)
    comparison = RankingPositionsSerializer(allow_null=True, read_only=True)
    grouping = serializers.JSONField(allow_null=True, read_only=True)
    score = RankingScoreSerializer(allow_null=True, read_only=True)
    assessments = serializers.DictField(child=serializers.FloatField(), read_only=True)
    can_move_up = serializers.BooleanField(read_only=True)
    can_move_down = serializers.BooleanField(read_only=True)

    class Meta(EntrySerializer.Meta):
        fields = [*EntrySerializer.Meta.fields, 'display_position', 'explanation', 'context', 'comparison',
                  'grouping', 'score', 'can_move_up', 'can_move_down']


class RankingBrowsePageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = RankingBrowseEntrySerializer(many=True)
    revision = serializers.IntegerField()
    grouped = serializers.BooleanField()
    count_unit = serializers.ChoiceField(choices=['entries', 'placements'])
    facets = RankingFacetsSerializer()
    comparison = RankingComparisonSerializer()


class RankingMoveSerializer(serializers.Serializer):
    entry_id = serializers.IntegerField(min_value=1)
    direction = serializers.ChoiceField(choices=[-1, 1])
    expected_revision = serializers.IntegerField(min_value=1)


class RankingMutationSerializer(serializers.Serializer):
    detail = serializers.CharField()
    revision = serializers.IntegerField()


class RankingCandidateSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
