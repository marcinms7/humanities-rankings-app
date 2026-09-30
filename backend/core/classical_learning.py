"""Private learning actions, independent of book completion and ranking scores."""
import json
from .content_cache import read_content
import uuid
from datetime import timedelta
from pathlib import Path
from django.utils import timezone
from rest_framework.exceptions import ValidationError


def learning_content(curriculum):
    atlas = read_content((Path(__file__).parent / 'content/classical_atlas.json'))
    prompts = []
    for m in curriculum['modules']:
        for suffix, question in [('question', m['question']), ('evidence', f'For {m["title"]}, recall one precise passage or example and explain what it supports.'), ('limits', f'What uncertainty, counterargument or alternative interpretation matters in {m["title"]}?')]:
            prompts.append(dict(id=m['id'] + ':' + suffix, module=m['id'], question=question,
                                check=f'Reopen the assigned text and your notes. {m["rationale"]}', refs=m['refs']))
    return dict(revision='learning-v1', atlas=atlas, prompts=prompts)


def validate_learning(data, curriculum):
    from .classical_companion import text_field
    if not isinstance(data, dict) or not isinstance(data.get('action'), str):
        raise ValidationError('Choose a learning action.')
    fields = {'session': {'module', 'reflection', 'passage', 'minutes'},
              'recall': {'prompt', 'answer', 'interval', 'expected_attempts'},
              'essay': {'id', 'expected_revision', 'module', 'title', 'question', 'thesis', 'argument', 'counterargument', 'response', 'conclusion', 'draft', 'sources', 'commonplaces'}}
    action = data['action']
    if action not in fields or set(data) - (fields[action] | {'action'}):
        raise ValidationError('Unknown learning action or field.')
    if action in ('essay', 'session') and data.get('module') not in [m['id'] for m in curriculum['modules']]:
        raise ValidationError('Choose a syllabus module.')
    if action == 'session':
        text_field(data, 'reflection', 10000, True)
        text_field(data, 'passage', 1000, True)
        if type(data.get('minutes')) is not int or not 1 <= data['minutes'] <= 720:
            raise ValidationError('Enter 1–720 minutes actually studied, not estimated book pages.')
    if action == 'recall':
        if data.get('prompt') not in [p['id'] for p in curriculum['learning']['prompts']]:
            raise ValidationError('Unknown recall prompt.')
        text_field(data, 'answer', 10000, True)
        if type(data.get('interval')) is not int or data['interval'] not in (1, 3, 7, 14):
            raise ValidationError('Choose a revisit interval of 1, 3, 7 or 14 days.')
        if type(data.get('expected_attempts')) is not int or data['expected_attempts'] < 0:
            raise ValidationError('Include the last seen attempt count.')
    if action == 'essay':
        if type(data.get('expected_revision')) is not int or data['expected_revision'] < 0:
            raise ValidationError('Include the last seen draft revision.')
        if 'id' in data and (not isinstance(data['id'], str) or len(data['id']) > 40):
            raise ValidationError('Invalid essay ID.')
        for key in ('title', 'question', 'thesis', 'argument', 'counterargument', 'response', 'conclusion', 'draft', 'sources'):
            text_field(data, key, 500 if key == 'title' else 40000 if key == 'draft' else 10000, key in ('title', 'question'))
        refs = data.get('commonplaces', [])
        if not isinstance(refs, list) or len(refs) > 30 or any(not isinstance(k, str) or len(k) > 40 for k in refs) or len(set(refs)) != len(refs):
            raise ValidationError('Choose up to 30 distinct saved commonplaces.')
    return data


