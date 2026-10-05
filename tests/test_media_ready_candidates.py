"""Verified image downloads must not wait behind fresh metadata lookups."""
from contextlib import ExitStack, redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from research import enrich_media_alternatives as media
from research import enrichment_queue, media_transport as transport


class ReadyCandidateTests(unittest.TestCase):
    PROVIDER = 'openlibrary-portraits'

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        for change in (patch.object(transport, 'STATE', self.root / 'http'),
                       patch.object(enrichment_queue, 'STATE', self.root / 'queues')):
            change.start()
            self.addCleanup(change.stop)
        self.item = {'id': 2, 'title': 'Jane Writer', 'works': ['A Known Work'], 'authors': ['A Known Work']}
        self.candidate = {'source': 'https://openlibrary.org/authors/OL123A',
            'image_url': 'https://covers.openlibrary.org/a/id/456-L.jpg?default=false',
            'author_key': 'OL123A', 'matched_works': ['A Known Work'], 'credit': 'Original credited portrait.',
            'allowed_image_hosts': list(transport.OPENLIBRARY_IMAGE_HOSTS)}
        self.current = transport.CandidateStore(self.PROVIDER, version=media.provider_policy(self.PROVIDER))
        self.previous = transport.CandidateStore(self.PROVIDER, version=media.POLICY + ':archive-storage-v1')

    def test_old_compatible_positive_is_discoverable_read_only_then_migrated(self):
        self.previous.put(self.item, [self.candidate])
        previous_path = self.previous._path(self.item)
        original = previous_path.read_bytes()
        self.assertEqual(media.positive_candidates([self.item], self.PROVIDER)[0]['_cached_candidates'], [self.candidate])
        self.assertIsNone(self.current.get(self.item))
        self.assertNotIn('_cached_candidates', self.item)
        media.positive_candidates([self.item], self.PROVIDER, migrate=True)
        self.assertEqual(self.current.get(self.item), [self.candidate])
        self.assertEqual(previous_path.read_bytes(), original)

    def test_old_negatives_and_changed_identities_are_not_migrated(self):
        self.previous.put(self.item, [])
        self.assertEqual(media.positive_candidates([self.item], self.PROVIDER, migrate=True), [])
        self.assertIsNone(self.current.get(self.item))
        self.previous.put(self.item, [self.candidate])
        changed = {**self.item, 'title': 'Other Writer'}
        self.assertEqual(media.positive_candidates([changed], self.PROVIDER, migrate=True), [])
        self.assertIsNone(self.current.get(changed))

    def test_current_negative_is_not_overruled_by_older_positive(self):
        self.previous.put(self.item, [self.candidate])
        self.current.put(self.item, [])
        self.assertEqual(media.positive_candidates([self.item], self.PROVIDER, migrate=True), [])
        self.assertEqual(self.current.get(self.item), [])

    def test_migration_rejects_incompatible_works_source_credit_and_image_hosts(self):
        invalid = [
            {**self.candidate, 'matched_works': ['Someone Else’s Book']},
            {**self.candidate, 'author_key': 'OL456A'},
            {**self.candidate, 'source': 'https://openlibrary.org/authors/OL123A?unverified=true'},
            {**self.candidate, 'image_url': 'https://other.example/image.jpg'},
            {**self.candidate, 'credit': ''},
            {**self.candidate, 'allowed_image_hosts': ['other.example']},
        ]
        for candidate in invalid:
            with self.subTest(candidate=candidate):
                self.previous.put(self.item, [candidate])
                self.assertEqual(media.positive_candidates([self.item], self.PROVIDER, migrate=True), [])
                self.assertIsNone(self.current.get(self.item))

    def test_positive_candidates_precede_fresh_items_before_batch_limit(self):
        self.current.put(self.item, [self.candidate])
        fresh = {**self.item, 'id': 1}
        queue = SimpleNamespace(priority=lambda item: item['id'])
        with patch.object(media, 'provider_candidates', side_effect=AssertionError('Unexpected discovery')):
            prioritized = media.prioritize_candidates([fresh, self.item], self.PROVIDER, queue)
        self.assertEqual([item['id'] for item in prioritized[:1]], [2])
        self.assertEqual([item['id'] for item in prioritized], [2, 1])

    def test_cached_only_never_discovers_missing_candidates(self):
        with patch.object(media, 'provider_candidates', side_effect=AssertionError('Unexpected discovery')) as lookup:
            self.assertIsNone(media.cached_match(self.item, self.PROVIDER, cached_only=True))
        lookup.assert_not_called()

    def test_partial_wikidata_batch_checkpoints_completed_items_only(self):
        from research import media_cached_wikidata_portraits as provider
        items = [{**self.item, 'id': identity} for identity in range(1, 5)]
        store = transport.CandidateStore('cached-wikidata-portraits',
                                        version=media.provider_policy('cached-wikidata-portraits'))
        store.put(items[1], [self.candidate])
        outage = transport.ProviderOutage('HTTP 429', status=429)
        # Indices address the missing subset (1, 3, 4), not the original list.
        partial = provider.PartialDiscovery(outage, {0: [self.candidate], 1: []})
        with patch.object(provider, 'batch_candidates', side_effect=partial) as lookup:
            with self.assertRaises(provider.PartialDiscovery) as caught:
                media.prepare_cached_wikidata_batch(items)
        self.assertIs(caught.exception, partial)
        self.assertEqual([item['id'] for item in lookup.call_args.args[0]], [1, 3, 4])
        self.assertEqual(store.get(items[0]), [self.candidate])
        self.assertEqual(store.get(items[1]), [self.candidate])
        self.assertEqual(store.get(items[2]), [])
        self.assertIsNone(store.get(items[3]))

    def test_plain_wikidata_outage_does_not_create_negative_checkpoints(self):
        from research import media_cached_wikidata_portraits as provider
        store = transport.CandidateStore('cached-wikidata-portraits',
                                        version=media.provider_policy('cached-wikidata-portraits'))
        with patch.object(provider, 'batch_candidates', side_effect=transport.ProviderOutage('HTTP 503')):
            with self.assertRaises(transport.ProviderOutage):
                media.prepare_cached_wikidata_batch([self.item])
        self.assertIsNone(store.get(self.item))

    def test_partial_metadata_failure_saves_ready_first_person_and_signals_other_downloads(self):
        from research import media_cached_wikidata_portraits as provider
        name = 'cached-wikidata-portraits'
        items = [{**self.item, 'id': identity} for identity in (1, 2, 3)]
        queryset = MagicMock()
        queryset.prefetch_related.return_value = queryset
        queryset.annotate.return_value = queryset
        queryset.order_by.return_value = items
        person = MagicMock()
        person.objects.filter.return_value = queryset
        modules = {
            'django': SimpleNamespace(setup=lambda: None),
            'django.db.models': SimpleNamespace(Count=lambda *a, **k: 0, Q=lambda **k: 0,
                                                Prefetch=lambda *a, **k: None),
            'backend.core.models': SimpleNamespace(Person=person, Work=MagicMock(), Edition=MagicMock()),
            'backend.core.search': SimpleNamespace(aliases=lambda: {}),
        }
        failure = transport.ProviderOutage('HTTP 429', status=429)
        partial = provider.PartialDiscovery(failure, {0: [self.candidate], 1: [self.candidate]})
        with ExitStack() as stack:
            stack.enter_context(patch.object(media, 'RUN', self.root))
            stack.enter_context(patch.dict(sys.modules, modules))
            stack.enter_context(patch.object(sys, 'argv', ['worker', name]))
            stack.enter_context(patch.object(media, 'portrait_lookup_item', side_effect=lambda item, *a, **k: dict(item)))
            stack.enter_context(patch.object(provider, 'cached_identity', return_value={
                'identity_sources': ['https://openlibrary.org/authors/OL123A'], 'wikidata': 'Q123'}))
            stack.enter_context(patch.object(provider, 'batch_candidates', side_effect=partial))
            stack.enter_context(patch.object(media, 'download_candidates', return_value={**self.candidate, 'blob': b'image'}))
            save = stack.enter_context(patch.object(media, 'save_match', return_value='covered'))
            stack.enter_context(redirect_stdout(io.StringIO()))
            media.main()
        save.assert_called_once()
        self.assertEqual(save.call_args.args[1]['id'], 1)
        stats = json.loads((self.root / (name + '-stats.json')).read_text())
        self.assertEqual((stats['covered'], stats['processed'], stats['cached_waiting']), (1, 1, 1))
        self.assertLess(stats['cached_next_retry'], failure.retry_after)
        self.assertEqual(stats['http_status'], 429)
        queue = enrichment_queue.Queue(name, self.root / (name + '.jsonl'))
        try:
            states = dict(queue.db.execute('SELECT work_id,state FROM attempts'))
        finally:
            queue.close()
        self.assertEqual(states, {1: 'complete', 2: 'pending', 3: 'pending'})

    def test_cached_only_download_keeps_real_image_host_cooldown(self):
        self.current.put(self.item, [self.candidate])
        until = transport.time.time() + 900
        transport._cooldown('covers.openlibrary.org', until, 429)
        state = next((self.root / 'http/hosts').glob('*.json'))
        original = state.read_bytes()
        with patch.object(transport, 'build_opener') as network:
            with self.assertRaises(media.ImageProviderOutage) as error:
                media.cached_match(self.item, self.PROVIDER, cached_only=True)
        network.assert_not_called()
        self.assertEqual(error.exception.retry_after, until)
        self.assertEqual(state.read_bytes(), original)

    def test_cached_only_worker_bypasses_metadata_wait_but_preserves_image_queue_wait(self):
        fresh = {**self.item, 'id': 1}
        waiting = {**self.item, 'id': 3, 'title': 'Waiting Writer'}
        items = [fresh, self.item, waiting]
        self.previous.put(self.item, [self.candidate])
        self.current.put(waiting, [self.candidate])
        ledger = self.root / (self.PROVIDER + '.jsonl')
        queue = enrichment_queue.Queue(self.PROVIDER, ledger)
        for item in items:
            queue.due(item, media.provider_policy(self.PROVIDER))
        until = media.time.time() + 900
        with ledger.open('a') as audit:
            queue.finish(waiting, {'status': 'image_deferred', 'provider_outage': True,
                                  'retry_after': until}, audit)
        queue.close()
        cooldown = self.root / (self.PROVIDER + '-cooldown.json')
        cooldown.write_text(json.dumps({'until': until, 'reason': 'HTTP 429', 'http_status': 429}))
        original = cooldown.read_bytes()
        queryset = MagicMock()
        queryset.prefetch_related.return_value = queryset
        queryset.annotate.return_value = queryset
        queryset.order_by.return_value = items
        person = MagicMock()
        person.objects.filter.return_value = queryset
        modules = {
            'django': SimpleNamespace(setup=lambda: None),
            'django.db.models': SimpleNamespace(Count=lambda *a, **k: 0, Q=lambda **k: 0,
                                                Prefetch=lambda *a, **k: None),
            'backend.core.models': SimpleNamespace(Person=person, Work=MagicMock(), Edition=MagicMock()),
            'backend.core.search': SimpleNamespace(aliases=lambda: {}),
        }
        image = {**self.candidate, 'blob': b'validated-image'}
        with ExitStack() as stack:
            stack.enter_context(patch.object(media, 'RUN', self.root))
            stack.enter_context(patch.dict(sys.modules, modules))
            stack.enter_context(patch.dict(os.environ, {}))
            stack.enter_context(patch.object(sys, 'argv', ['worker', self.PROVIDER, '--cached-only']))
            stack.enter_context(patch.object(media, 'portrait_lookup_item', side_effect=lambda item, *a, **k: item))
            discovery = stack.enter_context(patch.object(media, 'provider_candidates', side_effect=AssertionError('Unexpected metadata lookup')))
            download = stack.enter_context(patch.object(media, 'download_candidates', return_value=image))
            save = stack.enter_context(patch.object(media, 'save_match', return_value='covered'))
            stack.enter_context(redirect_stdout(io.StringIO()))
            media.main()
        self.assertEqual(cooldown.read_bytes(), original)
        discovery.assert_not_called()
        download.assert_called_once()
        self.assertEqual(save.call_args.args[1]['id'], 2)
        self.assertFalse((self.root / (self.PROVIDER + '-stats.json')).exists())
        stats = json.loads((self.root / (self.PROVIDER + '-cached-stats.json')).read_text())
        self.assertEqual((stats['cached_only'], stats['processed'], stats['covered']), (True, 1, 1))
        self.assertEqual(stats['cached_waiting'], 1)
        self.assertEqual(stats['cached_next_retry'], until)
        queue = enrichment_queue.Queue(self.PROVIDER, ledger)
        try:
            states = {identity: (state, attempts) for identity, state, attempts in
                      queue.db.execute('SELECT work_id,state,attempts FROM attempts')}
        finally:
            queue.close()
        self.assertEqual(states, {1: ('pending', 0), 2: ('complete', 1), 3: ('provider_wait', 0)})
