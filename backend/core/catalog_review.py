"""Staff catalog triage, using saved evidence and explicit, audited decisions.

The queue is derived from live catalog facts. Review decisions never merge
identities, reorder rankings, fetch external content, or rewrite reader data.
"""
from collections import defaultdict
from copy import deepcopy
from .mutations import mutation_guard
from .catalog_cache import cached_catalog
from datetime import date
import hashlib
import json
import uuid

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.core.files.storage import default_storage
from django.core.validators import URLValidator
from django.db import transaction
from django.db.models import Count, F, Q, Window
from django.db.models.functions import RowNumber
from django.utils import timezone
from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response

from .models import CatalogReviewDecision, Edition, LibraryItem, Person, RankingEntry, ResearchSource, Work


class ReviewConflict(APIException):
    status_code = 409
    default_detail = 'The catalog record or its review changed. Refresh the queue and review the current evidence.'


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, cls=DjangoJSONEncoder).encode()).hexdigest()


def _normal(value):
    return ' '.join(value.casefold().split())


def _staged(edition):
    notes = edition['translation_notes'].casefold()
    return edition['is_archived'] and ('candidate' in notes or 'confirmation' in notes or 'bibliographic review' in notes)


def _catalog():
    """Load a compact catalog index; only the requested page gets evidence text.

    A single query per relation avoids a count/source request per queue item.
    No private notes, account identifiers or reading histories are loaded.
    """
    works = {row['id']: row for row in Work.objects.filter(is_archived=False).values(
        'id', 'title', 'form', 'field', 'default_edition_id', 'original_year', 'updated_at')}
    people = {row['id']: row for row in Person.objects.filter(is_archived=False).values(
        'id', 'name', 'countries', 'portrait', 'image_attribution', 'source_url', 'updated_at')}
    authors = defaultdict(list)
    for work_id, person_id, name in Work.authors.through.objects.filter(work_id__in=works).values_list(
            'work_id', 'person_id', 'person__name'):
        authors[work_id].append({'id': person_id, 'name': name})
    editions = {row['id']: row for row in Edition.objects.filter(work_id__in=works).values(
        'id', 'work_id', 'is_archived', 'language', 'translator', 'publisher', 'isbn', 'pages',
        'pages_basis', 'pages_source_url', 'cover', 'cover_basis', 'cover_source_url', 'image_attribution',
        'source_url', 'abridged', 'translation_notes', 'updated_at')}
    saves = dict(LibraryItem.objects.values('work_id').annotate(total=Count('id')).values_list('work_id', 'total'))
    shared_entries = RankingEntry.objects.filter(is_archived=False, ranking__is_archived=False,
                                                 ranking__is_public=True).exclude(ranking__origin='personal')
    appearances = dict(shared_entries.filter(work_id__isnull=False).values('work_id').annotate(
        total=Count('ranking_id', distinct=True)).values_list('work_id', 'total'))
    person_appearances = dict(shared_entries.filter(person_id__isnull=False).values('person_id').annotate(
        total=Count('ranking_id', distinct=True)).values_list('person_id', 'total'))
    latest = {}
    for row in CatalogReviewDecision.objects.annotate(number=Window(
            RowNumber(), partition_by=[F('entity_type'), F('entity_id'), F('issue')],
            order_by=F('id').desc())).filter(number=1).values(
                'id', 'entity_type', 'entity_id', 'issue', 'fingerprint', 'action', 'note',
                'evidence_url', 'deferred_until', 'created_at'):
        latest[f"{row['entity_type']}:{row['entity_id']}:{row['issue']}"] = row
    return works, people, authors, editions, saves, appearances, person_appearances, latest


