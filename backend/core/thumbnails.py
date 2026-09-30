"""On-demand bounded WebP derivatives; original media and credits stay intact."""
import hashlib
import os
from pathlib import Path
import tempfile
from urllib.parse import quote
import warnings

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponseNotModified
from django.views.decorators.http import require_safe
from PIL import Image, ImageOps, UnidentifiedImageError

SIZES = {96, 240, 480}


def source_file(name):
    if not name or Path(name).is_absolute() or '..' in Path(name).parts or Path(name).parts[0] not in {'covers', 'portraits'}:
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


@require_safe
def thumbnail(request, size, filename):
    if size not in SIZES:
        raise Http404('Image size not available.')
    source, version = source_file(filename)
    etag = f'"{version}-{size}"'
    if request.headers.get('If-None-Match') == etag:
        response = HttpResponseNotModified()
    else:
        directory = Path(settings.BASE_DIR) / 'data' / 'thumbnail-cache'
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        target = directory / f'{version}-{size}.webp'
        if not target.is_file():
            temporary = None
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter('error', Image.DecompressionBombWarning)
                    with Image.open(source) as original:
                        if original.width * original.height > 40_000_000:
                            raise ValueError('Image is too large for a preview.')
                        original.seek(0)
                        picture = ImageOps.exif_transpose(original).convert('RGB')
                        picture.thumbnail((size, size * 2), Image.Resampling.LANCZOS)
                        with tempfile.NamedTemporaryFile(dir=directory, suffix='.webp', delete=False) as output:
                            temporary = output.name
                            picture.save(output, format='WEBP', quality=82, method=4)
                        os.replace(temporary, target)
            except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
                raise Http404('Image preview unavailable.') from error
            finally:
                if temporary and os.path.exists(temporary):
                    os.unlink(temporary)
        response = FileResponse(target.open('rb'), content_type='image/webp')
    response['ETag'] = etag
    response['Cache-Control'] = 'public, max-age=31536000, immutable' if request.GET.get('v') == version else 'public, max-age=300'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
