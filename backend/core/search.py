"""Rebuildable shared-catalog search; never indexes private reading data.

SQLite FTS lives in a disposable sidecar, not the authoritative database. Catalog
commits enqueue affected identities; background workers replace only changed
search documents. Periodic reconciliation catches bulk writes without rebuilding
unchanged FTS rows. Private data and images never enter this index or its queue.
PostgreSQL and unavailable FTS use a portable accent-folded matching fallback.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
from tempfile import NamedTemporaryFile
from threading import Lock, Thread
import time
import unicodedata

from django.conf import settings
from django.db import connections, close_old_connections, transaction
from django.db.models import Case, IntegerField, Prefetch, Value, When
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save

logger = logging.getLogger(__name__)
SCHEMA = 2
MAX_STALE_SECONDS = 120
CHECK_SECONDS = 60
_running = set()
_lock = Lock()
_checked = {}
_observed_stale = {}


def fold(value):
    value = str(value).casefold().translate(str.maketrans({'ł': 'l', 'ø': 'o', 'đ': 'd', 'ð': 'd', 'þ': 'th', 'æ': 'ae', 'œ': 'oe'}))
    return ''.join(char for char in unicodedata.normalize('NFKD', value) if not unicodedata.combining(char))


def tokens(value):
    # Operators, quotes, punctuation and SQL never reach FTS syntax.
    return list(dict.fromkeys(re.findall(r'[^\W_]+', fold(str(value)[:300]), re.UNICODE)))[:16]


def fts_query(value):
    return ' AND '.join('"' + token + '"*' for token in tokens(value))


def index_path(using='default'):
    configured = getattr(settings, 'CATALOG_SEARCH_INDEX', None)
    if configured:
        return Path(configured).resolve()
    config = connections[using].settings_dict
    identity = f"{config['ENGINE']}:{config.get('HOST', '')}:{config['NAME']}:{using}"
    suffix = hashlib.sha256(identity.encode()).hexdigest()[:16]
    return Path(settings.BASE_DIR) / 'data' / 'search' / f'catalog-{suffix}.sqlite3'


def _aliases_path():
    return Path(getattr(settings, 'CATALOG_SEARCH_ALIASES', Path(settings.BASE_DIR) / 'docs/catalog_search_aliases.json'))


def aliases():
    path = _aliases_path()
    if not path.exists():
        return {'works': {}, 'people': {}}
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or set(data) - {'works', 'people'}:
        raise ValueError('Search aliases must contain only works and people ID mappings.')
    for kind in ['works', 'people']:
        rows = data.setdefault(kind, {})
        if not isinstance(rows, dict):
            raise ValueError('Search aliases must be ID mappings.')
        for pk, values in rows.items():
            if not str(pk).isdigit() or int(pk) < 1 or not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() or len(v) > 300 for v in values):
                raise ValueError('Search aliases require positive existing IDs and nonempty names of at most 300 characters.')
    return data


def _stamp(path):
    try:
        stat = Path(path).stat()
        return [stat.st_mtime_ns, stat.st_size]
    except OSError:
        return None


def _source_stamp(using='default'):
    connection = connections[using]
    source = str(connection.settings_dict['NAME'])
    return [_stamp(source), _stamp(source + '-wal')] if connection.vendor == 'sqlite' else None


def _queue_path(using='default'):
    return Path(str(index_path(using)) + '.pending.sqlite3')


def _pending(using='default'):
    path = _queue_path(using)
    if not path.exists():
        return {'watermark': 0, 'count': 0, 'since': None}
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=0.2) as queue:
        row = queue.execute('SELECT coalesce(max(sequence), 0), count(*), min(changed_at) FROM pending').fetchone()
        return dict(zip(['watermark', 'count', 'since'], row))


def _enqueue(identities, using='default'):
    identities = set(identities)
    if not identities or connections[using].vendor != 'sqlite':
        return
    path = _queue_path(using)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path, timeout=2) as queue:
            queue.execute('CREATE TABLE IF NOT EXISTS pending (sequence INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, object_id INTEGER NOT NULL, changed_at REAL NOT NULL, UNIQUE(kind, object_id))')
            # Replacing allocates a new sequence even for an already queued ID.
            # A worker may acknowledge only the generation it actually observed.
            queue.executemany(
                'INSERT OR REPLACE INTO pending(kind,object_id,changed_at) VALUES (?,?,coalesce((SELECT changed_at FROM pending WHERE kind = ? AND object_id = ?),?))',
                [(kind, pk, kind, pk, time.time()) for kind, pk in identities])
        os.chmod(path, 0o600)
    except (OSError, sqlite3.Error):
        logger.warning('Could not queue catalog search changes; periodic content reconciliation remains active.')


def _acknowledge(using, watermark):
    if watermark:
        with sqlite3.connect(_queue_path(using), timeout=2) as queue:
            queue.execute('DELETE FROM pending WHERE sequence <= ?', [watermark])


def _documents(using='default', *, people_ids=None, work_ids=None):
    from .models import Person, Tag, Work
    names = aliases()
    people = Person.objects.using(using).only('id', 'name')
    if people_ids is not None:
        people = people.filter(pk__in=people_ids)
    existing_people = set()
    for person in people.iterator(chunk_size=1000):
        existing_people.add(str(person.pk))
        yield ('person', person.pk, fold(person.name), fold(' '.join(names['people'].get(str(person.pk), []))), '', '')
    works = Work.objects.using(using).only('id', 'title').prefetch_related(Prefetch('authors', queryset=Person.objects.using(using).only('id', 'name')), Prefetch('tags', queryset=Tag.objects.using(using).only('id', 'name', 'is_archived')))
    if work_ids is not None:
        works = works.filter(pk__in=work_ids)
    existing_works = set()
    for work in works.iterator(chunk_size=500):
        existing_works.add(str(work.pk))
        authors = ' '.join(person.name + ' ' + ' '.join(names['people'].get(str(person.pk), [])) for person in work.authors.all())
        tags = ' '.join(tag.name for tag in work.tags.all() if not tag.is_archived)
        yield ('work', work.pk, fold(work.title), fold(' '.join(names['works'].get(str(work.pk), []))), fold(authors), fold(tags))
    # A typo in an aliases file must not silently point at a different catalog.
    if (people_ids is None and set(names['people']) - existing_people) or (work_ids is None and set(names['works']) - existing_works):
        logger.warning('Search aliases include missing catalog IDs; those aliases were omitted.')


def _fingerprint(row):
    return hashlib.sha256(json.dumps(row[2:], ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def _catalog_fingerprint(using):
    """Compare only searchable columns/links, without constructing documents.

    File stamps cannot identify which table changed. This cheap bounded-interval
    pass avoids title folding, related-object materialization and all FTS writes
    when private records, edition images or other unindexed fields changed.
    """
    from .models import Person, Tag, Work
    sources = [
        (Work, ('id', 'title')), (Person, ('id', 'name')),
        (Tag, ('id', 'name', 'is_archived')),
        (Work.authors.through, ('work_id', 'person_id')),
        (Work.tags.through, ('work_id', 'tag_id')),
    ]
    digest = hashlib.sha256()
    checked = 0
    for model, fields in sources:
        digest.update(model._meta.label.encode())
        rows = model.objects.using(using).order_by(*fields[:1]).values_list(*fields)
        # Through rows need deterministic ordering within a work as well.
        if model in {Work.authors.through, Work.tags.through}:
            rows = rows.order_by(*fields)
        for row in rows.iterator(chunk_size=2000):
            digest.update(json.dumps(row, ensure_ascii=False, separators=(',', ':')).encode())
            digest.update(b'\n')
            checked += 1
    return digest.hexdigest(), checked


def _metadata(target):
    return json.loads(target.execute('SELECT value FROM metadata').fetchone()[0])


def _put_document(target, row, existing=None):
    fingerprint = _fingerprint(row)
    if existing is not None and existing[1] == fingerprint:
        return False
    if existing is not None:
        rowid = existing[0]
        target.execute('DELETE FROM documents WHERE rowid = ?', [rowid])
        target.execute('INSERT INTO documents(rowid,kind,object_id,title,aliases,authors,tags) VALUES (?,?,?,?,?,?,?)', [rowid, *row])
        target.execute('UPDATE document_keys SET fingerprint = ? WHERE rowid = ?', [fingerprint, rowid])
    else:
        cursor = target.execute('INSERT INTO documents(kind,object_id,title,aliases,authors,tags) VALUES (?,?,?,?,?,?)', row)
        target.execute('INSERT INTO document_keys(rowid,kind,object_id,fingerprint) VALUES (?,?,?,?)', [cursor.lastrowid, row[0], row[1], fingerprint])
    return True


def _rebuild_locked(using, path):
    pending = _pending(using)
    source_stamp, aliases_stamp = _source_stamp(using), _stamp(_aliases_path())
    temporary = None
    try:
        with NamedTemporaryFile(dir=path.parent, prefix='search-', suffix='.sqlite3', delete=False) as handle:
            temporary = Path(handle.name)
        with sqlite3.connect(temporary) as target:
            target.execute("CREATE VIRTUAL TABLE documents USING fts5(kind UNINDEXED, object_id UNINDEXED, title, aliases, authors, tags, tokenize='unicode61 remove_diacritics 2')")
            target.execute('CREATE TABLE document_keys (rowid INTEGER PRIMARY KEY, kind TEXT NOT NULL, object_id INTEGER NOT NULL, fingerprint TEXT NOT NULL, UNIQUE(kind, object_id))')
            target.execute('CREATE TABLE metadata (value TEXT NOT NULL)')
            with transaction.atomic(using=using):
                for row in _documents(using):
                    _put_document(target, row)
                fingerprint, _ = _catalog_fingerprint(using)
            total = target.execute('SELECT count(*) FROM documents').fetchone()[0]
            now = time.time()
            info = {'schema': SCHEMA, 'built_at': now, 'updated_at': now, 'reconciled_at': now,
                    'source': source_stamp, 'aliases': aliases_stamp, 'documents': total,
                    'catalog_fingerprint': fingerprint,
                    'last_update': {'mode': 'rebuild', 'scanned': total, 'updated': total, 'deleted': 0}}
            target.execute('INSERT INTO metadata(value) VALUES (?)', [json.dumps(info)])
            target.execute("INSERT INTO documents(documents) VALUES ('optimize')")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        _acknowledge(using, pending['watermark'])
        _checked.pop(str(path), None)
        return info
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def _with_writer(using, operation):
    import fcntl
    path = index_path(using)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path) + '.lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'busy': True}
        return operation(using, path)


def rebuild_index(using='default'):
    """Explicit/schema-recovery rebuild, preserving the previous index on failure."""
    return _with_writer(using, _rebuild_locked)


def _read_info(path):
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=0.2) as source:
        return _metadata(source)


def index_status(using='default'):
    path = index_path(using)
    try:
        info = _read_info(path)
        pending = _pending(using)
        aliases_changed = info.get('aliases') != _stamp(_aliases_path())
        reconcile_due = time.time() - info.get('reconciled_at', 0) >= CHECK_SECONDS and info.get('source') != _source_stamp(using)
        info.update(pending=pending['count'], needs_reconcile=reconcile_due,
                    stale=info.get('schema') != SCHEMA or bool(pending['count']) or aliases_changed or reconcile_due)
        since = []
        if pending['since'] is not None:
            since.append(pending['since'])
        if aliases_changed or reconcile_due:
            # An old index may still be perfectly current: a private edit after
            # a long idle period must not force an immediate portable scan.
            key, revision = str(path), info.get('reconciled_at', 0)
            observed = _observed_stale.get(key)
            if observed is None or observed[0] != revision:
                observed = (revision, time.time())
                _observed_stale[key] = observed
                if len(_observed_stale) > 128:
                    _observed_stale.pop(next(iter(_observed_stale)))
            since.append(observed[1])
        else:
            _observed_stale.pop(str(path), None)
        info['stale_since'] = min(since) if since else None
        return info
    except (OSError, ValueError, sqlite3.Error, TypeError, KeyError):
        return {'stale': True, 'missing': True}


def _affected_identities(using, watermark):
    from .models import Work
    with sqlite3.connect(_queue_path(using), timeout=0.2) as queue:
        rows = queue.execute('SELECT kind, object_id FROM pending WHERE sequence <= ?', [watermark]).fetchall()
    people = {pk for kind, pk in rows if kind == 'person'}
    tags = {pk for kind, pk in rows if kind == 'tag'}
    works = {pk for kind, pk in rows if kind == 'work'}
    if people:
        works.update(Work.authors.through.objects.using(using).filter(person_id__in=people).values_list('work_id', flat=True))
    if tags:
        works.update(Work.tags.through.objects.using(using).filter(tag_id__in=tags).values_list('work_id', flat=True))
    return people, works


def _existing_documents(target, scope):
    if scope is None:
        rows = target.execute('SELECT rowid,kind,object_id,fingerprint FROM document_keys')
        return {(kind, pk): (rowid, fingerprint) for rowid, kind, pk, fingerprint in rows}
    result = {}
    for kind in ['person', 'work']:
        ids = [pk for row_kind, pk in scope if row_kind == kind]
        for start in range(0, len(ids), 500):
            batch = ids[start:start + 500]
            placeholders = ','.join('?' for _ in batch)
            rows = target.execute(f'SELECT rowid,kind,object_id,fingerprint FROM document_keys WHERE kind = ? AND object_id IN ({placeholders})', [kind, *batch])
            result.update({(row_kind, pk): (rowid, fingerprint) for rowid, row_kind, pk, fingerprint in rows})
    return result


def _sync_locked(using, path, *, reconcile=False):
    try:
        info = _read_info(path)
    except (OSError, ValueError, sqlite3.Error, TypeError, KeyError):
        return _rebuild_locked(using, path)
    if info.get('schema') != SCHEMA:
        return _rebuild_locked(using, path)
    pending = _pending(using)
    source_stamp, aliases_stamp = _source_stamp(using), _stamp(_aliases_path())
    reconcile = reconcile or info.get('aliases') != aliases_stamp or (
        time.time() - info.get('reconciled_at', 0) >= CHECK_SECONDS and info.get('source') != source_stamp)
    if not reconcile and not pending['count']:
        return {**info, 'last_update': {'mode': 'unchanged', 'scanned': 0, 'updated': 0, 'deleted': 0}}
    changes = {'mode': 'reconcile' if reconcile else 'incremental', 'scanned': 0, 'updated': 0, 'deleted': 0}
    # One source snapshot, one atomic FTS transaction. Readers keep seeing the
    # previous complete state until commit; another writer is excluded by flock.
    with transaction.atomic(using=using), sqlite3.connect(path, timeout=2) as target:
        same_content = False
        if reconcile:
            fingerprint, checked_rows = _catalog_fingerprint(using)
            same_content = info.get('catalog_fingerprint') == fingerprint and info.get('aliases') == aliases_stamp
            changes['checked_catalog_rows'] = checked_rows
        people, works = (None, None) if reconcile else _affected_identities(using, pending['watermark'])
        scope = None if reconcile else {('person', pk) for pk in people} | {('work', pk) for pk in works}
        if same_content:
            scope, people, works = set(), set(), set()
        existing = _existing_documents(target, scope)
        if reconcile and not same_content:
            scope = set(existing)
        seen = set()
        for row in _documents(using, people_ids=people, work_ids=works):
            key = (row[0], row[1])
            seen.add(key)
            changes['scanned'] += 1
            changes['updated'] += _put_document(target, row, existing.get(key))
        for key in scope - seen:
            if key in existing:
                rowid = existing[key][0]
                target.execute('DELETE FROM documents WHERE rowid = ?', [rowid])
                target.execute('DELETE FROM document_keys WHERE rowid = ?', [rowid])
                changes['deleted'] += 1
        info['updated_at'] = time.time()
        info['documents'] = target.execute('SELECT count(*) FROM document_keys').fetchone()[0]
        info['last_update'] = changes
        if reconcile:
            info.update(reconciled_at=info['updated_at'], source=source_stamp, aliases=aliases_stamp, catalog_fingerprint=fingerprint)
        elif changes['updated'] or changes['deleted']:
            # The last whole-catalog digest no longer describes the FTS state.
            # In particular a later bulk edit may revert the source to that old
            # digest, while the index still contains this incremental update.
            info['catalog_fingerprint'] = None
        target.execute('UPDATE metadata SET value = ?', [json.dumps(info)])
    # A save arriving during this transaction has a higher sequence, including
    # another save of the very same object, and survives this acknowledgement.
    _acknowledge(using, pending['watermark'])
    _checked.pop(str(path), None)
    return info


def sync_index(using='default', *, reconcile=False):
    """Apply queued documents; periodically compare content for bulk/SQL writes."""
    return _with_writer(using, lambda alias, path: _sync_locked(alias, path, reconcile=reconcile))


def _schedule(using, *, rebuild=False):
    connection = connections[using]
    # Test transactions/in-memory databases are not visible in another connection.
    if connection.in_atomic_block or ':memory:' in str(connection.settings_dict['NAME']):
        return
    key = (using, str(index_path(using)))
    with _lock:
        if key in _running:
            return
        _running.add(key)
    def run():
        try:
            close_old_connections()
            rebuild_index(using) if rebuild else sync_index(using)
        except Exception:
            logger.exception('Catalog search update failed; portable search remains available.')
        finally:
            connections.close_all()
            with _lock:
                _running.discard(key)
    Thread(target=run, name='catalog-search-update', daemon=True).start()


def _indexed_ids(term, kind, using):
    path = index_path(using)
    if connections[using].vendor != 'sqlite':
        return None
    now = time.monotonic()
    key = str(path)
    dirty = [_stamp(_queue_path(using)), _stamp(_aliases_path()), _stamp(path)]
    checked = _checked.get(key)
    if not checked or now - checked[0] >= CHECK_SECONDS or checked[1] != dirty:
        status = index_status(using)
        _checked[key] = (now, dirty, status)
    else:
        status = checked[2]
    if status.get('stale'):
        _schedule(using)
    stale_since = status.get('stale_since')
    if status.get('missing') or status.get('schema') != SCHEMA or (stale_since is not None and time.time() - stale_since > MAX_STALE_SECONDS):
        return None
    try:
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=0.2) as source:
            return [row[0] for row in source.execute(
                'SELECT object_id FROM documents WHERE documents MATCH ? AND kind = ? '
                'ORDER BY CASE WHEN title = ? OR aliases = ? THEN 0 WHEN title LIKE ? ESCAPE "\\" THEN 1 ELSE 2 END, '
                'bm25(documents, 0, 0, 8, 6, 4, 1), title, CAST(object_id AS INTEGER)',
                [fts_query(term), kind, fold(term.strip()), fold(term.strip()), fold(term.strip()).replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'])]
    except (OSError, sqlite3.Error) as error:
        # A malformed/deleted FTS table needs recovery, not a no-op queue drain.
        # Ordinary contention needs only a later retry, never a full rebuild.
        busy = getattr(error, 'sqlite_errorcode', None) in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
        _schedule(using, rebuild=not busy)
        return None


def _portable_ids(term, kind, using):
    words = tokens(term)
    matches = []
    from .catalog_cache import cached_catalog
    documents = cached_catalog(('search-portable', using, _stamp(_aliases_path()) and tuple(_stamp(_aliases_path()))), lambda: list(_documents(using)), ttl=30, copy=False)
    for row_kind, pk, title, alternate, authors, tags in documents:
        if row_kind != kind:
            continue
        fields = [title, alternate, authors, tags]
        field_words = [re.findall(r'[^\W_]+', field, re.UNICODE) for field in fields]
        if all(any(word.startswith(query) for words_in_field in field_words for word in words_in_field) for query in words):
            score = sum(next((weight for field, weight in zip(field_words, [8, 6, 4, 1]) if any(word.startswith(query) for word in field)), 0) for query in words)
            phrase = fold(term.strip())
            matches.append((0 if phrase in [title, alternate] else 1 if title.startswith(phrase) else 2, -score, title, pk))
    return [row[3] for row in sorted(matches)]


def search_catalog(queryset, term, *, kind='work', order=True):
    if not str(term).strip():
        return queryset
    if not tokens(term):
        return queryset.none()
    ids = _indexed_ids(term, kind, queryset.db)
    if ids is None:
        ids = _portable_ids(term, kind, queryset.db)
    if not ids:
        return queryset.none()
    # Always reapply the caller's visibility/ownership/filter constraints. The
    # shared index is only a candidate ordering, never an authorization source.
    queryset = queryset.filter(pk__in=ids)
    if order:
        queryset = queryset.order_by(Case(*(When(pk=pk, then=Value(position)) for position, pk in enumerate(ids)), output_field=IntegerField()), 'pk')
    return queryset


def _searchable_save(sender, instance, using='default', update_fields=None, raw=False, **kwargs):
    fields = {'work': {'title'}, 'person': {'name'}, 'tag': {'name', 'is_archived'}}[sender._meta.model_name]
    if update_fields is not None:
        fields &= set(update_fields)
    instance._catalog_search_changed = False
    if raw or not fields:
        return
    if instance._state.adding:
        instance._catalog_search_changed = True
        return
    previous = sender.objects.using(using).filter(pk=instance.pk).values(*fields).first()
    instance._catalog_search_changed = previous is None or any(previous[field] != getattr(instance, field) for field in fields)


def _saved(sender, instance, using='default', created=False, raw=False, **kwargs):
    if raw or not (created or getattr(instance, '_catalog_search_changed', False)):
        return
    identity = (sender._meta.model_name, instance.pk)
    transaction.on_commit(lambda: _enqueue([identity], using), using=using)


def _deleted(sender, instance, using='default', **kwargs):
    identity = (sender._meta.model_name, instance.pk)
    transaction.on_commit(lambda: _enqueue([identity], using), using=using)


def _relations_changed(sender, instance, action, reverse, pk_set, using='default', **kwargs):
    from .models import Work
    relation = 'person' if sender is Work.authors.through else 'tag'
    if action == 'pre_clear' and reverse:
        # Clearing from the author/tag end loses these links before post_clear.
        ids = sender.objects.using(using).filter(**{relation + '_id': instance.pk}).values_list('work_id', flat=True)
        setattr(instance, '_catalog_search_cleared_' + relation, set(ids))
    if not action.startswith('post_'):
        return
    if reverse:
        works = getattr(instance, '_catalog_search_cleared_' + relation, set()) if action == 'post_clear' else pk_set
    else:
        works = {instance.pk} if action == 'post_clear' or pk_set else set()
    identities = [('work', pk) for pk in works]
    transaction.on_commit(lambda: _enqueue(identities, using), using=using)


def connect_search_invalidation():
    from .models import Person, Tag, Work
    for model in [Person, Tag, Work]:
        pre_save.connect(_searchable_save, sender=model, weak=False, dispatch_uid=f'search-before-save-{model._meta.label}')
        post_save.connect(_saved, sender=model, weak=False, dispatch_uid=f'search-save-{model._meta.label}')
        post_delete.connect(_deleted, sender=model, weak=False, dispatch_uid=f'search-delete-{model._meta.label}')
    for model in [Work.authors.through, Work.tags.through]:
        m2m_changed.connect(_relations_changed, sender=model, weak=False, dispatch_uid=f'search-m2m-{model._meta.label}')
