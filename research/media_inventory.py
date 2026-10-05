"""Read-only media inventory: catalog coverage, local files and actionable gaps."""
from collections import Counter
from contextlib import closing
from functools import lru_cache
import json
from pathlib import Path
import sqlite3
import time

from PIL import Image
from research.media_image_quality import placeholder_file


@lru_cache(maxsize=20000)
def _inspect_file(path, size, modified):
    try:
        if placeholder_file(path):
            return 'known_placeholder'
        with Image.open(path) as image:
            if min(image.size) < 1:
                return 'invalid_file'
            image.verify()
        # JPEG verification checks structure but does not decode its pixel
        # stream. A truncated image must not count as a usable saved portrait.
        with Image.open(path) as image:
            image.load()
        return 'ready'
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return 'invalid_file'


def image_state(root, name):
    if not name:
        return 'missing_image'
    root = Path(root).resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root):
        return 'invalid_path'
    try:
        stat = path.stat()
    except OSError:
        return 'missing_file'
    return _inspect_file(str(path), stat.st_size, stat.st_mtime_ns)


def unresolved_reason(providers, health):
    states = {row.get('state') for row in providers.values()}
    statuses = ' '.join(str(row.get('status') or '') for row in providers.values())
    # A known ambiguous identity is actionable even when another source waits.
    if 'identity_review' in states or 'ambiguous' in statuses:
        return 'identity_review'
    blocked = {name for name, row in providers.items()
               if row.get('state') == 'provider_wait' or (
                   health.get(name, {}).get('status') in {'cooldown', 'credential_required', 'worker_failed'}
                   and row.get('state') not in {'complete', 'unresolved', 'identity_review'})}
    # A missing key at one provider must not label a book blocked while another
    # ready source has yet to attempt it. Report the next available action.
    if any(row.get('state') in {'not_attempted', 'pending'} and name not in blocked
           for name, row in providers.items()):
        return 'not_attempted'
    if any(row.get('state') in {'retryable', 'retry_exhausted'} and name not in blocked
           for name, row in providers.items()):
        return 'retry_needed'
    if blocked:
        return 'provider_blocked'
    # A prior successful lookup cannot describe a currently missing default
    # cover (for example after choosing another edition) as a failed match.
    if 'complete' in states:
        return 'retry_needed'
    return 'no_safe_match'


def inventory(state_dir, jobs, health=None):
    """Inspect shared catalog data only; never create accounts or reading rows."""
    from django.conf import settings
    from backend.core.models import Person, RankingEntry, Work

    health = health or {}
    outcomes = {}
    for name, *_ in jobs:
        path = Path(state_dir) / f'{name}.sqlite3'
        if not path.exists():
            continue
        with closing(sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro', uri=True)) as connection:
            outcomes[name] = {}
            for identity, state, raw in connection.execute('SELECT work_id,state,result FROM attempts'):
                try:
                    saved = json.loads(raw)
                except (TypeError, ValueError):
                    saved = {}
                outcomes[name][identity] = {'state': state, 'status': saved.get('status'), 'error': saved.get('error')}

    def provider_outcomes(kind, identity):
        names = [name for name, *_ in jobs if (kind == 'cover' and (name == 'covers' or name.endswith('-covers')))
                 or (kind == 'portrait' and (name == 'portraits' or name.endswith('-portraits')))]
        return {name: outcomes.get(name, {}).get(identity, {'state': 'not_attempted', 'status': None, 'error': None})
                for name in names}

    shared = RankingEntry.objects.filter(is_archived=False, ranking__is_archived=False).exclude(ranking__origin='personal')
    ranked_works = set(shared.exclude(work_id=None).values_list('work_id', flat=True))
    ranked_people = set(shared.exclude(person_id=None).values_list('person_id', flat=True))
    rows, covers, portraits = [], Counter(), Counter()
    works = Work.objects.filter(is_archived=False).select_related('default_edition').prefetch_related('authors')
    for work in works:
        edition = work.default_edition
        state = image_state(settings.MEDIA_ROOT, edition.cover.name if edition else '')
        covers[state] += 1
        if state != 'ready':
            providers = provider_outcomes('cover', work.pk)
            rows.append({'kind': 'cover', 'id': work.pk, 'title': work.title,
                         'authors': [person.name for person in work.authors.all()], 'form': work.form,
                         'ranked': work.pk in ranked_works, 'file_state': state,
                         'reason': unresolved_reason(providers, health) if state == 'missing_image' else state,
                         'providers': providers})
    for person in Person.objects.filter(is_archived=False).only('id', 'name', 'portrait'):
        state = image_state(settings.MEDIA_ROOT, person.portrait.name)
        portraits[state] += 1
        if state != 'ready':
            providers = provider_outcomes('portrait', person.pk)
            rows.append({'kind': 'portrait', 'id': person.pk, 'name': person.name,
                         'ranked': person.pk in ranked_people, 'file_state': state,
                         'reason': unresolved_reason(providers, health) if state == 'missing_image' else state,
                         'providers': providers})
    rows.sort(key=lambda row: (not row['ranked'], row['kind'], row['id']))
    totals = {'counted_at': time.time(), 'total_works': sum(covers.values()), 'total_people': sum(portraits.values()),
              'covers_ready': covers['ready'], 'portraits_ready': portraits['ready'],
              'missing_covers': sum(covers.values()) - covers['ready'],
              'missing_portraits': sum(portraits.values()) - portraits['ready'],
              'cover_file_states': dict(covers), 'portrait_file_states': dict(portraits),
              'unresolved_reasons': dict(Counter(row['reason'] for row in rows)),
              'ranked_missing_covers': sum(row['ranked'] and row['kind'] == 'cover' for row in rows),
              'ranked_missing_portraits': sum(row['ranked'] and row['kind'] == 'portrait' for row in rows)}
    return totals, rows
