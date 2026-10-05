"""Batch discovery checkpoints real candidate caches without catalog writes."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research import enrich_media_alternatives as media, media_dbpedia_portraits as dbpedia
from research import media_transport as transport


class DBpediaBatchCheckpointTests(unittest.TestCase):
    def test_twenty_people_share_two_discovery_batches_and_resume_without_lookups(self):
        items = [{'id': index, 'title': f'Writer {index}', 'works': ['A known work']}
                 for index in range(20)]
        def discovered(group):
            return [[{'image_url': f'https://thumb.wikimedia.org/portrait{item["id"]}.jpg'}]
                    if item['id'] % 2 else [] for item in group]
        with tempfile.TemporaryDirectory() as folder, patch.object(transport, 'STATE', Path(folder)), \
                patch.object(dbpedia, 'batch_candidates', side_effect=discovered) as lookup:
            for index in range(len(items)):
                media.prepare_dbpedia_batch(items[index:index + 10])
            self.assertEqual(lookup.call_count, 2)
            store = transport.CandidateStore('dbpedia-portraits', version=media.provider_policy('dbpedia-portraits'))
            self.assertEqual(store.get(items[0]), [])
            self.assertEqual(store.get(items[1])[0]['image_url'], 'https://thumb.wikimedia.org/portrait1.jpg')
            for index in range(len(items)):
                media.prepare_dbpedia_batch(items[index:index + 10])
            self.assertEqual(lookup.call_count, 2)

    def test_discovery_failure_leaves_missing_people_uncached_and_existing_candidates_intact(self):
        items = [{'id': index, 'title': f'Writer {index}'} for index in range(3)]
        with tempfile.TemporaryDirectory() as folder, patch.object(transport, 'STATE', Path(folder)), \
                patch.object(dbpedia, 'batch_candidates', side_effect=transport.ProviderOutage('HTTP 503')):
            store = transport.CandidateStore('dbpedia-portraits', version=media.provider_policy('dbpedia-portraits'))
            store.put(items[1], [{'image_url': 'https://thumb.wikimedia.org/known.jpg'}])
            with self.assertRaises(transport.ProviderOutage):
                media.prepare_dbpedia_batch(items)
            self.assertIsNone(store.get(items[0]))
            self.assertIsNone(store.get(items[2]))
            self.assertEqual(len(store.get(items[1])), 1)
