"""Reject byte-identical, reviewed wrong covers only for their catalog work.

A valid book image can be incorrectly linked to another book by a provider.
These decisions therefore pin both the catalog identity and the image bytes;
they are never global image bans. This module does not change catalog records.
"""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

from research.media_transport import CandidateRejected, public_url, validate_external_url


REGISTRY = Path(__file__).with_name('reviewed_cover_rejections.json')
_FIELDS = {'work_id', 'title', 'authors', 'image_sha256', 'reason', 'source_url', 'automatic_hold'}
_REQUIRED = _FIELDS - {'source_url', 'automatic_hold'}


def _signature(path):
    value = path.stat()
    return value.st_mtime_ns, value.st_size, value.st_ino, value.st_dev


@lru_cache(maxsize=8)
def _read_registry(path, signature):
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError('Invalid reviewed cover rejection registry JSON') from error
    if _signature(path) != signature:
        raise ValueError('Reviewed cover rejection registry changed during reading')
    if (not isinstance(payload, dict) or type(payload.get('version')) is not int
            or payload['version'] != 1 or not isinstance(payload.get('rejections'), list)):
        raise ValueError('Unsupported reviewed cover rejection registry')
    result = []
    for entry in payload['rejections']:
        if not isinstance(entry, dict) or not _REQUIRED <= entry.keys() or entry.keys() - _FIELDS:
            raise ValueError('Invalid reviewed cover rejection fields')
        if (type(entry['work_id']) is not int or entry['work_id'] <= 0
                or not isinstance(entry['title'], str) or not entry['title'].strip()
                or not isinstance(entry['authors'], list)
                or not all(isinstance(name, str) and name.strip() for name in entry['authors'])
                or not isinstance(entry['reason'], str) or not entry['reason'].strip()
                or not isinstance(entry['image_sha256'], str)
                or not re.fullmatch(r'[0-9a-f]{64}', entry['image_sha256'])
                or ('automatic_hold' in entry and type(entry['automatic_hold']) is not bool)):
            raise ValueError('Invalid reviewed cover rejection identity, digest or reason')
        if 'source_url' in entry:
            source = entry['source_url']
            try:
                if not isinstance(source, str) or not source:
                    raise ValueError('Missing source URL')
                parsed = validate_external_url(source)
                if parsed.scheme != 'https' or public_url(source) != source:
                    raise ValueError('Source URL must be public HTTPS without credentials or fragments')
            except (CandidateRejected, ValueError, TypeError) as error:
                raise ValueError('Invalid reviewed cover rejection source URL') from error
        # Immutable cached rows prevent a caller from changing future reviews.
        result.append((entry['work_id'], entry['title'], tuple(entry['authors']),
                       entry['image_sha256'], entry['reason'], entry.get('source_url'),
                       entry.get('automatic_hold')))
    return tuple(result)


def load_registry(path=None):
    """Read validated public decisions, refreshing after any file revision."""
    path = Path(path or REGISTRY)
    try:
        signature = _signature(path)
    except FileNotFoundError:
        return []
    return [dict(work_id=work_id, title=title, authors=list(authors), image_sha256=digest,
                 reason=reason, **({'source_url': source} if source is not None else {}),
                 **({'automatic_hold': hold} if hold is not None else {}))
            for work_id, title, authors, digest, reason, source, hold
            in _read_registry(str(path.resolve()), signature)]


def _matching(item):
    entries = load_registry()
    identity = item.get('id')
    title = item.get('display_title', item.get('title'))
    authors = item.get('authors')
    if (type(identity) is not int or not isinstance(title, str)
            or not isinstance(authors, list) or not all(isinstance(name, str) for name in authors)):
        return []
    return [entry for entry in entries if entry['work_id'] == identity
            and entry['title'] == title and sorted(entry['authors']) == sorted(authors)]


def requires_scope_review(item):
    """Identify an exact catalog work whose automatic covers need review."""
    return any(entry.get('automatic_hold') is True for entry in _matching(item))


def reject_reviewed_cover(item, blob, *, reviewed=False):
    """Reject reviewed wrong bytes, or unreviewed candidates for held works.

    A manual scope review may admit other images for the same work. It never
    overrides a recorded rejection of the exact image bytes.
    """
    applicable = _matching(item)
    if applicable:
        digest = hashlib.sha256(blob).hexdigest()
        for entry in applicable:
            if entry['image_sha256'] == digest:
                raise CandidateRejected('Reviewed wrong cover for this work: ' + entry['reason'])
        if reviewed is not True and any(entry.get('automatic_hold') is True for entry in applicable):
            raise CandidateRejected('Cover scope requires manual review for this work')
    return None
