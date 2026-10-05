"""Offline worker control flow; catalog, queue and provider I/O are mocked."""
from contextlib import ExitStack, redirect_stdout
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from research import enrich_catalog_portraits as portraits
from research import enrichment_queue
from research.media_transport import ProviderOutage


class PortraitBatchTests(unittest.TestCase):
    def test_image_outage_defers_only_affected_people_and_continues_later_batches(self):
        items = [{'id': index, 'title': f'Writer {index}', 'works': ['A known work']}
                 for index in range(1, 13)]
        queryset = MagicMock()
        queryset.prefetch_related.return_value = queryset
        queryset.annotate.return_value = queryset
        queryset.order_by.return_value = items
        person = MagicMock()
        person.objects.filter.return_value = queryset
        queue = MagicMock()
        queue.due.return_value = True
        queue.priority.side_effect = lambda item: item['id']
        queue.batch_errors = 0
        queue.summary.return_value = {'states': {}, 'next_retry': None}
        store = MagicMock()
        store.get.return_value = [{'image_url': 'https://thumb.wikimedia.org/image.jpg'}]
        image = {'blob': b'validated-image', 'extension': 'jpg', 'credit': 'Preserved credit',
                 'source': 'https://commons.wikimedia.org/wiki/File:Portrait.jpg'}
        until = portraits.time.time() + 900
        rate_limit = ProviderOutage('HTTP 429', retry_after=until, status=429)
        lag = ProviderOutage('Provider returned an API error: maxlag',
                            retry_after=until + 10, status=200, outage_type='maxlag')
        modules = {
            'django': SimpleNamespace(setup=lambda: None),
            'django.db.models': SimpleNamespace(Count=lambda *a, **k: 0, Q=lambda **k: 0),
            'backend.core.models': SimpleNamespace(Person=person),
            'backend.core.search': SimpleNamespace(aliases=lambda: {}),
        }
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            run = Path(directory)
            replacements = {
                'RUN': run, 'LEDGER': run / 'outcomes.jsonl', 'COOLDOWN': run / 'cooldown.json',
                'Queue': MagicMock(return_value=queue), 'CandidateStore': MagicMock(return_value=store),
                'portrait_lookup_item': lambda item, aliases: item,
                'wikimedia_candidates': MagicMock(side_effect=AssertionError('New metadata after outage')),
                'download_candidates': MagicMock(side_effect=[rate_limit, image, lag] + [None] * 9),
                'save_match': MagicMock(return_value='covered'),
            }
            for name, replacement in replacements.items():
                stack.enter_context(patch.object(portraits, name, replacement))
            stack.enter_context(patch.dict(sys.modules, modules))
            stack.enter_context(patch.dict(os.environ, {}))
            stack.enter_context(patch.object(sys, 'argv', ['portraits', '--limit', '12']))
            stack.enter_context(redirect_stdout(io.StringIO()))
            portraits.main()
            stats = json.loads((run / 'latest-stats.json').read_text())
            self.assertFalse((run / 'cooldown.json').exists())
        self.assertEqual(queue.finish.call_count, 12)
        self.assertEqual(store.get.call_count, 12)
        replacements['wikimedia_candidates'].assert_not_called()
        replacements['save_match'].assert_called_once()
        records = [call.args[1] for call in queue.finish.call_args_list]
        self.assertEqual([record['status'] for record in records[:3]],
                         ['image_deferred', 'covered', 'image_deferred'])
        self.assertEqual(stats['portraits'], 1)
        self.assertEqual(stats['processed'], 12)
        self.assertEqual(stats['image_deferred'], 2)
        self.assertEqual(stats['provider_errors'], 0)
        self.assertFalse(stats.get('provider_outage', False))
        self.assertEqual(records[0]['retry_after'], until)
        self.assertEqual(records[2]['retry_after'], until + 10)
        self.assertEqual(records[0]['outage_stage'], 'image')

    def test_metadata_outage_preserves_cached_images_and_leaves_other_people_unattempted(self):
        items = [{'id': index, 'title': f'Writer {index}', 'works': ['A known work']}
                 for index in range(1, 13)]
        queryset = MagicMock()
        queryset.prefetch_related.return_value = queryset
        queryset.annotate.return_value = queryset
        queryset.order_by.return_value = items
        person = MagicMock()
        person.objects.filter.return_value = queryset
        queue = MagicMock()
        queue.due.return_value = True
        queue.priority.side_effect = lambda item: item['id']
        queue.batch_errors = 0
        queue.summary.return_value = {'states': {}, 'next_retry': None}
        store = MagicMock()
        # This ready image is outside the first ten by ordinary priority.
        store.get.side_effect = lambda item: [{'image_url': 'https://thumb.wikimedia.org/image.jpg'}] if item['id'] == 12 else None
        image = {'blob': b'validated-image', 'extension': 'jpg', 'credit': 'Preserved credit',
                 'source': 'https://commons.wikimedia.org/wiki/File:Portrait.jpg'}
        until = portraits.time.time() + 900
        modules = {
            'django': SimpleNamespace(setup=lambda: None),
            'django.db.models': SimpleNamespace(Count=lambda *a, **k: 0, Q=lambda **k: 0),
            'backend.core.models': SimpleNamespace(Person=person),
            'backend.core.search': SimpleNamespace(aliases=lambda: {}),
        }
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            run = Path(directory)
            replacements = {
                'RUN': run, 'LEDGER': run / 'outcomes.jsonl', 'COOLDOWN': run / 'cooldown.json',
                'Queue': MagicMock(return_value=queue), 'CandidateStore': MagicMock(return_value=store),
                'portrait_lookup_item': lambda item, aliases: item,
                'wikimedia_candidates': MagicMock(side_effect=ProviderOutage('HTTP 429', retry_after=until, status=429)),
                'download_candidates': MagicMock(return_value=image),
                'save_match': MagicMock(return_value='covered'),
            }
            for name, replacement in replacements.items():
                stack.enter_context(patch.object(portraits, name, replacement))
            stack.enter_context(patch.dict(sys.modules, modules))
            stack.enter_context(patch.dict(os.environ, {}))
            stack.enter_context(patch.object(sys, 'argv', ['portraits', '--limit', '12']))
            stack.enter_context(redirect_stdout(io.StringIO()))
            portraits.main()
            stats = json.loads((run / 'latest-stats.json').read_text())
            cooldown = json.loads((run / 'cooldown.json').read_text())
        self.assertEqual(queue.finish.call_count, 2)
        replacements['wikimedia_candidates'].assert_called_once()
        replacements['download_candidates'].assert_called_once()
        self.assertEqual(replacements['save_match'].call_args.args[1]['id'], 12)
        self.assertTrue(stats['provider_outage'])
        self.assertEqual(stats['portraits'], 1)
        self.assertEqual(cooldown['until'], until)

    def test_partial_discovery_caches_only_completed_people_and_preserves_retry_budgets(self):
        items = [{'id': identity, 'title': f'Writer {identity}', 'works': ['A known work']}
                 for identity in range(1, 13)]
        queryset = MagicMock()
        queryset.prefetch_related.return_value = queryset
        queryset.annotate.return_value = queryset
        queryset.order_by.return_value = items
        person = MagicMock()
        person.objects.filter.return_value = queryset
        store = MagicMock()
        store.get.return_value = None
        store.put.side_effect = lambda item, candidates: candidates
        image = {'blob': b'validated-image', 'extension': 'jpg', 'credit': 'Preserved credit',
                 'source': 'https://commons.wikimedia.org/wiki/File:Portrait.jpg'}
        partial = portraits.DiscoveryResult(items[:10])
        partial[1] = [{'image_url': 'https://thumb.wikimedia.org/image.jpg'}]
        partial.completed.update({1, 2})
        partial.interrupt(ProviderOutage('HTTP 429', status=429))
        modules = {
            'django': SimpleNamespace(setup=lambda: None),
            'django.db.models': SimpleNamespace(Count=lambda *a, **k: 0, Q=lambda **k: 0),
            'backend.core.models': SimpleNamespace(Person=person),
            'backend.core.search': SimpleNamespace(aliases=lambda: {}),
        }
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            run = Path(directory)
            stack.enter_context(patch.object(enrichment_queue, 'STATE', run / 'queues'))
            replacements = {
                'RUN': run, 'LEDGER': run / 'outcomes.jsonl', 'COOLDOWN': run / 'cooldown.json',
                'CandidateStore': MagicMock(return_value=store),
                'portrait_lookup_item': lambda item, aliases: item,
                'wikimedia_candidates': MagicMock(return_value=partial),
                'download_candidates': MagicMock(side_effect=lambda candidates, **kwargs: image if candidates else None),
                'save_match': MagicMock(return_value='covered'),
            }
            for name, replacement in replacements.items():
                stack.enter_context(patch.object(portraits, name, replacement))
            stack.enter_context(patch.dict(sys.modules, modules))
            stack.enter_context(patch.dict(os.environ, {}))
            stack.enter_context(patch.object(sys, 'argv', ['portraits', '--limit', '12']))
            stack.enter_context(redirect_stdout(io.StringIO()))
            portraits.main()
            stats = json.loads((run / 'latest-stats.json').read_text())
            with sqlite3.connect(run / 'queues/portraits.sqlite3') as db:
                rows = {identity: (attempts, state) for identity, attempts, state in
                        db.execute('SELECT work_id, attempts, state FROM attempts')}
            ledger = [json.loads(line) for line in (run / 'outcomes.jsonl').read_text().splitlines()]
        self.assertEqual([call.args[0]['id'] for call in store.put.call_args_list], [1, 2])
        self.assertEqual(rows[1], (1, 'complete'))
        self.assertEqual(rows[2], (1, 'unresolved'))
        self.assertTrue(all(rows[identity] == (0, 'provider_wait') for identity in range(3, 11)))
        self.assertTrue(all(rows[identity] == (0, 'pending') for identity in (11, 12)))
        self.assertEqual(len(ledger), 10)
        self.assertEqual(stats['portraits'], 1)
        self.assertTrue(stats['provider_outage'])
        replacements['wikimedia_candidates'].assert_called_once()
        replacements['save_match'].assert_called_once()
