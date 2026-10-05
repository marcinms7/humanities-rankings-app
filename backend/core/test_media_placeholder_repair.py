"""An exact reviewed placeholder can be repaired without replacing real media."""
import hashlib
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from PIL import Image

from research import media_image_quality as quality
from research.enrich_catalog_covers_public import cover_lookup_item
from research.enrich_media_alternatives import save_match
from research.media_transport import CandidateRejected

from .models import Edition, LibraryItem, Person, Work


def raster(color):
    output = io.BytesIO()
    Image.new('RGB', (120, 180), color).save(output, 'PNG')
    return output.getvalue()


class PlaceholderRepairTests(TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        settings = override_settings(MEDIA_ROOT=self.root / 'media', BASE_DIR=self.root)
        settings.enable()
        self.addCleanup(settings.disable)
        self.old_blob = raster('red')
        known = patch.dict(quality.KNOWN_PLACEHOLDERS,
                           {hashlib.sha256(self.old_blob).hexdigest(): len(self.old_blob)}, clear=True)
        known.start()
        self.addCleanup(known.stop)
        self.person = Person.objects.create(name='Fixture Writer')
        self.work = Work.objects.create(title='Fixture Book')
        self.work.authors.add(self.person)
        self.edition = Edition.objects.create(work=self.work, language='English', pages=210,
            publisher='Original publisher', cover_basis='unknown', source_url='https://example.org/edition',
            cover_source_url='https://archive.org/details/old-item', image_attribution='Original image credit')
        self.edition.cover.save('old-placeholder.png', ContentFile(self.old_blob))
        self.old_path = Path(self.edition.cover.path)
        self.work.default_edition = self.edition
        self.work.save(update_fields=['default_edition'])
        self.item = cover_lookup_item(self.work, {})
        self.match = {'blob': raster('blue'), 'source': 'https://example.org/new-image',
                      'credit': 'Replacement image credit'}

    def test_repair_preserves_original_and_private_metadata_with_audit_receipt(self):
        user = get_user_model().objects.create_user('placeholder-fixture')
        reading = LibraryItem.objects.create(user=user, work=self.work, edition=self.edition,
            notes='Private fixture', reading_basis={'edition_id': self.edition.pk, 'pages': 210})
        before = LibraryItem.objects.filter(pk=reading.pk).values().get()
        self.assertEqual(save_match('reviewed-covers', self.item, self.match), 'covered')
        self.edition.refresh_from_db()
        self.assertNotEqual(Path(self.edition.cover.path), self.old_path)
        self.assertEqual(self.old_path.read_bytes(), self.old_blob)
        self.assertEqual(Path(self.edition.cover.path).read_bytes(), self.match['blob'])
        self.assertEqual(self.edition.cover_source_url, self.match['source'])
        self.assertIn('Replacement image credit', self.edition.image_attribution)
        self.assertEqual((self.edition.publisher, self.edition.pages, self.edition.source_url),
                         ('Original publisher', 210, 'https://example.org/edition'))
        self.assertEqual(LibraryItem.objects.filter(pk=reading.pk).values().get(), before)
        receipt = self.match['replaced_placeholder']
        self.assertEqual(receipt['path'], self.item['placeholder_replacement']['path'])
        self.assertEqual(receipt['image_attribution'], 'Original image credit')
        self.assertEqual(receipt['source_url'], 'https://archive.org/details/old-item')
        self.assertEqual(receipt['cover_basis'], 'unknown')

    def test_repair_requires_explicit_exact_reference_and_never_overwrites_new_cover(self):
        item = {key: value for key, value in self.item.items() if key != 'placeholder_replacement'}
        self.assertEqual(save_match('reviewed-covers', item, self.match), 'preserved_existing')
        # A concurrent worker installing a real image invalidates the old repair marker.
        self.edition.cover.save('concurrent-real.png', ContentFile(raster('green')))
        current_path = Path(self.edition.cover.path)
        current_bytes = current_path.read_bytes()
        self.assertEqual(save_match('reviewed-covers', self.item, self.match), 'preserved_existing')
        self.edition.refresh_from_db()
        self.assertEqual(Path(self.edition.cover.path), current_path)
        self.assertEqual(current_path.read_bytes(), current_bytes)
        self.assertEqual(self.old_path.read_bytes(), self.old_blob)

    def test_changed_placeholder_reference_and_archived_edition_are_protected(self):
        self.edition.cover.save('another-placeholder.png', ContentFile(self.old_blob))
        self.assertEqual(save_match('reviewed-covers', self.item, self.match), 'preserved_existing')
        self.work.refresh_from_db()
        current = cover_lookup_item(self.work, {})
        self.edition.is_archived = True
        self.edition.save(update_fields=['is_archived'])
        self.assertEqual(save_match('reviewed-covers', current, self.match), 'identity_review_archived_edition')
        self.assertNotIn('replaced_placeholder', self.match)

    def test_incoming_placeholder_is_rejected_before_any_write(self):
        with self.assertRaises(CandidateRejected):
            save_match('reviewed-covers', self.item, {**self.match, 'blob': self.old_blob})
        self.edition.refresh_from_db()
        self.assertEqual(Path(self.edition.cover.path), self.old_path)
        self.assertEqual(self.edition.image_attribution, 'Original image credit')

    def test_catalog_reuse_does_not_promote_unknown_provenance(self):
        self.assertEqual(save_match('catalog-covers', self.item, {**self.match, 'cover_basis': 'unknown'}), 'covered')
        self.edition.refresh_from_db()
        self.assertEqual(self.edition.cover_basis, 'unknown')

    def test_public_worker_selects_repairs_and_excludes_them_from_ready_inventory(self):
        from research import enrich_catalog_covers_public as public, enrichment_queue
        from research.media_inventory import inventory

        totals, rows = inventory(self.root / 'queues', [('covers',)])
        self.assertEqual(totals['covers_ready'], 0)
        self.assertEqual(totals['cover_file_states']['known_placeholder'], 1)
        self.assertEqual(next(row for row in rows if row['kind'] == 'cover')['reason'], 'known_placeholder')
        run = self.root / 'run'
        cache = run / 'outcomes.jsonl'
        match = {'image': self.match['blob'], 'provider': 'openlibrary', 'cover_id': 123,
                 'source_key': '/books/OL123M'}
        with patch.object(public, 'RUN', run), patch.object(public, 'CACHE', cache), \
                patch.object(enrichment_queue, 'STATE', self.root / 'queues'), \
                patch('backend.core.search.aliases', return_value={}), \
                patch.object(public, 'lookup', return_value=(match, None)) as lookup, \
                patch.object(public.sys, 'argv', ['worker', '--limit', '1', '--workers', '1']), \
                patch('builtins.print'):
            public.main()
        lookup.assert_called_once()
        self.assertEqual(lookup.call_args.args[0]['placeholder_replacement'], self.item['placeholder_replacement'])
        receipt = json.loads(cache.read_text().splitlines()[0])
        self.assertEqual(receipt['status'], 'covered')
        self.assertEqual(receipt['replaced_placeholder']['image_attribution'], 'Original image credit')
        self.edition.refresh_from_db()
        self.assertNotEqual(Path(self.edition.cover.path), self.old_path)
        self.assertEqual(self.old_path.read_bytes(), self.old_blob)
        totals, _ = inventory(self.root / 'queues', [('covers',)])
        self.assertEqual(totals['covers_ready'], 1)
        self.assertEqual(totals['missing_covers'], 0)

    def test_publisher_inapplicable_inputs_never_enter_lookup_queue(self):
        from research import enrich_media_alternatives as media, enrichment_queue

        run = self.root / 'run'
        with patch.object(media, 'RUN', run), \
                patch.object(enrichment_queue, 'STATE', self.root / 'queues'), \
                patch('backend.core.search.aliases', return_value={}), \
                patch.object(media, 'cached_match') as lookup, \
                patch.object(media, 'positive_candidates', return_value=[]) as positives, \
                patch.object(media.sys, 'argv', ['worker', 'publisher-covers']), \
                patch('builtins.print'):
            media.main()
        lookup.assert_not_called()
        self.assertEqual(positives.call_args.args[0], [])
        stats = json.loads((run / 'publisher-covers-stats.json').read_text())
        self.assertEqual(stats['not_applicable'], 1)
        self.assertEqual((stats['queued'], stats['processed']), (0, 0))
