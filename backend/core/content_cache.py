"""Small revision-aware caches for file-backed editorial curriculum only."""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=24)
def _read(path, modified_ns, size):
    return json.loads(Path(path).read_text())


def read_content(path):
    path = Path(path)
    stat = path.stat()
    # Return a copy: callers combine glossaries and source registers in place.
    return deepcopy(_read(str(path.resolve()), stat.st_mtime_ns, stat.st_size))
