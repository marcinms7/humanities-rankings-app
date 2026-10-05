"""Export public catalog media metadata without changing originals or records."""
from collections import defaultdict
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from PIL import Image, UnidentifiedImageError

from backend.core.local_backups import atomic_json
from backend.core.models import Edition, Person, Work


RASTER_FORMATS = {'JPEG', 'PNG', 'GIF', 'WEBP', 'TIFF', 'BMP', 'ICO', 'AVIF'}
# Internet Archive's generic item-image logo, visually audited on 2026-10-05.
# Retain the original and its associations, but never count it as a usable cover.
KNOWN_PLACEHOLDER_HASHES = {'f84e75694fef8121d7fed94ab7f1a92751e48188e512d66207498f6825fc9408'}


class MediaReadError(Exception):
    pass


def reference_path(value, kind):
    if not isinstance(value, str) or '\\' in value:
        return None
    path = PurePosixPath(value)
    if (path.is_absolute() or '..' in path.parts or len(path.parts) < 2
            or path.parts[0] != kind or path.as_posix() != value):
        return None
    return path.as_posix()


def public_references(include_portraits):
    """Release the short database snapshot before decoding/hashing any files."""
    references = defaultdict(list)
    errors = []
    with transaction.atomic():
        snapshot_at = timezone.now().isoformat()
        editions = list(Edition.objects.exclude(cover='').order_by('pk').values(
            'id', 'work_id', 'cover', 'is_archived', 'language', 'translator', 'publisher', 'isbn',
            'cover_basis', 'source_url', 'cover_source_url', 'image_attribution',
            'work__title', 'work__is_archived', 'work__default_edition_id'))
        authors = defaultdict(list)
        work_ids = {row['work_id'] for row in editions}
        for row in Work.objects.filter(pk__in=work_ids).order_by('pk', 'authors__pk').values(
                'id', 'authors__id', 'authors__name', 'authors__is_archived'):
            if row['authors__id'] is not None:
                authors[row['id']].append({'id': row['authors__id'], 'name': row['authors__name'],
                                           'is_archived': row['authors__is_archived']})
        portraits = list(Person.objects.exclude(portrait='').order_by('pk').values(
            'id', 'name', 'is_archived', 'portrait', 'source_url', 'image_attribution')) if include_portraits else []
    for row in editions:
        association = {'edition_id': row['id'], 'work_id': row['work_id'],
                       'work_title': row['work__title'], 'authors': authors[row['work_id']],
                       'is_default_edition': row['id'] == row['work__default_edition_id'],
                       'edition_is_archived': row['is_archived'], 'work_is_archived': row['work__is_archived'],
                       **{key: row[key] for key in ('language', 'translator', 'publisher', 'isbn',
                           'cover_basis', 'source_url', 'cover_source_url', 'image_attribution')}}
        path = reference_path(row['cover'], 'covers')
        if path:
            references[path].append(association)
        else:
            errors.append({'path': None, 'kind': 'cover', 'reason': 'unsafe_or_out_of_scope_reference',
                           'associations': [association]})
    for row in portraits:
        association = {'person_id': row['id'], **{key: row[key] for key in (
            'name', 'is_archived', 'source_url', 'image_attribution')}}
        path = reference_path(row['portrait'], 'portraits')
        if path:
            references[path].append(association)
        else:
            errors.append({'path': None, 'kind': 'portrait', 'reason': 'unsafe_or_out_of_scope_reference',
                           'associations': [association]})
    return snapshot_at, references, errors


def read_original(root, relative):
    """Open every component without following symlinks, then verify and hash."""
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parts = PurePosixPath(relative).parts
        for component in parts[:-1]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    finally:
        os.close(directory)
    with os.fdopen(descriptor, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise MediaReadError('not_a_regular_file')
        try:
            with Image.open(stream) as image:
                image_format, width, height = image.format, image.width, image.height
                if image_format not in RASTER_FORMATS:
                    raise MediaReadError('unsupported_image_format')
                image.verify()
            stream.seek(0)
            with Image.open(stream) as image:
                image.load()
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError) as error:
            raise MediaReadError('invalid_raster') from error
        stream.seek(0)
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
        after = os.fstat(stream.fileno())
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise MediaReadError('changed_during_read')
    return {'size': before.st_size, 'sha256': digest.hexdigest(), 'format': image_format,
            'width': width, 'height': height}