def review_rows():
    works, people, authors, editions, saves, appearances, person_appearances, latest = _catalog()
    identities, names = defaultdict(list), defaultdict(list)
    person_work_ids = defaultdict(set)
    for work in works.values():
        work['authors'] = sorted(authors[work['id']], key=lambda row: row['id'])
        key = (_normal(work['title']), tuple(sorted(_normal(a['name']) for a in work['authors'])))
        identities[key].append(work['id'])
        for author in work['authors']:
            person_work_ids[author['id']].add(work['id'])
    for person in people.values():
        names[_normal(person['name'])].append(person['id'])
    rows = []

    def add(kind, record, issue, category, reason, snapshot, related=None):
        entity_id = record['id']
        work_id = entity_id if kind == 'work' else record.get('work_id')
        visible_works = person_work_ids[entity_id] if kind == 'person' else {work_id}
        library_saves = sum(saves.get(pk, 0) for pk in visible_works)
        list_appearances = (person_appearances.get(entity_id, 0) if kind == 'person' else 0)
        list_appearances += sum(appearances.get(pk, 0) for pk in visible_works)
        key = f'{kind}:{entity_id}:{issue}'
        fingerprint = _digest(snapshot)
        previous = latest.get(key)
        current = previous if previous and previous['fingerprint'] == fingerprint else None
        action = current['action'] if current else ''
        status = 'active'
        if action == 'defer' and current['deferred_until'] and current['deferred_until'] > timezone.localdate():
            status = 'deferred'
        elif action == 'identity_checked':
            status = 'checked'
        elif action == 'needs_research':
            status = 'needs_research'
        title = record.get('title') or record.get('name') or works[work_id]['title']
        rows.append({'key': key, 'entity_type': kind, 'entity_id': entity_id, 'work_id': work_id,
                     'issue': issue, 'category': category, 'reason': reason, 'title': title,
                     'fingerprint': fingerprint, 'review_version': previous['id'] if previous else 0,
                     'status': status, 'decision': current, 'snapshot': snapshot, 'related': related or [],
                     'library_saves': library_saves, 'list_appearances': list_appearances,
                     'priority': library_saves * 5 + list_appearances,
                     'prioritized': action == 'prioritize'})

    for work in works.values():
        edition = editions.get(work['default_edition_id'])
        snapshot = {**work, 'edition': edition}
        if not edition or not edition['cover']:
            add('work', work, 'missing_cover', 'images', 'The default reading display has no cover.', snapshot)
        elif not edition['image_attribution'].strip():
            add('work', work, 'cover_credit', 'images', 'The default cover has no recorded attribution.', snapshot)
        key = (_normal(work['title']), tuple(sorted(_normal(a['name']) for a in work['authors'])))
        duplicate_ids = [pk for pk in identities[key] if pk != work['id']]
        placeholders = {'unknown', 'unknown author', 'author unknown', 'not recorded', 'various'}
        if not work['authors'] or any(_normal(a['name']) in placeholders for a in work['authors']):
            add('work', work, 'author_identity', 'identity',
                'Author attribution is missing or uses a placeholder; anonymous works can be checked with evidence.', snapshot)
        elif duplicate_ids:
            related = [{'id': pk, 'title': works[pk]['title'], 'entity_type': 'work'} for pk in duplicate_ids]
            add('work', work, 'possible_duplicate', 'identity',
                'Another live record has the same normalized title and author names. This is a review signal, not a merge instruction.',
                {**snapshot, 'related': related}, related)
        if not edition or edition['is_archived']:
            add('work', work, 'missing_edition', 'editions', 'No selectable default edition is recorded.', snapshot)
    for person in people.values():
        if not person['portrait']:
            add('person', person, 'missing_portrait', 'images', 'No portrait is recorded.', person)
        elif not person['image_attribution'].strip():
            add('person', person, 'portrait_credit', 'images', 'The portrait has no recorded attribution.', person)
        duplicate_ids = [pk for pk in names[_normal(person['name'])] if pk != person['id']]
        if duplicate_ids:
            related = [{'id': pk, 'title': people[pk]['name'], 'entity_type': 'person'} for pk in duplicate_ids]
            add('person', person, 'possible_duplicate', 'identity',
                'Another live person has the same normalized name. Check whether these are distinct people.',
                {**person, 'related': related}, related)
    for edition in editions.values():
        snapshot = {**edition, 'work': works[edition['work_id']]}
        if _staged(edition):
            add('edition', edition, 'staged_edition', 'editions',
                'This archived candidate needs publisher/library confirmation of exact work, volume scope and physical pagination.', snapshot)
        elif not edition['is_archived'] and (not edition['pages'] or edition['pages_basis'] in {'unknown', 'estimated_across_editions'}
                                             or not edition['pages_source_url']):
            add('edition', edition, 'uncertain_pages', 'editions',
                'The physical length is missing, estimated, or lacks a saved source. Reading snapshots retain their existing basis.', snapshot)
    return rows


