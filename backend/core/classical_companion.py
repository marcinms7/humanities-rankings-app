"""Additive private study helpers. No shared catalog or ranking mutations."""
import json
from .content_cache import read_content
import math
import uuid
from datetime import date
from pathlib import Path

from django.conf import settings
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from backend.domain.reading_capacity import effort_per_page
from .models import LibraryItem, PlanCarryover, PlanItem, Ranking, Work
from .plan_previews import PlanPreviewConflict, preview_token, require_preview
from .reading_basis import capture_edition, comparable, length_edition


def companion_content():
    data = read_content((Path(__file__).parent / 'content/classical_companion.json'))
    # Explicit identities from the audited owner import, never title-only matching.
    catalog = read_content(settings.BASE_DIR / 'research/classical-education-guide/owner-chat-catalog-2026-09-14.json')
    ranking = Ranking.objects.filter(slug='classical-education-guide', is_archived=False).first()
    entries = dict(ranking.entries.filter(is_archived=False, work__is_archived=False).values_list('work_id', 'position')) if ranking else {}
    data['ranking_id'] = ranking.pk if ranking else None
    data['works'] = [dict(key=w['key'], id=w['item_id'], title=w['title'], author=w['attribution'],
                          position=entries[w['item_id']], beginner_start=w['beginner_start'],
                          modules=[m for m, keys in data['module_works'].items() if w['key'] in keys])
                     for w in catalog['works'] if w['item_id'] in entries]
    data['works'].sort(key=lambda w: w['position'])
    return data


def route_summary(curriculum, state):
    preferences = state.get('companion', {}).get('preferences', {})
    route = next((r for r in curriculum['companion']['routes'] if r['id'] == preferences.get('route')), curriculum['companion']['routes'][0])
    experience = preferences.get('experience', 'beginner')
    path = state.get('path', 'light')
    modules = {m['id']: m for m in curriculum['modules']}
    hours = sum(modules[mid][path]['hours'] for mid in route['modules'])
    preparation = list(dict.fromkeys(p for mid in route['modules'] for p in modules[mid]['prerequisites'] if p not in route['modules']))
    return dict(**route, experience=experience, path=path, hours=hours,
                weeks=math.ceil(hours / state.get('pace', 4)), preparation=preparation)


def text_field(data, key, maximum, required=False):
    value = data.get(key, '')
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        raise ValidationError(f'{key}: provide text up to {maximum} characters' + (' (required).' if required else '.'))
    return value.strip()


def valid_date(value, optional=False):
    if optional and value == '':
        return ''
    try:
        result = date.fromisoformat(value)
        if not isinstance(value, str) or result.isoformat() != value or not 1900 <= result.year <= 2200:
            raise ValueError
        return result
    except (ValueError, TypeError):
        raise ValidationError('Use a valid ISO date between 1900 and 2200.')


