"""Bind plan confirmation to the proposal and saved state the reader reviewed."""
import hashlib
import json

from django.core import signing
from django.core.serializers.json import DjangoJSONEncoder
from rest_framework.exceptions import APIException


class PlanPreviewConflict(APIException):
    status_code = 409
    default_detail = 'Your library or plan changed, or the preview expired. Preview the plan again before saving.'


def _proof(user, scope, state):
    from .reading_calendar import calendar_state
    state = {'proposal': state, 'calendar': calendar_state(user),
             'rhythm': {key: getattr(user, key) for key in ('reading_target_period', 'pages_per_day',
                 'pages_per_week', 'pages_per_month', 'reading_days_per_week', 'difficulty_aware_planning')}}
    encoded = json.dumps(state, cls=DjangoJSONEncoder, sort_keys=True, separators=(',', ':'))
    return {'user': user.pk, 'scope': scope, 'digest': hashlib.sha256(encoded.encode()).hexdigest()}


def preview_token(user, scope, state):
    return signing.dumps(_proof(user, scope, state), salt='reading-plan-preview', compress=True)


def require_preview(token, user, scope, state):
    if not isinstance(token, str):
        raise PlanPreviewConflict()
    try:
        expected = signing.loads(token, salt='reading-plan-preview', max_age=1800)
    except (signing.BadSignature, ValueError, TypeError):
        raise PlanPreviewConflict()
    if expected != _proof(user, scope, state):
        raise PlanPreviewConflict()
