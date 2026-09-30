"""Bounded process-local caches containing shared catalog facts only.

SQLite file/WAL generations catch external import writes as well as API edits.
Other engines use model-change signals and a short TTL for external SQL writers.
Permission checks and private context are always evaluated outside these caches.
"""
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path
from threading import RLock
from time import monotonic

from django.db import connection
from django.db.models.signals import m2m_changed, post_delete, post_save

_items = OrderedDict()
_lock = RLock()
_epoch = 0


def invalidate_catalog(**kwargs):
    global _epoch
    with _lock:
        _epoch += 1
        _items.clear()


def database_stamp():
    if connection.vendor == 'sqlite' and str(connection.settings_dict['NAME']) != ':memory:':
        name = str(connection.settings_dict['NAME'])
        result = []
        for suffix in ['', '-wal']:
            try:
                stat = Path(name + suffix).stat()
                result.append((stat.st_mtime_ns, stat.st_size))
            except OSError:
                result.append(None)
        return tuple(result)
    return _epoch


def cached_catalog(key, factory, *, ttl=30, copy=True):
    stamp = database_stamp()
    cache_key = (connection.alias, stamp, key)
    now = monotonic()
    with _lock:
        item = _items.get(cache_key)
        if item and now - item[0] < ttl:
            _items.move_to_end(cache_key)
            return deepcopy(item[1]) if copy else item[1]
    result = factory()
    # A concurrent catalog write must not label an older result as current.
    if database_stamp() == stamp:
        with _lock:
            for old in list(_items):
                if old[0] == cache_key[0] and old[2] == key and old != cache_key:
                    del _items[old]
            _items[cache_key] = (now, result)
            while len(_items) > 32:
                _items.popitem(last=False)
    return deepcopy(result) if copy else result


def connect_catalog_invalidation():
    from .models import Work, Person, Edition, Ranking, RankingEntry, Tag, ResearchSource, CatalogReviewDecision, LibraryItem
    for model in [Work, Person, Edition, Ranking, RankingEntry, Tag, ResearchSource, CatalogReviewDecision, LibraryItem]:
        post_save.connect(invalidate_catalog, sender=model, weak=False, dispatch_uid=f'catalog-save-{model._meta.label}')
        post_delete.connect(invalidate_catalog, sender=model, weak=False, dispatch_uid=f'catalog-delete-{model._meta.label}')
    for model in [Work.authors.through, Work.tags.through]:
        m2m_changed.connect(invalidate_catalog, sender=model, weak=False, dispatch_uid=f'catalog-m2m-{model._meta.label}')
