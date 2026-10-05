"""Prewarmed, bounded WebP derivatives with an on-demand fallback."""
import hashlib
import logging
import os
from pathlib import Path
import tempfile
from urllib.parse import quote
import warnings

from django.conf import settings
from django.core.files import locks
from django.db import transaction
from django.db.models.signals import post_save
from django.http import FileResponse, Http404, HttpResponseNotModified
from django.views.decorators.http import require_safe
from PIL import Image, ImageOps, UnidentifiedImageError

SIZES = {96, 240, 480}
logger = logging.getLogger(__name__)


def source_file(name):
    parts = Path(name).parts if name else ()
    if not parts or Path(name).is_absolute() or '..' in parts or parts[0] not in {'covers', 'portraits'}:
        raise Http404('Image not available.')
    root = Path(settings.MEDIA_ROOT).resolve()
    source = (root / name).resolve()
    if not source.is_relative_to(root) or source.suffix.lower() not in {'.jpg', '.jpeg', '.png', '.webp', '.gif'}:
        raise Http404('Image not available.')
    try:
        stat = source.stat()
    except OSError as error:
        raise Http404('Image not available.') from error
    if not source.is_file():
        raise Http404('Image not available.')
    return source, hashlib.sha256(f'{name}:{stat.st_mtime_ns}:{stat.st_size}'.encode()).hexdigest()[:24]


def thumbnail_url(field, size=240):
    if not field:
        return None
    name = str(field)
    try:
        _, version = source_file(name)
    except Http404:
        return None
    return f'/media-preview/{size}/{quote(name, safe="/")}?v={version}'


def prepare_thumbnails(filename, sizes=None):
    """Return (source version, size/path mapping, created count), without DB writes.

    A version-specific file lock coordinates web requests and separate ingestion
    processes. Atomic replacement keeps readers from seeing partial derivatives.
    Cached images take the stat-only path without opening or decoding the source.
    """
    sizes = set(SIZES if sizes is None else sizes)
    if not sizes or not sizes <= SIZES:
        raise ValueError('Image size not available.')
    directory = Path(settings.BASE_DIR) / 'data' / 'thumbnail-cache'
    for _ in range(3):
        source, version = source_file(filename)
        targets = {size: directory / f'{version}-{size}.webp' for size in sorted(sizes)}
        if all(target.is_file() for target in targets.values()):
            return version, targets, 0
        temporary = None
        try:
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            # Keep the lock file: unlinking it would allow competing processes
            # to lock different inodes while an existing waiter still holds it.
            with (directory / f'{version}.lock').open('a+b') as lock:
                if not locks.lock(lock, locks.LOCK_EX):
                    raise OSError('Could not lock the thumbnail cache.')
                try:
                    if source_file(filename)[1] != version:
                        continue
                    missing = {size: target for size, target in targets.items() if not target.is_file()}
                    if not missing:
                        return version, targets, 0
                    with warnings.catch_warnings():
                        warnings.simplefilter('error', Image.DecompressionBombWarning)
                        with Image.open(source) as original:
                            if original.width * original.height > 40_000_000:
                                raise ValueError('Image is too large for a preview.')
                            original.seek(0)
                            picture = ImageOps.exif_transpose(original).convert('RGB')
                        with picture:
                            for size, target in missing.items():
                                with picture.copy() as preview:
                                    preview.thumbnail((size, size * 2), Image.Resampling.LANCZOS)
                                    with tempfile.NamedTemporaryFile(dir=directory, suffix='.webp', delete=False) as output:
                                        temporary = output.name
                                        preview.save(output, format='WEBP', quality=82, method=4)
                                if source_file(filename)[1] != version:
                                    break
                                os.replace(temporary, target)
                                temporary = None
                            else:
                                return version, targets, len(missing)
                finally:
                    locks.unlock(lock)
        except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
            raise Http404('Image preview unavailable.') from error
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
    raise Http404('Image changed while preparing its preview.')


def _warm_saved_image(sender, instance, raw=False, update_fields=None, using='default', **kwargs):
    field = 'cover' if sender._meta.model_name == 'edition' else 'portrait'
    if raw or (update_fields is not None and field not in update_fields):
        return
    filename = str(getattr(instance, field))
    if not filename:
        return

    def warm():
        try:
            prepare_thumbnails(filename)
        except (Http404, OSError, ValueError):
            # The original save is authoritative. A broken/missing image or an
            # unavailable cache must not make a successful catalog import fail.
            logger.warning('Could not prepare %s image previews for record %s; request fallback remains available.',
                           sender._meta.model_name, instance.pk)

    transaction.on_commit(warm, using=using, robust=True)


def connect_thumbnail_warming():
    from .models import Edition, Person
    for model in (Edition, Person):
        post_save.connect(_warm_saved_image, sender=model, weak=False,
                          dispatch_uid=f'thumbnail-warming-{model._meta.label_lower}')


@require_safe
def thumbnail(request, size, filename):
    if size not in SIZES:
        raise Http404('Image size not available.')
    _, version = source_file(filename)
    etag = f'"{version}-{size}"'
    if request.headers.get('If-None-Match') == etag:
        response = HttpResponseNotModified()
    else:
        version, targets, _ = prepare_thumbnails(filename, {size})
        etag = f'"{version}-{size}"'
        response = FileResponse(targets[size].open('rb'), content_type='image/webp')
    response['ETag'] = etag
    response['Cache-Control'] = 'public, max-age=31536000, immutable' if request.GET.get('v') == version else 'public, max-age=300'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