def apply_learning(data, state):
    private = state.setdefault('learning', {})
    now = timezone.now()
    action = data['action']
    if action == 'session':
        sessions = private.setdefault('sessions', [])
        if len(sessions) >= 2000:
            raise ValidationError('Study journal has reached 2,000 sessions; export remains available.')
        sessions.append({**{k: data[k] for k in ('module', 'reflection', 'passage', 'minutes')}, 'id': str(uuid.uuid4()), 'saved_at': now.isoformat()})
    elif action == 'recall':
        recall = private.setdefault('recall', {}).setdefault(data['prompt'], {'attempts': []})
        if len(recall['attempts']) != data['expected_attempts']:
            raise ValidationError('A newer recall attempt exists. Reload before saving; your unsaved answer is still in the form.')
        if len(recall['attempts']) >= 500:
            raise ValidationError('This prompt has 500 attempts; history is preserved and exportable.')
        recall['attempts'].append(dict(answer=data['answer'], interval=data['interval'], saved_at=now.isoformat()))
        recall['due'] = (timezone.localdate() + timedelta(days=data['interval'])).isoformat()
    elif action == 'essay':
        essays = private.setdefault('essays', {})
        key = data.get('id') or str(uuid.uuid4())
        existing = essays.get(key)
        if data.get('id') and not existing:
            raise ValidationError('Essay not found in your private study space.')
        if data['expected_revision'] != (existing or {}).get('revision', 0):
            raise ValidationError('A newer essay revision exists. Export/copy your draft and reload before updating it.')
        if not existing and len(essays) >= 100:
            raise ValidationError('You have 100 saved essays. Existing drafts remain editable/exportable.')
        notes = state.get('companion', {}).get('commonplaces', {})
        if any(k not in notes for k in data.get('commonplaces', [])):
            raise ValidationError('A selected commonplace is not in your private notebook.')
        history = (existing or {}).get('history', [])
        if len(history) >= 50:
            raise ValidationError('This essay has 50 preserved revisions. Export it and start a new essay to continue.')
        if existing:
            history.append({k: v for k, v in existing.items() if k != 'history'})
        essays[key] = {**{k: v for k, v in data.items() if k not in ('action', 'id', 'expected_revision')},
                       'revision': data['expected_revision'] + 1, 'saved_at': now.isoformat(), 'history': history,
                       'evidence': [{'id': k, **notes[k]} for k in data.get('commonplaces', [])]}


def learning_summary(curriculum, state):
    from .classical_companion import route_summary
    today = timezone.localdate().isoformat()
    path = state.get('path', 'light')
    complete = [m['id'] for m in curriculum['modules'] if state.get('modules', {}).get(m['id'], {}).get(curriculum['revision'], {}).get(path)]
    route = route_summary(curriculum, state)
    ordered = list(dict.fromkeys(route['modules'] + [m['id'] for m in curriculum['modules']]))
    mid = next((id for id in ordered if id not in complete), None)
    module = next((m for m in curriculum['modules'] if m['id'] == mid), None)
    private = state.get('learning', {})
    recall = private.get('recall', {})
    due = [p['id'] for p in curriculum['learning']['prompts'] if recall.get(p['id'], {}).get('due', '9999') <= today]
    listening = next((p for p in curriculum['companion']['listening'] if mid in p['modules'] and not state.get('companion', {}).get('listening', {}).get(p['id'])), None)
    material = next((p for p in curriculum['companion']['resources'] if mid in p['modules']), None)
    return dict(date=today, date_basis='Server calendar (UTC)', next_module=mid,
                assignment=module[path] if module else None, question=module['question'] if module else None,
                listening=listening, material=material, due=due,
                commonplace_due=[k for k, n in state.get('companion', {}).get('commonplaces', {}).items() if n.get('revisit') and n['revisit'] <= today],
                sessions_today=[s for s in private.get('sessions', []) if s['saved_at'][:10] == today],
                policy='Revisit intervals are reader-selected reminders, not a validated adaptive learning model. Study, recall and listening never mark a book or module complete.')


def essay_text(key, state, curriculum):
    essay = state.get('learning', {}).get('essays', {}).get(key)
    if not essay:
        raise ValidationError('Essay not found in your private study space.')
    works = {w['id']: w['title'] for w in curriculum['companion']['works']}
    lines = [essay['title'], f'Private draft · revision {essay["revision"]}', '']
    for k in ('question', 'thesis', 'argument', 'counterargument', 'response', 'conclusion', 'draft', 'sources'):
        lines += [k.upper(), essay.get(k, ''), '']
    lines += ['SAVED EVIDENCE SNAPSHOTS (not automatically verified citations)']
    for n in essay.get('evidence', []):
        lines += [works.get(n['work'], f'Work #{n["work"]}'), n['reference'], n['translator'], n.get('passage', ''), n['reflection'], '']
    return '\n'.join(lines)
