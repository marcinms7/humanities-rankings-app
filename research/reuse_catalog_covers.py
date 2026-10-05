"""Reuse a saved cover for an equivalent catalog work, preserving provenance.

Default is a read-only preview. --apply uses the usual transactional ingestion
and durable audit queue. No books are merged and no bibliographic facts copied.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
REGISTRY = ROOT / 'research/reviewed_cover_equivalences.json'
POLICY = 'catalog-equivalent-covers-v1'


def identity(work):
    return {'id': work.pk, 'title': work.title,
            'authors': sorted(person.name for person in work.authors.all()),
            'author_ids': sorted(person.pk for person in work.authors.all()),
            'form': work.form, 'year': work.original_year, 'contained_in': work.contained_in_id}


def load_registry(path=None):
    path = Path(path or REGISTRY)
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    if data.get('version') != 1 or not isinstance(data.get('equivalences'), list):
        raise ValueError('Unsupported cover equivalence registry')
    for entry in data['equivalences']:
        if (not isinstance(entry, dict) or type(entry.get('work_id')) is not int
                or type(entry.get('source_work_id')) is not int or entry.get('reviewed') is not True
                or type(entry.get('source_edition_id')) is not int
                or not re.fullmatch(r'[0-9a-f]{64}', str(entry.get('source_sha256', '')))
                or not all(entry.get(key) for key in ('title', 'authors', 'source_title', 'source_authors', 'reason', 'source_cover'))):
            raise ValueError('Cover equivalences must pin both reviewed identities and reasoning')
    return data['equivalences']


def reviewed_equivalent(left, right, entry):
    return (entry['work_id'] == left['id'] and entry['source_work_id'] == right['id']
            and entry['title'] == left['title'] and entry['source_title'] == right['title']
            and sorted(entry['authors']) == left['authors']
            and sorted(entry['source_authors']) == right['authors'])


def read_cover(root, relative):
    """Read a bounded regular file without following any symlink component."""
    from research.media_transport import CandidateRejected, MAX_BYTES
    parts = PurePosixPath(relative).parts
    if (not parts or parts[0] != 'covers' or '..' in parts or '\\' in relative
            or PurePosixPath(relative).is_absolute()):
        raise CandidateRejected('Invalid catalog cover path')
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    finally:
        os.close(directory)
    with os.fdopen(descriptor, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES:
            raise CandidateRejected('Catalog cover is not a bounded regular file')
        blob = stream.read(MAX_BYTES + 1)
        after = os.fstat(stream.fileno())
        if len(blob) > MAX_BYTES or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise CandidateRejected('Catalog cover changed during read')
    return blob


def source_pin(work):
    edition = work.default_edition
    return {'identity': identity(work), 'edition_id': edition.pk, 'cover': edition.cover.name,
            'basis': edition.cover_basis, 'source': edition.cover_source_url,
            'credit': edition.image_attribution, 'updated_at': edition.updated_at.isoformat()}


def opportunities(works, registry):
    from django.conf import settings
    from research.media_image_quality import needs_cover
    from research.media_inventory import image_state
    available, reviewed = {}, defaultdict(list)
    for entry in registry:
        reviewed[entry['work_id']].append(entry)
    for work in works:
        edition = work.default_edition
        if (edition and not edition.is_archived and edition.work_id == work.pk
                and image_state(settings.MEDIA_ROOT, edition.cover.name) == 'ready'):
            available[work.pk] = work
    for work in works:
        if not needs_cover(work):
            continue
        current = identity(work)
        matches = []
        for entry in reviewed.get(work.pk, []):
            source = available.get(entry['source_work_id'])
            if (source and reviewed_equivalent(current, identity(source), entry)
                    and source.default_edition_id == entry['source_edition_id']
                    and source.default_edition.cover.name == entry['source_cover']):
                matches.append((source, entry))
        if matches:
            source, evidence = matches[0]
            yield work, source_pin(source), evidence


def ingest(item, pin, evidence):
    from django.conf import settings
    from django.db import transaction
    from backend.core.models import Work
    from research.enrich_media_alternatives import save_match, validate_image
    with transaction.atomic():
        # Both identities and source provenance are pinned before reading bytes.
        locked = {work.pk: work for work in Work.objects.select_for_update().filter(
            pk__in=[item['id'], pin['identity']['id']]).select_related('default_edition').prefetch_related('authors')}
        source, target = locked.get(pin['identity']['id']), locked.get(item['id'])
        if (not source or not target or source.is_archived or target.is_archived
                or not source.default_edition or source.default_edition.is_archived
                or source_pin(source) != pin or identity(target) != item['_catalog_identity']):
            return 'identity_review_changed_during_lookup', {}
        blob = read_cover(settings.MEDIA_ROOT, pin['cover'])
        validate_image(blob)
        digest = hashlib.sha256(blob).hexdigest()
        if digest != evidence['source_sha256']:
            return 'identity_review_source_image_changed', {}
        details = {'source_work_id': source.pk, 'source_edition_id': source.default_edition_id,
                   'source_cover': pin['cover'], 'source_sha256': digest,
                   'equivalence': evidence, 'original_cover_basis': pin['basis']}
        match = {'blob': blob, 'source': pin['source'],
                 'credit': pin['credit'] or 'Existing catalog cover; original image attribution was not recorded.',
                 'cover_basis': 'unknown' if pin['basis'] == 'unknown' else 'representative_work'}
        return save_match('catalog-covers', item, match), details


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--summary-file', type=Path, default=ROOT / 'research/_runs/media-completion/catalog-covers-stats.json')
    args = parser.parse_args()
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.config.settings')
    import django
    django.setup()
    from django.db.models import Prefetch
    from backend.core.models import Work, Edition
    from backend.core.search import aliases
    from research.enrichment_queue import Queue, exclusive
    from research.enrich_catalog_covers_public import cover_lookup_item
    from research.operational_state import atomic_state
    works = list(Work.objects.filter(is_archived=False).select_related('default_edition').prefetch_related(
        'authors', Prefetch('editions', queryset=Edition.objects.filter(is_archived=False), to_attr='media_editions')))
    found = list(opportunities(works, load_registry()))
    if not args.apply:
        print(json.dumps([{'work_id': work.pk, 'title': work.title, **pin, 'equivalence': evidence}
                          for work, pin, evidence in found], ensure_ascii=False, indent=2))
        return
    ledger = ROOT / 'research/_runs/media-completion/catalog-covers.jsonl'
    ledger.parent.mkdir(parents=True, exist_ok=True)
    stats = {'processed': 0, 'covered': 0, 'queued': len(found)}
    with exclusive('media-alternatives'), exclusive('covers'), ledger.open('a') as audit:
        queue = Queue('catalog-covers', ledger)
        known_aliases = aliases()
        for work, pin, evidence in found:
            item = cover_lookup_item(work, known_aliases)
            item['_catalog_identity'] = identity(work)
            revision = hashlib.sha256(json.dumps([pin, evidence], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            item['provider_identifiers']['catalog_cover'] = revision
            if not queue.due(item, POLICY):
                continue
            result = {'work_id': work.pk, 'title': work.title, 'provider': 'catalog-covers'}
            try:
                result['status'], details = ingest(item, pin, evidence)
                result.update(details)
            except (OSError, ValueError) as error:
                result.update(status='source_image_error', reason=str(error)[:200])
            queue.finish(item, result, audit)
            stats['processed'] += 1
            stats['covered'] += result['status'] == 'covered'
            atomic_state(args.summary_file, stats)
            print(json.dumps({key: result[key] for key in ('work_id', 'title', 'status')}), flush=True)
            if args.limit and stats['processed'] >= args.limit:
                break
        stats.update(queue.summary())
    atomic_state(args.summary_file, stats)


if __name__ == '__main__':
    main()