class Command(BaseCommand):
    help = 'Export a public, verified cover manifest; optionally include catalog portraits. Never changes catalog data.'

    def add_arguments(self, parser):
        parser.add_argument('--output', type=Path, required=True, help='JSON destination outside original covers/portraits directories.')
        parser.add_argument('--include-portraits', action='store_true', help='Include publicly credited catalog portraits.')

    def handle(self, *args, **options):
        root = Path(settings.MEDIA_ROOT).resolve()
        output = Path(options['output']).expanduser()
        output_paths = (Path(os.path.abspath(output)), output.resolve())
        if any(path.is_relative_to(root / kind) for path in output_paths for kind in ('covers', 'portraits')):
            raise CommandError('Manifest output must not overwrite original media directories.')
        snapshot_at, references, errors = public_references(options['include_portraits'])
        kinds = ['covers', 'portraits'] if options['include_portraits'] else ['covers']
        discovered, excluded_symlinks, skipped = set(), [], []
        for kind in kinds:
            directory = root / kind
            if directory.is_symlink():
                excluded_symlinks.append(kind)
                continue
            def scan_error(error):
                path = Path(error.filename) if error.filename else directory
                errors.append({'path': path.relative_to(root).as_posix(), 'reason': 'directory_unreadable'})
            for parent, dirs, files in os.walk(directory, followlinks=False, onerror=scan_error):
                for name in list(dirs):
                    path = Path(parent) / name
                    if path.is_symlink():
                        excluded_symlinks.append(path.relative_to(root).as_posix())
                        dirs.remove(name)
                for name in files:
                    path = Path(parent) / name
                    relative = path.relative_to(root).as_posix()
                    if path.is_symlink():
                        excluded_symlinks.append(relative)
                    else:
                        discovered.add(relative)
        files = []
        # Include explicit references even when enumeration missed the path,
        # so missing/inaccessible images cannot silently disappear.
        for path in sorted(discovered | set(references)):
            associations = references.get(path, [])
            kind = 'cover' if path.startswith('covers/') else 'portrait'
            try:
                metadata = read_original(root, path)
            except MediaReadError as error:
                if associations or str(error) == 'changed_during_read':
                    errors.append({'path': path, 'kind': kind, 'reason': str(error), 'associations': associations})
                else:
                    skipped.append({'path': path, 'reason': str(error)})
                continue
            except OSError as error:
                reason = ('missing_file' if isinstance(error, FileNotFoundError) else 'unreadable_or_unsafe_file')
                errors.append({'path': path, 'kind': kind, 'reason': reason, 'associations': associations})
                continue
            placeholder = metadata['sha256'] in KNOWN_PLACEHOLDER_HASHES
            files.append({'path': path, 'kind': kind, **metadata, 'associations': associations,
                          'association_status': 'referenced' if associations else 'unreferenced',
                          'quality': 'known_placeholder' if placeholder else 'validated_raster',
                          'usable': not placeholder})
        manifest = {
            'schema': 'marginalia.catalog-media-manifest', 'version': 1, 'snapshot_at': snapshot_at,
            'include_portraits': options['include_portraits'], 'complete': not errors,
            'summary': {'file_count': len(files), 'cover_count': sum(row['kind'] == 'cover' for row in files),
                        'portrait_count': sum(row['kind'] == 'portrait' for row in files),
                        'usable_cover_count': sum(row['kind'] == 'cover' and row['usable'] for row in files),
                        'known_placeholder_count': sum(not row['usable'] for row in files),
                        'unreferenced_file_count': sum(not row['associations'] for row in files),
                        'skipped_nonimage_count': len(skipped),
                        'excluded_symlink_count': len(excluded_symlinks), 'error_count': len(errors)},
            'files': files, 'skipped_nonimages': skipped,
            'excluded_symlinks': sorted(excluded_symlinks), 'errors': errors,
        }
        try:
            atomic_json(output, manifest)
        except OSError as error:
            raise CommandError(f'Could not write manifest: {type(error).__name__}.') from error
        if errors:
            raise CommandError(f'Incomplete media manifest: {len(errors)} error(s); inspect {output}.')
        self.stdout.write(f'Exported {len(files)} verified original(s); '
                          f'{manifest["summary"]["unreferenced_file_count"]} unreferenced; '
                          f'{manifest["summary"]["known_placeholder_count"]} known placeholder(s): {output}')