def _evidence(rows):
    work_ids = {r['work_id'] for r in rows if r['work_id']}
    person_ids = {r['entity_id'] for r in rows if r['entity_type'] == 'person'}
    entries = RankingEntry.objects.filter(is_archived=False, ranking__is_archived=False,
                                          ranking__is_public=True).exclude(ranking__origin='personal').filter(
        Q(work_id__in=work_ids) | Q(person_id__in=person_ids)).annotate(number=Window(
            RowNumber(), partition_by=[F('work_id'), F('person_id')], order_by=F('position').asc())).filter(number__lte=3).values(
                'work_id', 'person_id', 'ranking_id', 'ranking__title', 'ranking__source_url',
                'ranking__presentation', 'position', 'source_rank', 'rationale')
    grouped = defaultdict(list)
    for entry in entries:
        grouped[('work', entry['work_id']) if entry['work_id'] else ('person', entry['person_id'])].append({
            'ranking_id': entry['ranking_id'], 'title': entry['ranking__title'], 'url': entry['ranking__source_url'],
            'presentation': entry['ranking__presentation'], 'position': entry['position'], 'source_rank': entry['source_rank'],
            'rationale': entry['rationale'][:1600], 'excerpt_truncated': len(entry['rationale']) > 1600})
    ranking_ids = {e['ranking_id'] for values in grouped.values() for e in values}
    sources = defaultdict(list)
    for source in ResearchSource.objects.filter(ranking_id__in=ranking_ids, is_archived=False).annotate(number=Window(
            RowNumber(), partition_by=F('ranking_id'), order_by=F('id').asc())).filter(number__lte=2).values(
                'ranking_id', 'title', 'url', 'evidence', 'limitations', 'consulted_on'):
        sources[source['ranking_id']].append({**source, 'evidence': source['evidence'][:800],
                                              'limitations': source['limitations'][:400]})
    for row in rows:
        key = ('person', row['entity_id']) if row['entity_type'] == 'person' else ('work', row['work_id'])
        row['evidence'] = [{**entry, 'sources': sources[entry['ranking_id']]} for entry in grouped[key]]
        snapshot = row['snapshot']
        media_record = snapshot if row['entity_type'] in {'edition', 'person'} else snapshot.get('edition') or {}
        image_name = media_record.get('portrait') or media_record.get('cover')
        row['image_url'] = default_storage.url(image_name) if image_name else ''


def _positive(value, name):
    try:
        if isinstance(value, bool) or str(int(value)) != str(value) or int(value) < 1:
            raise ValueError()
        return int(value)
    except (TypeError, ValueError, OverflowError):
        raise ValidationError({name: 'Use a positive integer.'})


@api_view(['GET'])
@permission_classes([permissions.IsAdminUser])
def catalog_review_queue(request):
    category = request.query_params.get('category', 'all')
    status = request.query_params.get('status', 'active')
    if category not in {'all', 'identity', 'images', 'editions'} or status not in {'active', 'deferred', 'checked', 'needs_research', 'all'}:
        raise ValidationError('Unknown review filter.')
    page = _positive(request.query_params.get('page', '1'), 'page')
    search = request.query_params.get('search', '').strip().casefold()
    rows = cached_catalog('catalog-review-v1', review_rows, ttl=20, copy=False)
    totals = {key: sum(1 for row in rows if row['category'] == key and row['status'] in {'active', 'needs_research'})
              for key in ('identity', 'images', 'editions')}
    rows = [row for row in rows if (category == 'all' or row['category'] == category)
            and (status == 'all' or row['status'] == status or (status == 'active' and row['status'] == 'needs_research'))
            and (not search or search in row['title'].casefold())]
    rows.sort(key=lambda row: (-int(row['prioritized']), -row['priority'], row['title'].casefold(), row['key']))
    count = len(rows)
    selected = deepcopy(rows[(page - 1) * 24:page * 24])
    _evidence(selected)
    return Response({'count': count, 'page': page, 'page_size': 24, 'results': selected, 'totals': totals,
                     'priority_basis': 'Library saves × 5 + appearances in public shared lists; manually prioritized items first. These are usage proxies, not page-view counts.'})


