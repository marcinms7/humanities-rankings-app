"""Private owner syllabus and versioned assignment progress."""
import json
import math
from pathlib import Path
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from .models import ClassicalStudyProfile
from .classical_companion import companion_content, route_summary, validate_update, plan_preview, apply_update, saved_plans
from .classical_learning import learning_content, validate_learning, apply_learning, learning_summary, essay_text
from .classical_reading_desk import desk_content, validate_desk, apply_desk, desk_export


def content():
    curriculum = json.loads((Path(__file__).parent / 'content/classical_education.json').read_text())
    curriculum['tools'] = json.loads((Path(__file__).parent / 'content/classical_study_tools.json').read_text())
    curriculum['companion'] = companion_content()
    curriculum['learning'] = learning_content(curriculum)
    curriculum['desk'] = desk_content()
    curriculum['companion']['glossary'].extend(curriculum['desk']['glossary'])
    curriculum['companion']['sources'].extend(curriculum['desk']['sources'])
    return curriculum


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def syllabus(request):
    owner = get_user_model().objects.order_by('pk').values_list('pk', flat=True).first()
    if request.user.pk != owner:
        raise PermissionDenied('This is the owner’s private study space.')
    curriculum = content()
    if request.method == 'GET' and 'work' in request.query_params:
        work = next((w for w in curriculum['companion']['works'] if str(w['id']) == request.query_params['work']), None)
        if not work:
            raise ValidationError('No classical reading guide for this work.')
        response = Response({'work': work, 'modules': [dict(id=m['id'], title=m['title'], prerequisites=m['prerequisites']) for m in curriculum['modules'] if m['id'] in work['modules']], 'module_titles': {m['id']: m['title'] for m in curriculum['modules']}})
        response['Cache-Control'] = 'private, no-store'
        return response
    if request.method == 'PATCH':
        data = request.data
        if not isinstance(data, dict):
            raise ValidationError('Send a study update.')
        allowed = {'module', 'notes', 'completed', 'path', 'pace', 'activity', 'response', 'done', 'companion', 'learning', 'desk'}
        if set(data) - allowed:
            raise ValidationError('Unknown study field.')
        companion = None
        learning = None
        desk = None
        if 'desk' in data:
            if set(data) != {'desk'}:
                raise ValidationError('Update one study item at a time.')
            desk = validate_desk(data['desk'], curriculum['desk'])
        if 'learning' in data:
            if set(data) != {'learning'}:
                raise ValidationError('Update one study item at a time.')
            learning = validate_learning(data['learning'], curriculum)
        if 'companion' in data:
            if set(data) != {'companion'}:
                raise ValidationError('Update one study item at a time.')
            companion = validate_update(data['companion'], curriculum)
            if companion['action'] == 'plan-preview':
                response = Response({'preview': plan_preview(companion, request.user)})
                response['Cache-Control'] = 'private, no-store'
                return response
        if 'path' in data and data['path'] not in ('light', 'rigorous'):
            raise ValidationError('Choose Lighter or Rigorous.')
        if 'pace' in data and (type(data['pace']) is not int or data['pace'] not in (3, 4, 6, 8)):
            raise ValidationError('Choose 3, 4, 6 or 8 hours per week.')
        module = data.get('module')
        if module is not None and module not in [m['id'] for m in curriculum['modules']]:
            raise ValidationError('Unknown module.')
        if ('notes' in data or 'completed' in data) and not module:
            raise ValidationError('Choose a module.')
        if 'notes' in data and (not isinstance(data['notes'], str) or len(data['notes']) > 20000):
            raise ValidationError('Notes must contain at most 20,000 characters.')
        if 'completed' in data and (type(data['completed']) is not bool or 'path' not in data):
            raise ValidationError('Completion needs a path and a boolean value.')
        activity = data.get('activity')
        activity_ids = [item['id'] for section in ('language', 'exercises', 'gallery') for item in curriculum['tools'][section]]
        if activity is not None and (not isinstance(activity, str) or activity not in activity_ids):
            raise ValidationError('Unknown study activity.')
        if ('response' in data or 'done' in data) and not activity:
            raise ValidationError('Choose a study activity.')
        if activity and module:
            raise ValidationError('Update one study item at a time.')
        if 'response' in data and (not isinstance(data['response'], str) or len(data['response']) > 20000):
            raise ValidationError('Responses must contain at most 20,000 characters.')
        if 'done' in data and type(data['done']) is not bool:
            raise ValidationError('Completion must be true or false.')
        with transaction.atomic():
            profile, _ = ClassicalStudyProfile.objects.get_or_create(user=request.user)
            profile = ClassicalStudyProfile.objects.select_for_update().get(pk=profile.pk)
            state = profile.state
            if companion:
                apply_update(companion, curriculum, state, request.user)
            if learning:
                apply_learning(learning, state)
            if desk:
                apply_desk(desk, state, curriculum['desk'])
            for key in ('path', 'pace'):
                if key in data:
                    state[key] = data[key]
            if module:
                assignment = state.setdefault('modules', {}).setdefault(module, {})
                if 'notes' in data:
                    assignment['notes'] = data['notes']
                if 'completed' in data:
                    assignment.setdefault(curriculum['revision'], {})[data['path']] = data['completed']
            if activity:
                item = state.setdefault('activities', {}).setdefault(curriculum['tools']['revision'], {}).setdefault(activity, {})
                for key in ('response', 'done'):
                    if key in data:
                        item[key] = data[key]
            profile.state = state
            profile.save(update_fields=['state', 'updated_at'])
    profile = ClassicalStudyProfile.objects.filter(user=request.user).first()
    state = profile.state if profile else {}
    path = state.get('path', 'light')
    pace = state.get('pace', 4)
    total = sum(m[path]['hours'] for m in curriculum['modules'])
    completed = [m['id'] for m in curriculum['modules'] if state.get('modules', {}).get(m['id'], {}).get(curriculum['revision'], {}).get(path)]
    ready = [m['id'] for m in curriculum['modules'] if m['id'] not in completed and all(p in completed for p in m['prerequisites'])]
    remaining = sum(m[path]['hours'] for m in curriculum['modules'] if m['id'] not in completed)
    if request.query_params.get('export') == 'desk':
        response = HttpResponse(desk_export(state, curriculum['desk']), content_type='text/plain; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="marginalia-reading-desk.txt"'
    elif request.query_params.get('essay'):
        response = HttpResponse(essay_text(request.query_params['essay'], state, curriculum), content_type='text/plain; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="marginalia-classical-essay.txt"'
    elif request.query_params.get('export') == 'txt':
        report = (settings.BASE_DIR / 'research/incoming/classical-education/2026-09-14-paideia/report.txt').read_text()
        response = HttpResponse(report + '\n\nMARGINALIA RESEARCHED STUDY TOOLS\n' + json.dumps(curriculum['tools'], ensure_ascii=False, indent=2) + '\n\nMARGINALIA CLASSICAL COMPANION\n' + json.dumps(curriculum['companion'], ensure_ascii=False, indent=2) + '\n\nMARGINALIA PRIVATE STUDY STATE\n' + json.dumps(state, ensure_ascii=False, indent=2) + '\n\nCURRENT CLASSICAL PLAN ALLOCATIONS\n' + json.dumps(saved_plans(state, request.user), ensure_ascii=False, indent=2), content_type='text/plain; charset=utf-8')
        response.write('\n\nMARGINALIA LEARNING TOOLS & ATLAS\n' + json.dumps(curriculum['learning'], ensure_ascii=False, indent=2))
        response.write('\n\nMARGINALIA READING DESK\n' + json.dumps(curriculum['desk'], ensure_ascii=False, indent=2))
        response['Content-Disposition'] = 'attachment; filename="marginalia-classical-education.txt"'
    else:
        response = Response({'content': curriculum, 'state': state, 'path': path, 'pace': pace, 'completed': completed, 'ready': ready, 'total_hours': total, 'total_weeks': math.ceil(total / pace), 'remaining_hours': remaining, 'route': route_summary(curriculum, state), 'classical_plans': saved_plans(state, request.user), 'learning_summary': learning_summary(curriculum, state)})
    response['Cache-Control'] = 'private, no-store'
    return response