def validate_update(data, curriculum):
    if not isinstance(data, dict) or not isinstance(data.get('action'), str):
        raise ValidationError('Choose a companion action.')
    action = data['action']
    fields = {
        'preferences': {'route', 'experience'},
        'listen': {'id', 'done'},
        'commonplace': {'id', 'work', 'related', 'reference', 'translator', 'passage', 'reflection', 'revisit'},
        'review': {'id', 'revisit'},
        'plan-preview': {'work', 'month', 'pages', 'mode', 'passages'},
        'plan-add': {'work', 'month', 'pages', 'mode', 'passages', 'confirmed', 'preview_token'},
        'plan-progress': {'id', 'done'},
    }
    if action not in fields or set(data) - (fields[action] | {'action'}):
        raise ValidationError('Unknown companion action or field.')
    works = {w['id'] for w in curriculum['companion']['works']}
    if action == 'preferences':
        if data.get('route') not in [r['id'] for r in curriculum['companion']['routes']] or data.get('experience') not in ('beginner', 'some', 'experienced'):
            raise ValidationError('Choose an interest and experience level.')
    if action in ('listen', 'plan-progress') and type(data.get('done')) is not bool:
        raise ValidationError('Completion must be true or false.')
    if action == 'listen' and data.get('id') not in [r['id'] for r in curriculum['companion']['listening']]:
        raise ValidationError('Unknown listening entry.')
    if action in ('commonplace', 'plan-add', 'plan-preview'):
        if type(data.get('work')) is not int or data['work'] not in works:
            raise ValidationError('Choose a work from the classical ranking.')
    if action == 'commonplace':
        for key, limit, required in [('reference', 500, True), ('translator', 500, True), ('passage', 4000, False), ('reflection', 20000, True)]:
            text_field(data, key, limit, required)
        related = data.get('related', [])
        if not isinstance(related, list) or len(related) > 10 or any(type(w) is not int or w not in works for w in related):
            raise ValidationError('Choose up to ten related classical works.')
        valid_date(data.get('revisit', ''), optional=True)
        if 'id' in data and (not isinstance(data['id'], str) or len(data['id']) > 40):
            raise ValidationError('Invalid note ID.')
    if action == 'review':
        if not isinstance(data.get('id'), str):
            raise ValidationError('Choose a saved note.')
        valid_date(data.get('revisit', ''), optional=True)
    if action == 'plan-progress' and type(data.get('id')) is not int:
        raise ValidationError('Choose a plan allocation.')
    if action in ('plan-preview', 'plan-add'):
        month = valid_date(data.get('month'))
        if month.day != 1:
            raise ValidationError('Choose the first day of the month.')
        if type(data.get('pages')) is not int or not 1 <= data['pages'] <= 100000:
            raise ValidationError('Enter 1–100,000 actual pages in your edition, not an estimated whole-book length.')
        if data.get('mode') not in ('whole', 'selections'):
            raise ValidationError('Choose whole work or selections.')
        text_field(data, 'passages', 2000, required=data['mode'] == 'selections')
        if action == 'plan-add' and data.get('confirmed') is not True:
            raise ValidationError('Preview and confirm this allocation first.')
        if 'preview_token' in data and (not isinstance(data['preview_token'], str) or len(data['preview_token']) > 8000):
            raise ValidationError('Supply the allocation preview token.')
    return data


def plan_preview(data, user):
    work = Work.objects.filter(pk=data['work'], is_archived=False).first()
    if not work:
        raise ValidationError('This work is no longer available.')
    if PlanItem.objects.filter(user=user, work=work, month=data['month']).exists():
        if data['action'] == 'plan-add':
            raise PlanPreviewConflict()
        raise ValidationError('This book already has an allocation that month. It was left untouched; choose another month or edit it in Reading plan.')
    library = LibraryItem.objects.filter(user=user, work=work).select_related('edition').first()
    edition = length_edition(library) if library else work.default_edition
    if edition and edition.pages and data['pages'] > edition.pages:
        raise ValidationError('The allocation exceeds the recorded edition length. Correct/select your edition on the book page first.')
    multiplier = effort_per_page(work, edition, user.difficulty_aware_planning)
    from .reading_workflow import capacity_summary
    from datetime import date
    month = date.fromisoformat(data['month']) if isinstance(data['month'], str) else data['month']
    capacity = capacity_summary(user, month, list(PlanItem.objects.filter(user=user, month=month).select_related('work__default_edition')))
    result = dict(capacity=capacity, over_capacity=max(0, round(capacity['used'] + data['pages'] * multiplier - capacity['budget'], 2)), title=work.title, month=data['month'], pages=data['pages'], mode=data['mode'],
                passages=data.get('passages', ''), effort_pages=round(data['pages'] * multiplier, 2),
                adds_to_library=library is None, locked=True,
                note='Appends one locked allocation; existing plans, editions and reading status stay unchanged. Effort uses the existing provisional planner policy. Listening is not counted as reading.')
    state = {'work': work.pk, 'preview': result,
             'basis': comparable(library.reading_basis if library and library.reading_basis else capture_edition(edition)),
             'effort_multiplier': effort_per_page(work, edition),
             'difficulty_aware_planning': user.difficulty_aware_planning,
             'library': {'id': library.pk, 'updated_at': library.updated_at, 'status': library.status,
                         'current_page': library.current_page} if library else None,
             'plans': list(PlanItem.objects.filter(user=user, month=data['month']).order_by('pk').values(
                 'pk', 'work_id', 'month', 'position', 'pages', 'pages_read', 'carried_pages',
                 'locked', 'reading_basis', 'updated_at')),
             'carryovers': list(PlanCarryover.objects.filter(user=user, target_month=data['month']).order_by('pk').values(
                 'pk', 'source_plan_id', 'target_plan_id', 'pages', 'created_at'))}
    if data['action'] == 'plan-add':
        require_preview(data.get('preview_token'), user, 'classical-plan', state)
    result['preview_token'] = preview_token(user, 'classical-plan', state)
    return result