def _text(payload, field, minimum=0, maximum=3000):
    value = payload.get(field, '')
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        raise ValidationError({field: f'Use {minimum}–{maximum} characters.'})
    return value.strip()


def _url(payload, required=False):
    value = _text(payload, 'evidence_url', 1 if required else 0, 1000)
    if value:
        try:
            URLValidator(schemes=['http', 'https'])(value)
        except DjangoValidationError:
            raise ValidationError({'evidence_url': 'Use a full HTTP or HTTPS evidence URL.'})
    return value


def _selected(payload):
    if not isinstance(payload, dict):
        raise ValidationError('Send a JSON object.')
    selections = payload.get('items')
    if not isinstance(selections, list) or not 1 <= len(selections) <= 24:
        raise ValidationError('Select between 1 and 24 issues.')
    keys = set()
    lock_ids = defaultdict(set)
    for item in selections:
        if not isinstance(item, dict) or not isinstance(item.get('key'), str):
            raise ValidationError('Every selection needs a queue key and review fingerprint.')
        parts = item['key'].split(':')
        if len(parts) != 3 or parts[0] not in {'work', 'person', 'edition'} or item['key'] in keys:
            raise ValidationError('Use distinct queue issue keys.')
        keys.add(item['key'])
        lock_ids[parts[0]].add(_positive(parts[1], 'entity_id'))
    # Lock the work and its edition/attribution dependencies before fingerprinting.
    # This also prevents approving a candidate while its canonical work changes.
    lock_ids['work'].update(Edition.objects.filter(pk__in=lock_ids['edition']).values_list('work_id', flat=True))
    lock_ids['person'].update(Work.authors.through.objects.filter(work_id__in=lock_ids['work']).values_list('person_id', flat=True))
    lock_ids['edition'].update(Work.objects.filter(pk__in=lock_ids['work'], default_edition_id__isnull=False).values_list('default_edition_id', flat=True))
    # A stable lock order serializes simultaneous staff decisions for each record.
    for kind, model in [('work', Work), ('person', Person), ('edition', Edition)]:
        list(model.objects.select_for_update().filter(pk__in=lock_ids[kind]).order_by('pk').values_list('pk', flat=True))
    current = {row['key']: row for row in review_rows() if row['key'] in keys}
    result = []
    for item in selections:
        row = current.get(item['key'])
        if not row or row['fingerprint'] != item.get('fingerprint') or row['review_version'] != item.get('review_version'):
            raise ReviewConflict()
        result.append(row)
    return result


def _receipt(decision):
    return {'id': decision.pk, 'batch_id': str(decision.batch_id), 'entity_type': decision.entity_type,
            'entity_id': decision.entity_id, 'issue': decision.issue, 'action': decision.action,
            'note': decision.note, 'evidence_url': decision.evidence_url,
            'deferred_until': decision.deferred_until, 'created_at': decision.created_at,
            'title': decision.snapshot.get('title', '')}


def _record(user, row, batch_id, action, note, evidence_url='', deferred_until=None, extra=None):
    return CatalogReviewDecision.objects.create(actor=user, batch_id=batch_id, entity_type=row['entity_type'],
        entity_id=row['entity_id'], issue=row['issue'], fingerprint=row['fingerprint'], action=action,
        note=note, evidence_url=evidence_url, deferred_until=deferred_until,
        snapshot={'title': row['title'], 'reason': row['reason'],
                  'record': json.loads(json.dumps(row['snapshot'], cls=DjangoJSONEncoder)), **(extra or {})})


