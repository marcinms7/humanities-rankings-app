"""Operational retry index. Catalog data remains in the configured Django DB.

JSONL is the immutable audit trail; this small SQLite index is reconstructible.
Legacy outcomes are streamed once, never reread in full for each 50-row batch.
"""
from __future__ import annotations
import contextlib
import fcntl
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import time

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / 'data' / 'enrichment'
MAX_ATTEMPTS = 3


@contextlib.contextmanager
def exclusive(name):
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / f'{name}.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit(f'{name} is already running.')
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def rotate(path, threshold=20 * 1024 * 1024):
    """Preserve a compressed, checksummed archive before removing active bytes."""
    if not path.exists() or path.stat().st_size < threshold:
        return
    folder = path.parent / 'archives'
    folder.mkdir(exist_ok=True)
    target = folder / f'{path.name}.{time.time_ns()}.gz'
    temporary = target.with_suffix('.gz.partial')
    digest, size = hashlib.sha256(), 0
    with path.open('rb') as source, gzip.open(temporary, 'wb') as dest:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            dest.write(chunk); digest.update(chunk); size += len(chunk)
    check = hashlib.sha256()
    with gzip.open(temporary, 'rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            check.update(chunk)
    if check.digest() != digest.digest():
        raise RuntimeError('Archive verification failed; original log preserved.')
    with temporary.open('rb') as compressed:
        os.fsync(compressed.fileno())
    temporary.replace(target)
    with (folder / 'manifest.jsonl').open('a') as manifest:
        manifest.write(json.dumps({'archive': target.name, 'original': path.name,
                                  'uncompressed_bytes': size, 'sha256': digest.hexdigest()}) + '\n')
        manifest.flush(); os.fsync(manifest.fileno())
    path.unlink()


def records(path):
    archives = path.parent / 'archives'
    # Nanosecond suffixes preserve chronological order on a rebuild.
    paths = sorted(archives.glob(f'{path.name}.*.gz')) + ([path] if path.exists() else [])
    for source in paths:
        opener = gzip.open if source.suffix == '.gz' else open
        with opener(source, 'rt', encoding='utf-8', errors='replace') as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                    if isinstance(row, dict) and 'work_id' in row:
                        yield row
                except (ValueError, TypeError):
                    continue  # A torn final append does not invalidate earlier records.


def classify(status):
    if status in {'covered', 'found', 'preserved_existing'}:
        return 'complete'
    if any(term in status for term in ('no_author', 'no_credited_author', 'identity_review')):
        return 'identity_review'
    if any(term in status.lower() for term in ('error', 'timeout', 'timed out', '429', '503', '502')):
        return 'retryable'
    return 'unresolved'


def provider_failure(result):
    """Only explicit outages/HTTP service failures bypass the item retry budget."""
    if result.get('provider_outage') is True:
        return True
    message = str(result.get('status', '')) + ' ' + str(result.get('error', ''))
    return bool(re.search(r'\bHTTP(?: Error)?\s+(?:429|502|503|504)\b', message, re.I))


class Queue:
    def __init__(self, kind, ledger):
        self.batch_errors = 0
        self.inspected_ids = set()
        STATE.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(STATE / f'{kind}.sqlite3', timeout=20)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS attempts (
                work_id INTEGER PRIMARY KEY, fingerprint TEXT, attempts INTEGER NOT NULL,
                state TEXT NOT NULL, next_retry REAL NOT NULL, result TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT);
        ''')
        if not self.db.execute("SELECT 1 FROM metadata WHERE key='legacy_imported'").fetchone():
            with self.db:
                for row in records(ledger):
                    try: work_id = int(row['work_id'])
                    except (TypeError, ValueError): continue
                    state = classify(str(row.get('status', 'unknown')))
                    if row.get('input_fingerprint'):
                        self.db.execute('INSERT OR REPLACE INTO attempts VALUES (?,?,?,?,?,?)',
                            (work_id, row['input_fingerprint'], row['attempt'], row.get('queue_state', state),
                             row.get('next_retry') or 0, json.dumps(row, ensure_ascii=False)))
                        continue
                    self.db.execute('''INSERT INTO attempts VALUES (?,NULL,1,?,0,?)
                        ON CONFLICT(work_id) DO UPDATE SET attempts=attempts+1,state=excluded.state,
                        result=excluded.result''', (work_id, state, json.dumps(row, ensure_ascii=False)))
                self.db.execute("UPDATE attempts SET state='retry_exhausted' WHERE state='retryable' AND attempts>=?", (MAX_ATTEMPTS,))
                self.db.execute("INSERT INTO metadata VALUES ('legacy_imported',?)", (str(time.time()),))
        # Recover a crash between the durable audit append and index commit.
        # Active logs are bounded by rotation; completed archives are imported once.
        if ledger.exists():
            with ledger.open(encoding='utf-8', errors='replace') as stream, self.db:
                for line in stream:
                    try:
                        row = json.loads(line)
                        if not row.get('attempted_at') or not row.get('input_fingerprint'):
                            continue
                        current = self.db.execute('SELECT fingerprint,result FROM attempts WHERE work_id=?', (row['work_id'],)).fetchone()
                        if current and current[0] == row['input_fingerprint'] and row['attempted_at'] > json.loads(current[1]).get('attempted_at', 0):
                            self.db.execute('UPDATE attempts SET attempts=?,state=?,next_retry=?,result=? WHERE work_id=?',
                                (row['attempt'], row['queue_state'], row.get('next_retry') or 0, json.dumps(row), row['work_id']))
                    except (ValueError, KeyError, TypeError):
                        continue

        # Older workers charged provider-wide outages to every record in a
        # batch. Recover only those transient failures, preserving successful,
        # ambiguous and no-match decisions and the original audit history.
        if not self.db.execute("SELECT 1 FROM metadata WHERE key='provider_outages_v1'").fetchone():
            with self.db:
                for work_id, state, raw in self.db.execute(
                        "SELECT work_id,state,result FROM attempts WHERE state IN ('retryable','retry_exhausted')").fetchall():
                    try:
                        result = json.loads(raw)
                    except (TypeError, ValueError):
                        continue
                    if provider_failure(result):
                        self.db.execute("UPDATE attempts SET state='provider_wait',attempts=0,next_retry=0 WHERE work_id=?", (work_id,))
                self.db.execute("INSERT INTO metadata VALUES ('provider_outages_v1',?)", (str(time.time()),))

    def due(self, item, policy, retry=False):
        self.inspected_ids.add(item['id'])
        inputs = {key: item.get(key) for key in ('title', 'authors', 'isbn', 'year')}
        # Page lookups apply to a particular edition. A newly selected edition
        # needs its own lookup even when its work title and ISBN are unchanged.
        for key in ('edition_id', 'provider_identifiers', 'title_aliases', 'author_aliases', 'source_urls', 'isbns',
                    'publishers', 'works', 'work_aliases', 'biography', 'verified_identity_urls', 'birth_year', 'death_year', 'ranked', 'linked_works'):
            if key in item:
                inputs[key] = bool(item[key]) if key == 'ranked' else item[key]
        fingerprint = hashlib.sha256(json.dumps(inputs, sort_keys=True, ensure_ascii=False).encode() + policy.encode()).hexdigest()
        row = self.db.execute('SELECT fingerprint,attempts,state,next_retry FROM attempts WHERE work_id=?', (item['id'],)).fetchone()
        if row is None or retry or (row[0] is not None and row[0] != fingerprint):
            with self.db:
                self.db.execute('INSERT OR REPLACE INTO attempts VALUES (?,?,0,\'pending\',0,\'{}\')', (item['id'], fingerprint))
            return True
        if row[0] is None:
            with self.db:
                self.db.execute('UPDATE attempts SET fingerprint=? WHERE work_id=?', (fingerprint, item['id']))
        return (row[2] == 'pending' or
                (row[2] == 'provider_wait' and row[3] <= time.time()) or
                (row[2] == 'retryable' and row[1] < MAX_ATTEMPTS and row[3] <= time.time()))

    def priority(self, item):
        row = self.db.execute('SELECT attempts,state,result FROM attempts WHERE work_id=?', (item['id'],)).fetchone()
        priority = item.get('priority', item.get('ranked', item.get('shared_priority', 0)))
        # Provider outages intentionally do not spend the item attempt budget.
        # Consequently attempts=0 cannot distinguish a fresh item from a book
        # that failed on every recovery probe. Fresh work goes first; among
        # outage retries, rotate by last attempt instead of pinning the same ID.
        last_attempt = 0
        if row and row[1] == 'provider_wait':
            try:
                saved = json.loads(row[2])
                value = saved.get('attempted_at', 0)
                last_attempt = value if type(value) in (int, float) and math.isfinite(value) else 0
            except (TypeError, ValueError):
                pass
        return (bool(row and row[1] != 'pending'), row[0] if row else 0,
                last_attempt, -int(priority or 0), item['id'])

    def finish(self, item, result, audit):
        self.inspected_ids.add(item['id'])
        current = self.db.execute('SELECT attempts,fingerprint FROM attempts WHERE work_id=?', (item['id'],)).fetchone()
        outage = provider_failure(result)
        attempt = (current[0] if current else 0) + (0 if outage else 1)
        state = 'provider_wait' if outage else classify(str(result.get('status', 'unknown')))
        if state in {'retryable', 'provider_wait'}:
            self.batch_errors += 1
        if state == 'retryable' and attempt >= MAX_ATTEMPTS:
            state = 'retry_exhausted'
        next_retry = time.time() + min(900, 60 * 2 ** (attempt - 1)) if state == 'retryable' else 0
        if outage:
            supplied = result.get('retry_after')
            supplied = supplied if type(supplied) in (int, float) and math.isfinite(supplied) else 0
            next_retry = max(time.time() + 60, supplied)
        result.update(attempt=attempt, queue_state=state, attempted_at=time.time(), next_retry=next_retry or None,
                      input_fingerprint=current[1] if current else None)
        audit.write(json.dumps(result, ensure_ascii=False) + '\n')
        audit.flush(); os.fsync(audit.fileno())
        with self.db:
            self.db.execute('''UPDATE attempts SET attempts=?,state=?,next_retry=?,result=? WHERE work_id=?''',
                            (attempt, state, next_retry, json.dumps(result, ensure_ascii=False), item['id']))

    def summary(self):
        """Summarize records inspected in this invocation, retaining old history.

        A covered/archived record's stale retry must not hide a current item's
        future retry and incorrectly mark the provider exhausted. Filtering in
        one streamed read also avoids SQLite parameter limits for large queues.
        """
        states, retries = {}, []
        if self.inspected_ids:
            for identity, state, retry in self.db.execute('SELECT work_id,state,next_retry FROM attempts'):
                if identity not in self.inspected_ids:
                    continue
                states[state] = states.get(state, 0) + 1
                if state in {'retryable', 'provider_wait'}:
                    retries.append(retry)
        return {'states': states, 'next_retry': min(retries, default=None)}

    def close(self):
        self.db.close()
