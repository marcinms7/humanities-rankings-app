"""Version-checked edits and authenticated, transactional retry receipts."""
from collections.abc import Mapping
from functools import wraps
from hashlib import sha256
import json
import re

from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response

from .models import MutationReceipt

SAFE = {'GET', 'HEAD', 'OPTIONS'}


def edit_version(instance):
    if instance._meta.model_name in {'libraryitem', 'planitem'}:
        # Summary rows intentionally defer notes; hashing them would trigger one
        # extra query per row. Owned edits always advance their saved timestamp.
        return sha256(f'{instance._meta.label}:{instance.pk}:{instance.updated_at.isoformat()}'.encode()).hexdigest()
    values = {field.attname: getattr(instance, field.attname) for field in instance._meta.concrete_fields}
    for key, value in list(values.items()):
        if hasattr(value, 'name'):
            values[key] = value.name
    if instance._meta.model_name == 'work':
        values['authors'] = sorted(row.pk for row in instance.authors.all())
        values['tags'] = sorted(row.pk for row in instance.tags.all())
        if instance.default_edition:
            values['edition'] = edit_version(instance.default_edition)
    return sha256(json.dumps(values, cls=DjangoJSONEncoder, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class EditConflict(APIException):
    status_code = 409

    def __init__(self, current):
        # Keep typed JSON values; APIException normally converts every leaf to text.
        self.detail = {'detail': 'This record changed after you opened it. Compare the saved values before trying again.',
                       'code': 'edit_conflict', 'current': current}


def require_current(request, instance, serializer):
    if not isinstance(request.data, Mapping):
        raise ValidationError('Use an object containing the fields to change.')
    expected = request.headers.get('If-Match') or request.data.get('expected_version')
    if expected is None:
        return  # Older API clients remain supported; every current editor sends its version.
    if not isinstance(expected, str) or not re.fullmatch(r'[a-f0-9]{64}', expected.strip('"')):
        raise ValidationError({'expected_version': 'Use the version returned with this record.'})
    if expected.strip('"') != edit_version(instance):
        raise EditConflict(serializer(instance, context={'request': request}).data)


class _Replay(Exception):
    def __init__(self, receipt):
        self.receipt = receipt


def _value(value):
    if hasattr(value, 'chunks'):
        position = value.tell()
        value.seek(0)
        digest = sha256()
        for chunk in value.chunks():
            digest.update(chunk)
        value.seek(position)
        return {'file': value.name, 'sha256': digest.hexdigest(), 'size': value.size}
    return value


def _begin(request):
    key = request.headers.get('Idempotency-Key')
    if request.method in SAFE or not key or not request.user.is_authenticated:
        return None
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', key):
        raise ValidationError('Use a unique 16–128 character request key.')
    # All application mutations use this same account lock order.
    get_user_model().objects.select_for_update().get(pk=request.user.pk)
    data = ({name: [_value(value) for value in values] for name, values in request.data.lists()}
            if hasattr(request.data, 'lists') else request.data)
    # A changed precondition is a different command even when the body matches.
    payload = [request.method, request.path, sorted(request.query_params.lists()),
               request.headers.get('If-Match'), data]
    digest = sha256(json.dumps(payload, cls=DjangoJSONEncoder, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    receipt = MutationReceipt.objects.filter(user=request.user, key=key).first()
    if receipt:
        if receipt.request_hash != digest:
            raise ValidationError('This request key belongs to a different change. Submit the corrected change with a new key.')
        raise _Replay(receipt)
    return key, digest


def _replayed(receipt):
    response = Response(receipt.response, status=receipt.status_code)
    response['Idempotency-Replayed'] = 'true'
    response['Cache-Control'] = 'private, no-store'
    return response


def _finish(request, started, response):
    if started and 200 <= response.status_code < 300 and hasattr(response, 'data'):
        key, digest = started
        # Freeze renderer values while holding the same transaction as the write.
        payload = json.loads(json.dumps(response.data, cls=DjangoJSONEncoder))
        MutationReceipt.objects.create(user=request.user, key=key, request_hash=digest,
                                       status_code=response.status_code, response=payload)
        response['Idempotency-Replayed'] = 'false'
        response['Cache-Control'] = 'private, no-store'
    return response


def mutation_guard(view):
    """Place below api_view/permission decorators, so DRF authenticates first."""
    @wraps(view)
    def guarded(request, *args, **kwargs):
        if request.method in SAFE:
            return view(request, *args, **kwargs)
        with transaction.atomic():
            try:
                started = _begin(request)
            except _Replay as replay:
                return _replayed(replay.receipt)
            response = view(request, *args, **kwargs)
            if response.status_code >= 400:
                transaction.set_rollback(True)
                return response
            return _finish(request, started, response)
    return guarded


class MutationGuardMixin:
    """DRF authentication/permission checks precede receipt lookup and replay."""
    def dispatch(self, request, *args, **kwargs):
        if request.method in SAFE:
            return super().dispatch(request, *args, **kwargs)
        with transaction.atomic():
            response = super().dispatch(request, *args, **kwargs)
            if response.status_code >= 400:
                transaction.set_rollback(True)
                return response
            return _finish(self.request, getattr(self, '_mutation_started', None), response)

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self._mutation_started = _begin(request)

    def handle_exception(self, exc):
        if isinstance(exc, _Replay):
            return _replayed(exc.receipt)
        return super().handle_exception(exc)


class VersionedEditMixin:
    def update(self, request, *args, **kwargs):
        with transaction.atomic():
            visible = self.get_object()
            instance = type(visible).objects.select_for_update().get(pk=visible.pk)
            require_current(request, instance, self.get_serializer_class())
            serializer = self.get_serializer(instance, data=request.data, partial=kwargs.pop('partial', False))
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        with transaction.atomic():
            visible = self.get_object()
            instance = type(visible).objects.select_for_update().get(pk=visible.pk)
            require_current(request, instance, self.get_serializer_class())
            self.perform_destroy(instance)
            return Response(status=204)
