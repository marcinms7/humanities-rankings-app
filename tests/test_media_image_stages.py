"""Image failures retain candidates without blocking independent metadata.

Catalog and HTTP I/O are mocked. Real queues and candidate stores use temporary
directories, so these tests cannot write the owner's catalog or media.
"""
from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from research import enrichment_queue, enrich_media_alternatives as media
from research import media_transport as transport
from research.media_provider_health import outcome


class AlternativeImageStageTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.items = [{'id': index, 'title': f'Writer {index}', 'works': ['A known work']}
                      for index in range(1, 6)]
        queryset = MagicMock()
        queryset.prefetch_related.return_value = queryset
        queryset.annotate.return_value = queryset
        queryset.order_by.return_value = self.items
        person = MagicMock()
        person.objects.filter.return_value = queryset
        modules = {
            'django': SimpleNamespace(setup=lambda: None),
            'django.db.models': SimpleNamespace(Count=lambda *a, **k: 0, Q=lambda **k: 0,
                                               Prefetch=lambda *a, **k: None),
            'backend.core.models': SimpleNamespace(Person=person, Work=MagicMock(), Edition=MagicMock()),
            'backend.core.search': SimpleNamespace(aliases=lambda: {}),
        }
        self.stack.enter_context(patch.dict(sys.modules, modules))
        self.stack.enter_context(patch.object(media, 'RUN', self.root / 'run'))
        self.stack.enter_context(patch.object(enrichment_queue, 'STATE', self.root / 'queues'))
        self.stack.enter_context(patch.object(transport, 'STATE', self.root / 'http'))
        self.stack.enter_context(patch.object(media, 'portrait_lookup_item', side_effect=lambda item, *a, **k: item))
        self.save = self.stack.enter_context(patch.object(media, 'save_match', return_value='covered'))
        self.stack.enter_context(patch.object(sys, 'argv', ['media', 'linked-wikidata-portraits', '--limit', '5']))
        self.stack.enter_context(redirect_stdout(io.StringIO()))

    def discover(self, item, provider):
        return [{'image_url': f'https://images.example/{item["id"]}.jpg',
                 'source': f'https://source.example/{item["id"]}', 'credit': 'Recorded credit'}]

    def download(self, candidates, **kwargs):
        if '/5.jpg' not in candidates[0]['image_url']:
            raise transport.ProviderOutage('HTTP 429', status=429)
        return {**candidates[0], 'blob': b'validated image', 'extension': 'jpg'}

    def stats(self):
        return json.loads((self.root / 'run/linked-wikidata-portraits-stats.json').read_text())

    def rows(self):
        with sqlite3.connect(self.root / 'queues/linked-wikidata-portraits.sqlite3') as connection:
            return connection.execute('SELECT work_id,state,attempts FROM attempts ORDER BY work_id').fetchall()

    def test_four_image_deferrals_do_not_prevent_the_next_portrait_or_consume_retries(self):
        with patch.object(media, 'provider_candidates', side_effect=self.discover) as lookup, \
                patch.object(media, 'download_candidates', side_effect=self.download):
            media.main()
        stats = self.stats()
        self.assertEqual((stats['processed'], stats['covered'], stats['image_deferred'], stats['provider_errors']),
                         (5, 1, 4, 0))
        self.assertEqual(lookup.call_count, 5)
        self.assertNotIn('provider_outage', stats)
        self.assertNotIn('retry_after', stats)
        self.assertFalse((self.root / 'run/linked-wikidata-portraits-cooldown.json').exists())
        self.assertEqual(outcome({}, stats)['status'], 'ready')
        self.assertEqual(self.rows(), [(index, 'provider_wait', 0) for index in range(1, 5)] + [(5, 'complete', 1)])
        self.save.assert_called_once()

    def test_deferred_images_reuse_candidates_after_retry_and_wait_without_global_outage(self):
        with patch.object(media, 'provider_candidates', side_effect=self.discover), \
                patch.object(media, 'download_candidates', side_effect=self.download):
            media.main()
        with patch.object(media, 'provider_candidates', side_effect=AssertionError('Repeated metadata')), \
                patch.object(media, 'download_candidates') as download:
            media.main()
        self.assertEqual(outcome({}, self.stats())['status'], 'waiting')
        download.assert_not_called()
        with sqlite3.connect(self.root / 'queues/linked-wikidata-portraits.sqlite3') as connection:
            connection.execute("UPDATE attempts SET next_retry=0 WHERE state='provider_wait'")
        with patch.object(media, 'provider_candidates', side_effect=AssertionError('Repeated metadata')), \
                patch.object(media, 'download_candidates',
                             side_effect=lambda candidates, **kwargs: {**candidates[0], 'blob': b'validated image'}):
            media.main()
        self.assertEqual(self.stats()['covered'], 4)
        self.assertTrue(all(state == 'complete' and attempts == 1 for _, state, attempts in self.rows()))

    def test_metadata_outage_still_stops_and_preserves_unattempted_records(self):
        with patch.object(media, 'provider_candidates', side_effect=transport.ProviderOutage('HTTP 429', status=429)) as lookup:
            media.main()
        stats = self.stats()
        self.assertEqual(stats['processed'], 1)
        self.assertTrue(stats['provider_outage'])
        self.assertEqual(stats['provider_errors'], 1)
        self.assertEqual(stats['image_deferred'], 0)
        self.assertTrue((self.root / 'run/linked-wikidata-portraits-cooldown.json').exists())
        self.assertEqual(outcome({}, stats)['status'], 'cooldown')
        self.assertEqual(lookup.call_count, 1)
        self.assertEqual(self.rows(), [(1, 'provider_wait', 0)] + [(index, 'pending', 0) for index in range(2, 6)])

    def test_image_deferrals_do_not_rewrite_existing_provider_cooldown(self):
        run = self.root / 'run'
        run.mkdir()
        cooldown = run / 'linked-wikidata-portraits-cooldown.json'
        cooldown.write_text('{"until": 1, "reason": "Preserved expired provider wait"}')
        original = cooldown.read_bytes()
        with patch.object(media, 'provider_candidates', side_effect=self.discover), \
                patch.object(media, 'download_candidates', side_effect=self.download):
            media.main()
        self.assertEqual(cooldown.read_bytes(), original)