@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
@mutation_guard
def catalog_review_batch(request):
    if not isinstance(request.data, dict):
        raise ValidationError('Send a JSON object.')
    action = request.data.get('action')
    if action not in {'needs_research', 'prioritize', 'defer', 'reopen', 'identity_checked'}:
        raise ValidationError('Choose a supported review decision.')
    note = _text(request.data, 'note', 20 if action == 'identity_checked' else 3)
    evidence_url = _url(request.data, required=action == 'identity_checked')
    deferred_until = None
    if action == 'defer':
        try:
            deferred_until = date.fromisoformat(request.data.get('deferred_until', ''))
            if not 1 <= (deferred_until - timezone.localdate()).days <= 366:
                raise ValueError()
        except (TypeError, ValueError):
            raise ValidationError({'deferred_until': 'Choose a date within the next year.'})
    with transaction.atomic():
        rows = _selected(request.data)
        if action == 'identity_checked' and any(row['category'] != 'identity' for row in rows):
            raise ValidationError('Only identity signals can be marked checked. Missing images or uncertain editions need metadata fixes.')
        if action == 'identity_checked' and request.data.get('identity_confirmed') is not True:
            raise ValidationError('Confirm that the saved identities were checked against the supplied source.')
        batch_id = uuid.uuid4()
        receipts = [_receipt(_record(request.user, row, batch_id, action, note, evidence_url, deferred_until)) for row in rows]
    return Response({'batch_id': str(batch_id), 'count': len(receipts), 'receipts': receipts})


@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
@mutation_guard
def catalog_review_edition(request):
    if not isinstance(request.data, dict):
        raise ValidationError('Send a JSON object.')
    evidence_url = _url(request.data, required=True)
    note = _text(request.data, 'note', 30)
    if any(request.data.get(field) is not True for field in ('identity_confirmed', 'scope_confirmed', 'pagination_confirmed')):
        raise ValidationError('Confirm the exact identity, complete volume scope and physical page count against the evidence.')
    with transaction.atomic():
        rows = _selected(request.data)
        if len(rows) != 1 or rows[0]['issue'] != 'staged_edition':
            raise ValidationError('Review one archived bibliographic candidate at a time.')
        row = rows[0]
        edition = Edition.objects.select_for_update().get(pk=row['entity_id'])
        # Confirmation must repeat the visible record, not silently correct it.
        confirmations = request.data.get('confirmed_metadata')
        expected = {field: getattr(edition, field) for field in ('isbn', 'publisher', 'pages', 'language', 'abridged')}
        if not edition.isbn.strip() or not edition.publisher.strip() or not edition.pages or not edition.language.strip():
            raise ValidationError('This candidate lacks ISBN, publisher, language or page count; correct it in catalog administration before approval.')
        if not isinstance(confirmations, dict) or confirmations != expected or type(confirmations.get('pages')) is not int or type(confirmations.get('abridged')) is not bool:
            raise ValidationError('Repeat the exact ISBN, publisher, language, page count and abridgement status shown in the preview.')
        batch_id = uuid.uuid4()
        # Narrow fields preserve any unrelated background image enrichment.
        edition.is_archived = False
        edition.pages_source_url = evidence_url
        edition.pages_basis = 'manually_recorded'
        edition.translation_notes += f'\n\nStaff bibliographic review ({timezone.localdate().isoformat()}): {note}\nEvidence: {evidence_url}'
        try:
            edition.full_clean()
        except DjangoValidationError as error:
            raise ValidationError(error.message_dict if hasattr(error, 'message_dict') else error.messages)
        edition.save(update_fields=['is_archived', 'pages_source_url', 'pages_basis', 'translation_notes', 'updated_at'])
        decision = _record(request.user, row, batch_id, 'approve_edition', note, evidence_url,
                           extra={'confirmed_metadata': expected, 'approved_edition_id': edition.pk})
    return Response({'receipt': _receipt(decision), 'edition_id': edition.pk,
                     'message': 'Edition is now selectable. Existing default editions, reading progress and plans are preserved.'})


@api_view(['GET'])
@permission_classes([permissions.IsAdminUser])
def catalog_review_history(request):
    page = _positive(request.query_params.get('page', '1'), 'page')
    qs = CatalogReviewDecision.objects.order_by('-id')
    return Response({'count': qs.count(), 'page': page, 'page_size': 24,
                     'results': [_receipt(row) for row in qs[(page - 1) * 24:page * 24]]})
