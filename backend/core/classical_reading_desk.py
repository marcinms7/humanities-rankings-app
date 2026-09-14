"""Versioned private passage notes and translation exercises in the existing profile."""
import json
from pathlib import Path
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from .classical_companion import text_field


def desk_content():
    return json.loads((Path(__file__).parent / 'content/classical_reading_desk.json').read_text())


def validate_desk(data, content):
    if not isinstance(data, dict) or set(data) - {'action', 'passage', 'translation', 'notes', 'answers', 'expected_revision'}:
        raise ValidationError('Send one valid reading-desk update.')
    if data.get('action') not in ('note', 'exercise'):
        raise ValidationError('Choose a passage note or translation exercise.')
    passage = next((p for p in content['passages'] if p['id'] == data.get('passage')), None)
    if not passage or data.get('translation') not in [t['id'] for t in passage['translations']]:
        raise ValidationError('Choose a known passage and translation.')
    if type(data.get('expected_revision')) is not int or data['expected_revision'] < 0:
        raise ValidationError('Supply the saved revision before editing.')
    normalized = dict(data)
    if data['action'] == 'note':
        if 'answers' in data:
            raise ValidationError('Save notes and exercises separately.')
        normalized['notes'] = text_field(data, 'notes', 20000, required=True)
    else:
        answers = data.get('answers')
        if 'notes' in data or not isinstance(answers, dict) or set(answers) != {p['id'] for p in passage['prompts']}:
            raise ValidationError('Supply an answer for each comparison prompt.')
        normalized['answers'] = {p['id']: text_field(answers, p['id'], 10000, required=True) for p in passage['prompts']}
    return normalized


def apply_desk(data, state, content):
    records = state.setdefault('reading_desk', {}).setdefault(data['action'], {})
    # Notes belong to the named translation; exercises compare both but remember the primary view.
    key = f"{data['passage']}:{data['translation']}" if data['action'] == 'note' else data['passage']
    prior = records.get(key, {})
    if prior.get('revision', 0) != data['expected_revision']:
        raise ValidationError('This passage was edited elsewhere. Reload before saving; your draft has not been overwritten.')
    history = list(prior.get('history', []))
    if len(history) >= 100:
        raise ValidationError('This item has 100 preserved revisions. Export your notes before requesting additional capacity; no history was removed.')
    if prior:
        history.append({k: v for k, v in prior.items() if k != 'history'})
    passage = next(p for p in content['passages'] if p['id'] == data['passage'])
    records[key] = {**{k: v for k, v in data.items() if k not in ('action', 'expected_revision')},
                    'revision': prior.get('revision', 0) + 1, 'updated_at': timezone.now().isoformat(),
                    'history': history, 'content_revision': content['revision'],
                    'reference': passage['reference'], 'title': passage['title']}


def desk_export(state, content):
    lines = ['MARGINALIA — PRIVATE READING DESK', content['rights_note'], '']
    for action, rows in state.get('reading_desk', {}).items():
        for key, row in rows.items():
            lines.extend([action.upper(), row['title'], row['reference'], f"Translation: {row['translation']} · revision {row['revision']}"])
            if action == 'note':
                lines.append(row['notes'])
            else:
                passage = next((p for p in content['passages'] if p['id'] == row['passage']), None)
                for prompt, answer in row['answers'].items():
                    question = next((p['question'] for p in passage['prompts'] if p['id'] == prompt), prompt) if passage else prompt
                    lines.extend([question, answer])
            lines.extend(['Preserved prior revisions:', json.dumps(row.get('history', []), ensure_ascii=False, indent=2), ''])
    lines.extend(['PASSAGES, TRANSLATOR CREDITS & SOURCES', json.dumps(content, ensure_ascii=False, indent=2)])
    return '\n'.join(lines)