def apply_update(data, curriculum, state, user):
    """Called only inside the profile transaction/lock; exceptions roll back all writes."""
    action = data['action']
    private = state.setdefault('companion', {})
    if action == 'preferences':
        private['preferences'] = {key: data[key] for key in ('route', 'experience')}
        if data['experience'] == 'beginner':
            state['path'] = 'light'  # Select the recommended assignments; never erase either path's progress.
    elif action == 'listen':
        private.setdefault('listening', {})[data['id']] = data['done']
    elif action == 'commonplace':
        notes = private.setdefault('commonplaces', {})
        key = data.get('id') or str(uuid.uuid4())
        if data.get('id') and key not in notes:
            raise ValidationError('Saved note not found in your account.')
        if not data.get('id') and len(notes) >= 1000:
            raise ValidationError('Your commonplace book has reached 1,000 entries. Existing notes can still be edited/exported.')
        notes[key] = {**notes.get(key, {}), **{k: v for k, v in data.items() if k not in ('action', 'id')}, 'updated_at': timezone.now().isoformat()}
    elif action == 'review':
        note = private.get('commonplaces', {}).get(data['id'])
        if note is None:
            raise ValidationError('Saved note not found in your account.')
        note.update(reviewed_on=timezone.localdate().isoformat(), revisit=data.get('revisit', ''))
    elif action == 'plan-add':
        plan_preview(data, user)  # Recheck conflicts and edition length at save time.
        LibraryItem.objects.get_or_create(user=user, work_id=data['work'])
        position = (PlanItem.objects.filter(user=user, month=data['month']).aggregate(n=Max('position'))['n'] or 0) + 1
        plan = PlanItem.objects.create(user=user, work_id=data['work'], month=data['month'], pages=data['pages'], position=position, locked=True)
        private.setdefault('plans', {})[str(plan.pk)] = dict(work_id=data['work'], mode=data['mode'], passages=data.get('passages', ''), done=False)
    elif action == 'plan-progress':
        note = private.get('plans', {}).get(str(data['id']))
        if note is None or not PlanItem.objects.filter(pk=data['id'], user=user, work_id=note.get('work_id')).exists():
            raise ValidationError('Classical allocation not found in your account.')
        note['done'] = data['done']


def saved_plans(state, user):
    metadata = state.get('companion', {}).get('plans', {})
    return [dict(id=p.pk, work=p.work_id, title=p.work.title, month=p.month.isoformat(), pages=p.pages,
                 pages_read=p.pages_read, carried_pages=p.carried_pages, locked=p.locked, **metadata[str(p.pk)])
            for p in PlanItem.objects.filter(user=user, pk__in=[int(k) for k in metadata if k.isdigit()]).select_related('work')
            if metadata[str(p.pk)].get('work_id') == p.work_id]
