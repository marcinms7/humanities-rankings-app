"""Bibliography exports preserve recorded edition provenance and are read-only."""
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest import skipUnless
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from .api_contracts import contract_registry
from .bibliography import plain, tex
from .management.commands.export_frontend_contracts import schema_object
from .models import Edition, LibraryItem, MutationReceipt, Person, Work
from .test_api_contracts import assert_shape


class BibliographyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('bibliography-reader')
        cls.other = get_user_model().objects.create_user('bibliography-other')
        cls.work = Work.objects.create(title='A recorded work', original_year=1870)
        cls.author = Person.objects.create(name='Recorded Author')
        cls.work.authors.add(cls.author)
        cls.edition = Edition.objects.create(work=cls.work, publisher='Catalog Publisher',
            translator='Recorded Translator', isbn='9781234567890')
        cls.work.default_edition = cls.edition
        cls.work.save()
        cls.item = LibraryItem.objects.create(user=cls.user, work=cls.work, edition=cls.edition,
            notes='Never export private writing', rating=8, current_page=42)
        cls.unknown = Work.objects.create(title='Unknown edition', original_year=-400)
        cls.other_item = LibraryItem.objects.create(user=cls.other, work=cls.unknown,
            notes='Other reader private writing', reading_basis={
                'edition_id': 999999, 'publisher': 'Other reader publisher',
            })

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def post(self, ids=None, **kwargs):
        return self.client.post('/api/bibliography/', {
            'work_ids': ids if ids is not None else [self.work.pk], **kwargs,
        }, format='json')

    def test_exports_saved_edition_without_claiming_original_year_as_edition_year(self):
        response = self.post()
        self.assertEqual(response.status_code, 200, response.data)
        result = response.json()
        assert_shape(self, schema_object(contract_registry()['ApiBibliographyExport']()), result)
        reference = result['references'][0]
        self.assertEqual(reference['edition_source'], 'library_snapshot')
        self.assertEqual(reference['publisher'], 'Catalog Publisher')
        self.assertIn('edition publication year', reference['missing_fields'])
        self.assertIn('(n.d.)', reference['reference'])
        self.assertIn('Original work: 1870', reference['reference'])
        self.assertNotIn('PY  -', result['ris'])
        self.assertNotIn('Y1  -', result['ris'])
        self.assertNotIn('year =', result['bibtex'])
        self.assertIn('Translator as recorded: Recorded Translator', result['ris'])
        self.assertNotIn('A2  -', result['ris'])
        self.assertNotIn('editor =', result['bibtex'])
        self.assertIn('private, no-store', response['Cache-Control'])

    def test_frozen_metadata_survives_current_catalog_changes_and_opt_out_is_explicit(self):
        Edition.objects.filter(pk=self.edition.pk).update(publisher='Changed Catalog Publisher')
        self.assertEqual(self.post().data['references'][0]['publisher'], 'Catalog Publisher')
        reference = self.post(prefer_library_editions=False).data['references'][0]
        self.assertEqual(reference['publisher'], 'Changed Catalog Publisher')
        self.assertEqual(reference['edition_source'], 'catalog_default')
        self.assertIn('verify it matches', ' '.join(reference['notices']))

    def test_unknown_frozen_edition_does_not_silently_become_new_catalog_default(self):
        item = LibraryItem.objects.create(user=self.user, work=self.unknown)
        edition = Edition.objects.create(work=self.unknown, publisher='Later new publisher')
        Work.objects.filter(pk=self.unknown.pk).update(default_edition=edition)
        reference = self.post([self.unknown.pk]).data['references'][0]
        self.assertEqual(reference['edition_source'], 'library_snapshot')
        self.assertIsNone(reference['edition_id'])
        self.assertEqual(reference['publisher'], '')
        self.assertIn('edition', reference['missing_fields'])
        self.assertIn('has not been substituted', ' '.join(reference['notices']))
        item.refresh_from_db()
        self.assertIsNone(item.reading_basis['edition_id'])
        self.assertEqual(self.post([self.unknown.pk], prefer_library_editions=False)
                         .data['references'][0]['publisher'], 'Later new publisher')

    def test_legacy_library_edition_without_snapshot_uses_its_own_record(self):
        LibraryItem.objects.filter(pk=self.item.pk).update(reading_basis={})
        Edition.objects.filter(pk=self.edition.pk).update(is_archived=True)
        reference = self.post().data['references'][0]
        self.assertEqual(reference['edition_source'], 'library_edition')
        self.assertEqual(reference['edition_id'], self.edition.pk)
        self.assertIn('archived', ' '.join(reference['notices']))

    def test_missing_metadata_is_marked_and_other_accounts_are_never_used(self):
        response = self.post([self.unknown.pk])
        reference = response.data['references'][0]
        self.assertEqual(reference['edition_source'], 'none')
        self.assertEqual(reference['authors'], [])
        self.assertEqual(reference['missing_fields'], ['author', 'edition', 'publisher', 'edition publication year', 'ISBN'])
        self.assertIn('400 BCE', response.data['plain_text'])
        self.assertNotIn('Other reader', str(response.data))

    def test_invalid_or_archived_catalog_defaults_are_not_exported(self):
        Edition.objects.filter(pk=self.edition.pk).update(is_archived=True)
        reference = self.post(prefer_library_editions=False).data['references'][0]
        self.assertEqual(reference['edition_source'], 'none')
        Edition.objects.filter(pk=self.edition.pk).update(is_archived=False)
        Work.objects.filter(pk=self.unknown.pk).update(default_edition=self.edition)
        self.assertEqual(self.post([self.unknown.pk]).data['references'][0]['edition_source'], 'none')

    def test_selection_is_ordered_deduplicated_and_uses_distinct_citation_keys(self):
        result = self.post([self.unknown.pk, self.work.pk, self.unknown.pk]).data
        self.assertEqual(result['count'], 2)
        self.assertEqual([row['work_id'] for row in result['references']], [self.unknown.pk, self.work.pk])
        self.assertEqual(result['bibtex'].count('@book{'), 2)
        self.assertEqual(result['bibtex'].count(f'@book{{marginalia{self.unknown.pk},'), 1)

    def test_nonbook_forms_do_not_invent_standalone_book_publication(self):
        for form in ['essay', 'short_story', 'poem', 'play']:
            with self.subTest(form=form):
                Work.objects.filter(pk=self.work.pk).update(form=form)
                result = self.post().data
                self.assertTrue(result['bibtex'].startswith('@misc{'))
                self.assertTrue(result['ris'].startswith('TY  - GEN'))
                self.assertIn('standalone book publication is not assumed',
                              ' '.join(result['references'][0]['notices']))

    def test_ris_control_characters_cannot_inject_entries(self):
        Work.objects.filter(pk=self.work.pk).update(title='Title\r\nER  -\nTY  - BOOK\u2028AU  - forged\x00')
        result = self.post().data
        self.assertEqual([line for line in result['ris'].splitlines() if line.startswith('TY  -')], ['TY  - BOOK'])
        self.assertEqual([line for line in result['ris'].splitlines() if line.startswith('ER  -')], ['ER  -'])
        self.assertEqual([line for line in result['ris'].splitlines() if line.startswith('AU  -')], ['AU  - Recorded Author'])
        self.assertNotIn('\x00', str(result))

    def test_tex_escaping_preserves_unicode_and_keeps_author_names_literal(self):
        title = r'Éthique {A} & 50% $x_1$ #2 ~ ^ \input{evil}'
        Work.objects.filter(pk=self.work.pk).update(title=title)
        Person.objects.filter(pk=self.author.pk).update(name='Research and Arts Collective')
        result = self.post().data
        self.assertIn(r'Éthique \textbraceleft{}A\textbraceright{} \& 50\% \$x\_1\$ \#2', result['bibtex'])
        self.assertIn(r'\textbackslash{}input\textbraceleft{}evil\textbraceright{}', result['bibtex'])
        self.assertIn('author = {{Research and Arts Collective}}', result['bibtex'])
        self.assertNotIn(r'\input{evil}', result['bibtex'])
        self.assertEqual(plain('e\u0301\t\r\n漢字\u202e'), 'é 漢字')
        self.assertEqual(tex('100%'), r'100\%')

    def test_unbalanced_literal_braces_cannot_end_bibtex_fields(self):
        for title in ['Opening { fragment', 'Closing } fragment']:
            with self.subTest(title=title):
                Work.objects.filter(pk=self.work.pk).update(title=title)
                output = self.post().data['bibtex']
                self.assertEqual(output.count('{'), output.count('}'))
                self.assertNotIn(r'\{', output)
                self.assertNotIn(r'\}', output)
                self.assertIn('author = {{Recorded Author}}', output)

    @skipUnless(shutil.which('bibtex'), 'Optional BibTeX command is not installed')
    def test_installed_bibtex_parser_preserves_fields_after_unbalanced_title_braces(self):
        # Exercise the real parser when available; no dependency is required
        # for ordinary installs. Only temporary export files are created.
        with tempfile.TemporaryDirectory(prefix='marginalia-bibtex-check-') as directory:
            folder = Path(directory)
            for index, title in enumerate(['Opening { fragment', 'Closing } fragment']):
                with self.subTest(title=title):
                    Work.objects.filter(pk=self.work.pk).update(title=title)
                    stem = f'reference{index}'
                    (folder / f'{stem}.bib').write_text(self.post().data['bibtex'], encoding='utf-8')
                    (folder / f'{stem}.aux').write_text(
                        '\\relax\n\\citation{*}\n\\bibstyle{plain}\n\\bibdata{' + stem + '}\n', encoding='utf-8')
                    result = subprocess.run([shutil.which('bibtex'), stem], cwd=folder,
                                            capture_output=True, text=True, timeout=15)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    parsed = (folder / f'{stem}.bbl').read_text(encoding='utf-8')
                    self.assertIn('Recorded Author', parsed)
                    self.assertIn('Catalog Publisher', parsed)
                    self.assertNotIn('empty author', result.stdout)

    def test_export_has_no_private_notes_no_database_writes_and_bounded_queries(self):
        before = list(LibraryItem.objects.order_by('pk').values())
        with CaptureQueriesContext(connection) as captured:
            response = self.post([self.work.pk, self.unknown.pk])
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(captured), 3)
        self.assertTrue(all(query['sql'].lstrip().upper().startswith('SELECT') for query in captured))
        self.assertEqual(before, list(LibraryItem.objects.order_by('pk').values()))
        self.assertFalse(MutationReceipt.objects.exists())
        self.assertNotIn('Never export private writing', str(response.data))
        self.assertNotIn('Other reader private writing', str(response.data))

    def test_export_requires_authentication_and_valid_bounded_selection(self):
        for ids in [[], [0], [-1], [True], ['1'], [1.5], [self.work.pk] * 201, [99999999]]:
            with self.subTest(ids=ids[:3]):
                self.assertEqual(self.post(ids).status_code, 400)
        self.assertEqual(self.post(notes='Do not accept arbitrary input').status_code, 400)
        Work.objects.filter(pk=self.work.pk).update(is_archived=True)
        self.assertEqual(self.post([self.unknown.pk, self.work.pk]).status_code, 400)
        self.client.force_authenticate(None)
        self.assertIn(self.post().status_code, [401, 403])
