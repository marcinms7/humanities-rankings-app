"""Crash-safe worker state, independent of Django and the catalog database."""
import json
import math
import errno
import os
from pathlib import Path
import tempfile
import time


def atomic_state(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.partial', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            try:
                os.fsync(directory)
            except OSError as error:
                if error.errno not in {errno.EINVAL, errno.ENOTSUP}:
                    raise
        finally:
            os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)


def read_state(path, cooldown=False):
    if not path or not Path(path).exists():
        return {}
    try:
        value = json.loads(Path(path).read_text())
        if not isinstance(value, dict):
            raise ValueError('State must be an object.')
        if cooldown and (type(value.get('until')) not in (int, float) or not math.isfinite(value['until']) or value['until'] < 0):
            raise ValueError('Cooldown needs a valid timestamp.')
        return value
    except (ValueError, OSError, TypeError):
        result = {'invalid_state': True}
        if cooldown:
            result.update(until=time.time() + 900, reason='Unreadable cooldown record; requests remain paused until it is repaired.')
        return result
