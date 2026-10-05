"""Exact, reviewed provider placeholders shared by ingestion and reporting.

Only byte-identical reviewed images qualify. Size is an inexpensive prefilter,
never a reason to reject or replace an image. Existing originals are not edited.
"""
import hashlib
import os
from pathlib import Path
import stat
import time

from research.media_transport import CandidateRejected


# Internet Archive /services/img generic logo, visually audited 2026-10-05:
# 320x220 PNG, 3,777 bytes. A logo is not a book cover or a person's portrait.
KNOWN_PLACEHOLDERS = {
    'f84e75694fef8121d7fed94ab7f1a92751e48188e512d66207498f6825fc9408': 3777,
}
REPLACEMENT_POLICY = 'replace-reviewed-placeholder-v1'


def is_placeholder_digest(digest):
    return digest in KNOWN_PLACEHOLDERS


def placeholder_digest(blob):
    if len(blob) not in KNOWN_PLACEHOLDERS.values():
        return None
    digest = hashlib.sha256(blob).hexdigest()
    return digest if is_placeholder_digest(digest) else None


def reject_known_placeholder(blob):
    if placeholder_digest(blob):
        raise CandidateRejected('Known provider placeholder image')


def placeholder_file(path):
    """Return exact reviewed digest for an unchanged regular file, or None."""
    try:
        path = Path(path)
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_size not in KNOWN_PLACEHOLDERS.values():
            return None
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, 'rb') as stream:
            opened = os.fstat(stream.fileno())
            signature = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
            if signature(opened) != signature(before):
                return None
            blob = stream.read(opened.st_size + 1)
            if len(blob) != opened.st_size or signature(os.fstat(stream.fileno())) != signature(opened):
                return None
        return placeholder_digest(blob)
    except (OSError, ValueError, TypeError):
        return None


def placeholder_reference(field):
    if not field:
        return None
    try:
        digest = placeholder_file(field.path)
    except (OSError, ValueError, TypeError, NotImplementedError):
        return None
    if digest:
        return {'path': field.name, 'sha256': digest, 'size': KNOWN_PLACEHOLDERS[digest]}
    return None


def needs_cover(work):
    edition = work.default_edition
    return not edition or not edition.cover or placeholder_reference(edition.cover) is not None


def replacement_receipt(edition, item):
    """Recheck the exact reference under the caller's catalog row lock."""
    expected = item.get('placeholder_replacement')
    if not expected or placeholder_reference(edition.cover) != expected:
        return None
    return {**expected, 'edition_id': edition.pk, 'source_url': edition.cover_source_url,
            'cover_basis': edition.cover_basis, 'image_attribution': edition.image_attribution}


def lookup_policy(policy, item):
    # Reopen only these known bad references once, retaining ordinary retry
    # state thereafter and leaving every provider/host cooldown untouched.
    return policy + ':' + REPLACEMENT_POLICY if item.get('placeholder_replacement') else policy


def lookup_due(queue, item, policy, *, retry=False):
    """Reopen a reviewed repair without shortening an existing retry wait."""
    if item.get('placeholder_replacement'):
        row = queue.db.execute('SELECT fingerprint,state,next_retry FROM attempts WHERE work_id=?',
                               (item['id'],)).fetchone()
        if row:
            if row[1] in {'provider_wait', 'retryable'} and row[2] > time.time():
                queue.inspected_ids.add(item['id'])
                return False
            # Legacy imported successes have no fingerprint: explicitly reopen
            # once, then normal fingerprint/retry semantics apply thereafter.
            retry = retry or (row[0] is None and row[1] != 'pending')
    return queue.due(item, lookup_policy(policy, item), retry=retry)
