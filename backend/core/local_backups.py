"""Atomic SQLite snapshots and shared media objects; no deletion/pruning."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile


def digest_file(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        try:
            os.fsync(descriptor)
        except OSError as error:
            if error.errno not in {errno.EINVAL, errno.ENOTSUP}:
                raise
    finally:
        os.close(descriptor)


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.partial', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def read_json(path):
    try:
        value = json.loads(Path(path).read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


@contextmanager
def backup_lock(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / '.backup.lock').open('a') as lock:
        os.chmod(lock.name, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def object_path(directory, sha256):
    if not isinstance(sha256, str) or len(sha256) != 64 or any(char not in '0123456789abcdef' for char in sha256):
        raise ValueError('Invalid media-object digest.')
    return Path(directory) / 'media-objects' / sha256[:2] / sha256


def safe_media_path(root, relative):
    path = Path(relative)
    if not relative or path.is_absolute() or '..' in path.parts:
        raise ValueError('Unsafe media path in backup manifest.')
    target = (Path(root) / path).resolve()
    if not target.is_relative_to(Path(root).resolve()):
        raise ValueError('Media path escapes its storage root.')
    return target


def _signature(stat):
    return {'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns, 'ctime_ns': stat.st_ctime_ns,
            'inode': stat.st_ino, 'device': stat.st_dev}


def _save_media_object(path, directory, old):
    signature = _signature(path.stat())
    if old and all(old.get(key) == value for key, value in signature.items()):
        obj = object_path(directory, old['sha256'])
        if obj.is_file() and obj.stat().st_size == signature['size']:
            return {**signature, 'sha256': old['sha256']}, False
    objects = Path(directory) / 'media-objects'
    objects.mkdir(parents=True, exist_ok=True, mode=0o700)
    for _ in range(3):
        before = _signature(path.stat())
        descriptor, temporary = tempfile.mkstemp(prefix='.media-', dir=objects)
        digest = hashlib.sha256()
        try:
            with os.fdopen(descriptor, 'wb') as target, path.open('rb') as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b''):
                    target.write(chunk); digest.update(chunk)
                target.flush(); os.fsync(target.fileno())
            after = _signature(path.stat())
            if before != after:
                continue
            sha = digest.hexdigest()
            obj = object_path(directory, sha)
            obj.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            added = not obj.exists()
            if obj.exists() and digest_file(obj) != sha:
                raise ValueError('An existing backup media object failed its checksum; originals were preserved.')
            if added:
                os.replace(temporary, obj); fsync_directory(obj.parent)
            return {**after, 'sha256': sha}, added
        finally:
            Path(temporary).unlink(missing_ok=True)
    raise ValueError('A media file kept changing during the backup; retry after this write finishes.')


def backup_manifest(stem):
    stem = Path(stem)
    manifest = read_json(stem.with_suffix('.media.json'))
    if manifest.get('version') != 2 or not isinstance(manifest.get('files'), dict):
        raise ValueError('A version 2 media manifest is required.')
    marker = read_json(stem.with_suffix('.complete'))
    if marker.get('manifest_sha256') != digest_file(stem.with_suffix('.media.json')):
        raise ValueError('The backup manifest checksum does not match its completion record.')
    return manifest


def create_snapshot(source, media, directory, name):
    source, media, directory = Path(source), Path(media), Path(directory)
    if directory.resolve().is_relative_to(media.resolve()):
        raise ValueError('The backup directory must be outside the media directory.')
    stem = directory / name
    if stem.with_suffix('.complete').exists():
        if not stem.with_suffix('.sqlite3').is_file():
            raise ValueError('The completed backup is missing its database; create a fresh manual snapshot.')
        if read_json(stem.with_suffix('.complete')).get('version') == 2:
            existing = backup_manifest(stem)
            if digest_file(stem.with_suffix('.sqlite3')) != existing['database']['sha256']:
                raise ValueError('The completed backup database failed its checksum; create a fresh manual snapshot.')
        return {'name': name, 'skipped': True, 'format': 'content-addressed' if stem.with_suffix('.media.json').exists() else 'legacy-tar'}
    source_hash = hashlib.sha256(str(source.resolve()).encode()).hexdigest()
    media_hash = hashlib.sha256(str(media.resolve()).encode()).hexdigest()
    previous = {}
    for marker in sorted(directory.glob('*.complete'), key=lambda p: p.stat().st_mtime, reverse=True):
        candidate = read_json(marker.with_suffix('.media.json'))
        if candidate.get('media_root_fingerprint') == media_hash:
            previous = candidate.get('files') or {}
            break
    descriptor, temporary = tempfile.mkstemp(prefix=f'.{name}.', suffix='.sqlite3.partial', dir=directory)
    os.close(descriptor)
    files, added = {}, 0
    try:
        with sqlite3.connect(f'{source.resolve().as_uri()}?mode=ro', uri=True) as src, sqlite3.connect(temporary) as dst:
            src.backup(dst)
        with open(temporary, 'rb') as snapshot:
            os.fsync(snapshot.fileno())
        if media.exists():
            for parent, directories, names in os.walk(media):
                if any((Path(parent) / dirname).is_symlink() for dirname in directories):
                    raise ValueError('Symlinked media directories need an explicit backup policy; originals were preserved.')
                for filename in sorted(names):
                    path = Path(parent) / filename
                    if path.is_symlink() or not path.is_file():
                        raise ValueError('Media backups require regular files, not symlinks or special files.')
                    relative = path.relative_to(media).as_posix()
                    files[relative], is_new = _save_media_object(path, directory, previous.get(relative))
                    added += is_new
        with sqlite3.connect(f'{Path(temporary).as_uri()}?mode=ro', uri=True) as snapshot:
            missing = 0
            tables = {row[0] for row in snapshot.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table, field in [('core_edition', 'cover'), ('core_person', 'portrait')]:
                if table in tables:
                    missing += sum(value not in files for (value,) in snapshot.execute(f'SELECT {field} FROM {table} WHERE {field} != ?', ('',)))
            if missing:
                raise ValueError(f'The database snapshot references {missing} missing media files; the incomplete snapshot was not published.')
        database_path = stem.with_suffix('.sqlite3')
        os.replace(temporary, database_path)
        created_at = datetime.now(timezone.utc).isoformat()
        manifest = {'version': 2, 'created_at': created_at, 'database_fingerprint': source_hash,
                    'media_root_fingerprint': media_hash, 'database': {'sha256': digest_file(database_path), 'size': database_path.stat().st_size},
                    'files': files, 'media_files': len(files), 'media_bytes': sum(row['size'] for row in files.values()), 'new_objects': added}
        atomic_json(stem.with_suffix('.media.json'), manifest)
        atomic_json(stem.with_suffix('.complete'), {'version': 2, 'created_at': created_at,
                    'manifest_sha256': digest_file(stem.with_suffix('.media.json'))})
        return {'name': name, 'skipped': False, 'format': 'content-addressed', 'media_files': len(files), 'new_objects': added}
    finally:
        Path(temporary).unlink(missing_ok=True)


def _atomic_copy(source, destination, expected=None):
    source, destination = Path(source), Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    expected = expected or digest_file(source)
    if destination.is_file() and digest_file(destination) == expected:
        return
    descriptor, temporary = tempfile.mkstemp(prefix=f'.{destination.name}.', dir=destination.parent)
    try:
        with source.open('rb') as src, os.fdopen(descriptor, 'wb') as target:
            shutil.copyfileobj(src, target, length=1024 * 1024)
            target.flush(); os.fsync(target.fileno())
        if digest_file(temporary) != expected:
            raise ValueError('Copied backup failed its checksum.')
        os.replace(temporary, destination); fsync_directory(destination.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def copy_snapshot(stem, destination):
    stem, destination = Path(stem), Path(destination).expanduser().resolve()
    if not destination.is_dir():
        raise ValueError('The configured backup copy destination is unavailable; mount/create it before copying.')
    if destination == stem.parent.resolve() or destination.is_relative_to(stem.parent.resolve()):
        raise ValueError('The backup copy destination must be outside the local backup directory.')
    with backup_lock(destination):
        if stem.with_suffix('.media.json').exists():
            manifest = backup_manifest(stem)
            for record in manifest['files'].values():
                _atomic_copy(object_path(stem.parent, record['sha256']), object_path(destination, record['sha256']), record['sha256'])
            _atomic_copy(stem.with_suffix('.media.json'), destination / f'{stem.name}.media.json')
            _atomic_copy(stem.with_suffix('.sqlite3'), destination / f'{stem.name}.sqlite3', manifest['database']['sha256'])
        else:
            _atomic_copy(stem.with_suffix('.sqlite3'), destination / f'{stem.name}.sqlite3')
            if stem.with_suffix('.media.tar.gz').exists():
                _atomic_copy(stem.with_suffix('.media.tar.gz'), destination / f'{stem.name}.media.tar.gz')
        _atomic_copy(stem.with_suffix('.complete'), destination / f'{stem.name}.complete')
    return {'configured': True, 'status': 'copied', 'snapshot': stem.name,
            'finished_at': datetime.now(timezone.utc).isoformat(),
            'separate_device': destination.stat().st_dev != stem.parent.stat().st_dev}


def restore_media(stem, destination):
    """Restore v2 objects; caller retains legacy tar handling."""
    stem, destination = Path(stem), Path(destination)
    manifest = backup_manifest(stem)
    if digest_file(stem.with_suffix('.sqlite3')) != manifest['database']['sha256']:
        raise ValueError('The database backup checksum does not match its manifest.')
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    for relative, record in manifest['files'].items():
        target = safe_media_path(destination, relative)
        if target.exists():
            raise ValueError('Restore destination already contains a media file.')
        _atomic_copy(object_path(stem.parent, record['sha256']), target, record['sha256'])
    return len(manifest['files'])
