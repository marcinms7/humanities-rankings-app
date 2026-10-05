"""Reviewed local reuse must preserve identity, image and attribution boundaries."""
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from PIL import Image

from backend.core.models import Edition, Person, Work
from research import reuse_catalog_covers as reuse
from research.enrich_catalog_covers_public import cover_lookup_item


class CatalogCoverReuseTests(TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        settings = override_settings(MEDIA_ROOT=self.root)
        settings.enable()
        self.addCleanup(settings.disable)
        author = Person.objects.create(name='Reviewed Writer')
        self.source = Work.objects.create(title='Original Book')
        self.target = Work.objects.create(title='Original Book (translated title)')
        self.source.authors.add(author)
        self.target.authors.add(author)
        stream = io.BytesIO()
        Image.new('RGB', (120, 180), 'blue').save(stream, format='PNG')
        self.blob = stream.getvalue()
        edition = Edition.objects.create(work=self.source, cover_basis='unknown', image_attribution='Original credit')
        edition.cover.save('reviewed-source.png', ContentFile(self.blob))
        self.source.default_edition = edition
        self.source.save(update_fields=['default_edition'])
        self.entry = {'work_id': self.target.pk, 'title': self.target.title, 'authors': [author.name],
                      'source_work_id': self.source.pk, 'source_title': self.source.title,
                      'source_authors': [author.name], 'source_edition_id': edition.pk,
                      'source_cover': edition.cover.name, 'source_sha256': hashlib.sha256(self.blob).hexdigest(),
                      'reviewed': True, 'reason': 'Reviewed complete book and cover.'}

    def request(self):
        item = cover_lookup_item(self.target)
        item['_catalog_identity'] = reuse.identity(self.target)
        return item, reuse.source_pin(self.source)

    def test_matching_titles_alone_never_authorize_propagating_an_old_cover(self):
        self.assertEqual(list(reuse.opportunities([self.source, self.target], [])), [])
        self.assertEqual(len(list(reuse.opportunities([self.source, self.target], [self.entry]))), 1)

    def test_reviewed_reuse_preserves_unknown_provenance_and_original_file(self):
        item, pin = self.request()
        status, receipt = reuse.ingest(item, pin, self.entry)
        self.assertEqual(status, 'covered')
        self.target.refresh_from_db()
        new = self.target.default_edition
        self.assertEqual(new.cover_basis, 'unknown')
        self.assertEqual(new.cover_source_url, '')
        self.assertEqual(new.language, 'Not verified')
        self.assertEqual(new.image_attribution, 'Original credit')
        self.assertEqual(new.cover.read(), self.blob)
        self.assertEqual(self.source.default_edition.cover.read(), self.blob)
        self.assertNotEqual(new.cover.name, pin['cover'])
        self.assertEqual(receipt['source_sha256'], self.entry['source_sha256'])

    def test_changed_source_metadata_blocks_reuse(self):
        item, pin = self.request()
        Edition.objects.filter(pk=self.source.default_edition_id).update(image_attribution='Changed attribution')
        status, _ = reuse.ingest(item, pin, self.entry)
        self.assertIn('identity_review', status)
        self.target.refresh_from_db()
        self.assertIsNone(self.target.default_edition_id)

    def test_changed_source_bytes_block_reuse_even_at_same_path(self):
        item, pin = self.request()
        stream = io.BytesIO()
        Image.new('RGB', (120, 180), 'red').save(stream, format='PNG')
        Path(self.source.default_edition.cover.path).write_bytes(stream.getvalue())
        status, _ = reuse.ingest(item, pin, self.entry)
        self.assertEqual(status, 'identity_review_source_image_changed')

    def test_source_symlinks_are_never_followed(self):
        external = self.root / 'elsewhere.png'
        external.write_bytes(self.blob)
        link = self.root / 'covers' / 'link.png'
        link.symlink_to(external)
        with self.assertRaises(OSError):
            reuse.read_cover(self.root, 'covers/link.png')

    def test_changed_target_scope_blocks_reviewed_cover(self):
        item, pin = self.request()
        Work.objects.filter(pk=self.target.pk).update(form='poem')
        status, _ = reuse.ingest(item, pin, self.entry)
        self.assertIn('identity_review', status)

    def test_bulk_catalogue_outage_does_not_consume_work_attempts(self):
        from research import enrich_media_alternatives as media, enrichment_queue
        from research import media_wolnelektury_covers as library
        from research.media_transport import ProviderOutage
        run, queues = self.root / 'run', self.root / 'queues'
        with patch.object(media, 'RUN', run), patch.object(enrichment_queue, 'STATE', queues), \
                patch.object(library, 'prepare_items', side_effect=ProviderOutage('Incomplete catalogue')), \
                patch.object(media.sys, 'argv', ['worker', 'wolnelektury-covers']):
            media.main()
        stats = json.loads((run / 'wolnelektury-covers-stats.json').read_text())
        self.assertTrue(stats['provider_outage'])
        self.assertEqual(stats['processed'], 0)
        with sqlite3.connect(queues / 'wolnelektury-covers.sqlite3') as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0], 0)

    def test_cached_bulk_provider_images_do_not_require_catalogue_discovery(self):
        from research import enrich_media_alternatives as media, enrichment_queue
        from research import media_wolnelektury_covers as library
        run, queues = self.root / 'run', self.root / 'queues'
        match = {'blob': self.blob, 'source': 'https://wolnelektury.pl/katalog/lektura/book/',
                 'credit': 'Reviewed digital edition.'}
        with patch.object(media, 'RUN', run), patch.object(enrichment_queue, 'STATE', queues), \
                patch.object(library, 'prepare_items', side_effect=AssertionError('Unexpected discovery')), \
                patch.object(media, 'positive_candidates', side_effect=lambda items, *a, **kw: list(items)), \
                patch.object(media, 'cached_match', return_value=match), \
                patch.object(media.sys, 'argv', ['worker', 'wolnelektury-covers', '--cached-only']), \
                patch('builtins.print'):
            media.main()
        stats = json.loads((run / 'wolnelektury-covers-cached-stats.json').read_text())
        self.assertEqual(stats['covered'], 1)
        self.assertFalse((run / 'wolnelektury-covers-cooldown.json').exists())
