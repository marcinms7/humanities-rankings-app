"""Previewed edition transitions, separate from completion/reread history."""
from django.core import signing
from rest_framework import serializers
from rest_framework.exceptions import APIException
from .models import Edition, PlanItem, ReadingAdjustment
from .reading_basis import capture_edition, comparable


class EditionConflict(APIException):
    status_code = 409
    default_detail = 'The reading record or edition changed. Preview the edition change again.'


class EditionChangeCommand(serializers.Serializer):
    edition = serializers.IntegerField(min_value=1)
    mode = serializers.ChoiceField(choices=['manual', 'reset', 'proportional', 'keep'])
    page = serializers.IntegerField(min_value=0, required=False)
    apply = serializers.BooleanField(default=False)
    token = serializers.CharField(required=False, max_length=8000)


def transition(item, values, request):
    from .serializers import LibrarySerializer
    edition = Edition.objects.select_for_update().filter(pk=values['edition'], work=item.work, is_archived=False).first()
    if edition is None:
        raise serializers.ValidationError('Choose an active edition of this work.')
    before = item.reading_basis or capture_edition(item.edition or item.work.default_edition)
    after = capture_edition(edition)
    mode = values['mode']
    if mode == 'manual':
        if 'page' not in values:
            raise serializers.ValidationError({'page': 'Enter your page in the new edition.'})
        page = values['page']
    elif mode == 'reset':
        page = 0
    elif mode == 'keep':
        page = item.current_page
    else:
        if not before.get('pages') or not after.get('pages'):
            raise serializers.ValidationError('Percentage mapping needs both page counts. Enter a page or reset instead.')
        if before.get('abridged') != after.get('abridged'):
            raise serializers.ValidationError('Abridgement changed. Enter a page using a chapter/passage reference instead.')
        page = round(item.current_page / before['pages'] * after['pages'])
    if after.get('pages') is not None and page > after['pages']:
        raise serializers.ValidationError({'page': 'Progress exceeds the new edition length. Enter a page or reset.'})
    proof = {'user': request.user.pk, 'item': item.pk, 'updated': item.updated_at.isoformat(),
             'before': comparable(before), 'old_page': item.current_page, 'after': comparable(after),
             'mode': mode, 'page': page}
    if values['apply']:
        try:
            expected = signing.loads(values.get('token', ''), salt='edition-change', max_age=1800)
        except signing.BadSignature:
            raise EditionConflict()
        if expected != proof:
            raise EditionConflict()
        serializer = LibrarySerializer(item, data={'edition': edition.pk, 'current_page': page}, partial=True,
                                       context={'request': request, 'edition_transition': True})
        serializer.is_valid(raise_exception=True)
        ReadingAdjustment.objects.create(user=request.user, work=item.work, library_item=item, method=mode,
            before={'reading_basis': before, 'current_page': item.current_page},
            after={'reading_basis': after, 'current_page': page})
        serializer.save(reading_basis=after)
        return {'applied': True, 'item': serializer.data}
    return {'applied': False, 'before': before, 'after': after, 'old_page': item.current_page, 'page': page,
            'plan_items': PlanItem.objects.filter(user=request.user, work=item.work).count(),
            'token': signing.dumps(proof, salt='edition-change', compress=True),
            'note': 'Percentage mapping is approximate; translations and pagination may differ. '
                    'Reading status, completed attempts and saved physical allocations stay unchanged.'}
