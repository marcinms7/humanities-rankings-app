"""Accepted media changes only the intended illustration and attribution."""
import io
import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from PIL import Image

from .models import Edition, LibraryItem, Person, Ranking, RankingEntry, Work


class MediaIngestionTests(TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        settings = override_settings(MEDIA_ROOT=Path(folder.name) / 'media', BASE_DIR=Path(folder.name))
        settings.enable()
        self.addCleanup(settings.disable)
        self.person = Person.objects.create(name='Jane Writer')
        self.work = Work.objects.create(title='A Book')
        self.work.authors.add(self.person)
        self.edition = Edition.objects.create(work=self.work, publisher='Recorded publisher', pages=250,
            language='English', translator='Recorded translator', isbn='9780141439518')
        self.work.default_edition = self.edition
        self.work.save(update_fields=['default_edition'])
        self.user = get_user_model().objects.create_user('media-fixture')
        self.reading = LibraryItem.objects.create(user=self.user, work=self.work, edition=self.edition,
            notes='Private writing', reading_basis={'edition_id': self.edition.pk, 'pages': 250, 'publisher': 'Frozen publisher'})
        blob = io.BytesIO()
        Image.new('RGB', (120, 180)).save(blob, format='PNG')
        self.match = {'blob': blob.getvalue(), 'source': 'https://gallica.bnf.fr/ark:/12148/example',
                      'image_url': 'https://gallica.bnf.fr/iiif/example.png',
                      'credit': 'Scanned title page; Bibliothèque nationale de France / Gallica.',
                      'depiction_kind': 'title_page'}
        self.item = {'id': self.work.pk, 'title': self.work.title, 'authors': [self.person.name],
                     'edition_id': self.edition.pk}

    def save(self, item=None, match=None):
        from research.enrich_media_alternatives import save_match
        return save_match('gallica-covers', item or self.item, match or self.match)

    def test_image_save_preserves_bibliographic_and_private_reading_fields(self):
        before = LibraryItem.objects.filter(pk=self.reading.pk).values().get()
        self.assertEqual(self.save(), 'covered')
        self.edition.refresh_from_db()
        self.assertTrue(Path(self.edition.cover.path).is_file())
        self.assertEqual(self.edition.cover_basis, 'representative_work')
        self.assertIn('Scanned title page', self.edition.image_attribution)
        self.assertEqual((self.edition.publisher, self.edition.translator, self.edition.pages, self.edition.isbn),
                         ('Recorded publisher', 'Recorded translator', 250, '9780141439518'))
        self.assertEqual(LibraryItem.objects.filter(pk=self.reading.pk).values().get(), before)

    def test_existing_image_is_never_replaced_by_another_provider(self):
        self.save()
        self.edition.refresh_from_db()
        before = (self.edition.cover.name, self.edition.cover_source_url, self.edition.cover.read())
        self.assertEqual(self.save(match={**self.match, 'source': 'https://www.loc.gov/item/other'}), 'preserved_existing')
        self.edition.refresh_from_db()
        self.assertEqual((self.edition.cover.name, self.edition.cover_source_url, self.edition.cover.read()), before)

    def test_time_budget_checkpoints_completed_portrait_and_resumes_untouched_person(self):
        from research import enrich_media_alternatives as media
        from research import enrichment_queue
        other = Person.objects.create(name='Another Writer')
        self.work.authors.add(other)
        before = LibraryItem.objects.filter(pk=self.reading.pk).values().get()
        clock = [100.0]
        def lookup(*args, **kwargs):
            clock[0] += 2  # One lookup exceeds the one-second soft budget.
            return self.match
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(media, 'RUN', root / 'run'), \
                    patch.object(enrichment_queue, 'STATE', root / 'queues'), \
                    patch.object(media.time, 'monotonic', side_effect=lambda: clock[0]), \
                    patch.object(media, 'cached_match', side_effect=lookup), \
                    patch.object(media.sys, 'argv', ['worker', 'nobel-portraits', '--limit', '10', '--max-seconds', '1']), \
                    patch('builtins.print'):
                media.main()
                first = json.loads((root / 'run/nobel-portraits-stats.json').read_text())
                self.assertEqual(first['processed'], 1)
                self.assertTrue(first['yielded_for_time_budget'])
                self.person.refresh_from_db()
                other.refresh_from_db()
                original = (self.person.portrait.name, self.person.portrait.read())
                self.assertFalse(other.portrait)
                with sqlite3.connect(root / 'queues/nobel-portraits.sqlite3') as db:
                    self.assertEqual(db.execute('SELECT state,attempts FROM attempts WHERE work_id=?',
                                                (other.pk,)).fetchone(), ('pending', 0))
                media.main()
                self.person.refresh_from_db()
                other.refresh_from_db()
                self.assertTrue(other.portrait)
                self.assertEqual((self.person.portrait.name, self.person.portrait.read()), original)
                rows = [json.loads(line) for line in (root / 'run/nobel-portraits.jsonl').read_text().splitlines()]
                self.assertEqual([row['work_id'] for row in rows], [self.person.pk, other.pk])
        self.assertEqual(LibraryItem.objects.filter(pk=self.reading.pk).values().get(), before)

    def test_changed_catalog_identity_rejects_previously_matched_candidate(self):
        self.work.title = 'Different Book'
        self.work.save(update_fields=['title'])
        self.assertIn('identity_review', self.save())
        self.edition.refresh_from_db()
        self.assertFalse(self.edition.cover)

    def test_changed_default_edition_does_not_receive_old_lookup_image(self):
        replacement = Edition.objects.create(work=self.work, publisher='New edition')
        self.work.default_edition = replacement
        self.work.save(update_fields=['default_edition'])
        self.assertIn('identity_review', self.save())
        replacement.refresh_from_db()
        self.assertFalse(replacement.cover)

    def test_html_is_never_saved_as_a_successful_image(self):
        with self.assertRaises(Exception):
            self.save(match={**self.match, 'blob': b'<html>Provider unavailable</html>'})
        self.edition.refresh_from_db()
        self.assertFalse(self.edition.cover)

    def test_new_display_edition_does_not_claim_verified_edition_metadata(self):
        other = Work.objects.create(title='Another Book')
        other.authors.add(self.person)
        item = {'id': other.pk, 'title': other.title, 'authors': [self.person.name], 'edition_id': None}
        self.assertEqual(self.save(item=item), 'covered')
        other.refresh_from_db()
        self.assertEqual(other.default_edition.language, 'Not verified')
        self.assertEqual(other.default_edition.cover_basis, 'representative_work')
        self.assertEqual(other.default_edition.isbn, '')
        self.assertIsNone(other.default_edition.pages)

    def test_portrait_save_rechecks_person_and_work_identity(self):
        from research.enrich_media_alternatives import save_match
        item = {'id': self.person.pk, 'title': self.person.name, 'authors': [self.work.title]}
        self.person.name = 'Changed Name'
        self.person.save(update_fields=['name'])
        result = save_match('loc-portraits', item, self.match)
        self.assertIn('identity_review', result)
        self.person.refresh_from_db()
        self.assertFalse(self.person.portrait)

    def test_foreign_work_default_edition_never_receives_the_matched_cover(self):
        other = Work.objects.create(title='Different Work')
        foreign = Edition.objects.create(work=other, publisher='Another publisher', pages=180)
        # Simulate a legacy inconsistent relation, bypassing normal form/model
        # validation in this disposable database. The captured edition ID still
        # matches, so the ownership guard must independently reject the write.
        Work.objects.filter(pk=self.work.pk).update(default_edition=foreign)
        before = LibraryItem.objects.filter(pk=self.reading.pk).values().get()
        result = self.save(item={**self.item, 'edition_id': foreign.pk})
        self.assertIn('identity_review', result)
        foreign.refresh_from_db()
        self.edition.refresh_from_db()
        self.assertFalse(foreign.cover)
        self.assertFalse(self.edition.cover)
        self.assertEqual(foreign.work_id, other.pk)
        self.assertEqual(LibraryItem.objects.filter(pk=self.reading.pk).values().get(), before)

    def test_withdrawn_shared_ranking_invalidates_no_work_philosopher_candidate(self):
        from research.enrich_media_alternatives import save_match
        person = Person.objects.create(name='Ranked Philosopher')
        shared = Ranking.objects.create(slug='media-shared-philosophers', title='Philosophers', item_type='person')
        entry = RankingEntry.objects.create(ranking=shared, person=person)
        personal = Ranking.objects.create(slug='media-private-philosophers', title='Private philosophers',
                                          item_type='person', origin='personal', owner=self.user)
        RankingEntry.objects.create(ranking=personal, person=person)
        item = {'id': person.pk, 'title': person.name, 'authors': [], 'works': [], 'ranked': True}
        match = {**self.match, 'ranked_philosopher': True, 'matched_works': [],
                 'credit': 'Credited portrait / historical depiction.'}
        # Neither an archived shared entry nor an archived shared list remains
        # valid corroboration; a surviving personal copy cannot substitute.
        for withdrawn in ('entry', 'ranking'):
            with self.subTest(withdrawn=withdrawn):
                entry.is_archived = withdrawn == 'entry'
                entry.save(update_fields=['is_archived'])
                shared.is_archived = withdrawn == 'ranking'
                shared.save(update_fields=['is_archived'])
                result = save_match('wikimedia-portraits', item, match)
                self.assertEqual(result, 'identity_review_changed_during_lookup')
                person.refresh_from_db()
                self.assertFalse(person.portrait)
                self.assertEqual(person.image_attribution, '')
