import json
import unittest
from urllib.parse import parse_qs, urlsplit

from research import media_library_sources as sources


class LibrarySourcesTests(unittest.TestCase):
    def setUp(self):
        self.book = {'id': 1, 'title': 'Les Misérables', 'authors': ['Victor Hugo']}
        self.person = {'id': 2, 'title': 'Victor Hugo', 'works': ['Les Misérables']}
        self.calls = []

    def fetcher(self, *responses):
        responses = iter(responses)

        def fetch(url, **kwargs):
            self.calls.append((url, kwargs))
            return next(responses)
        return fetch

    def sru(self, title='Les Misérables ([Edition illustrée]) / par V. Hugo', creator='Hugo, Victor (1802-1885). Auteur du texte', description='', subject=''):
        return f'''<srw:searchRetrieveResponse xmlns:srw="http://www.loc.gov/zing/srw/" xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" xmlns:dc="http://purl.org/dc/elements/1.1/">
        <srw:records><srw:record><srw:recordData><oai_dc:dc>
        <dc:title>{title}</dc:title><dc:creator>{creator}</dc:creator>
        <dc:identifier>https://gallica.bnf.fr/ark:/12148/bpt6k6566991v</dc:identifier>
        <dc:rights>public domain</dc:rights><dc:description>{description}</dc:description><dc:subject>{subject}</dc:subject>
        </oai_dc:dc></srw:recordData></srw:record></srw:records></srw:searchRetrieveResponse>'''.encode()

    def manifest(self, *labels):
        return {'attribution': 'Bibliothèque nationale de France', 'license': 'https://gallica.bnf.fr/conditions',
            'sequences': [{'canvases': [{'label': label, 'images': [{'resource': {'service': {
                '@id': f'https://gallica.bnf.fr/iiif/ark:/12148/bpt6k6566991v/f{index}'}}}]} for index, label in enumerate(labels, 1)]}]}

    def test_gallica_live_shape_preserves_binding_and_title_page_labels(self):
        rows = sources.candidates(self.book, 'gallica-covers', self.fetcher(self.sru(), self.manifest('plat supérieur', 'NP', 'page de titre')))
        self.assertEqual([row['depiction_kind'] for row in rows], ['digitized_binding', 'title_page'])
        self.assertIn('/f3/full/600,/0/native.jpg', rows[1]['image_url'])
        self.assertIn('public domain', rows[0]['rights'])
        self.assertTrue(self.calls[0][1]['raw'])
        self.assertIn('dc.creator all "Victor Hugo"', parse_qs(urlsplit(self.calls[0][0]).query)['query'][0])
        self.assertEqual(self.calls[1][0], 'https://gallica.bnf.fr/iiif/ark:/12148/bpt6k6566991v/manifest.json')

    def test_gallica_rejects_namesake_wrong_author_and_partial_volume(self):
        for title, author in [('Les Misérables', 'Hugo, Charles (1826-1871). Auteur du texte'), ('Les Misérables. Tome 1 / Victor Hugo', 'Victor Hugo')]:
            self.calls.clear()
            self.assertEqual(sources.candidates(self.book, 'gallica-covers', self.fetcher(self.sru(title, author))), [])
            self.assertEqual(len(self.calls), 1)

    def test_gallica_arbitrary_scan_is_not_called_cover(self):
        self.assertEqual(sources.candidates(self.book, 'gallica-covers', self.fetcher(self.sru(), self.manifest('NP', '1', '2'))), [])

    def test_gallica_portrait_requires_identity_evidence(self):
        raw = self.sru('Portrait de Victor Hugo', 'A photographer', subject='Hugo, Victor (1802-1885)')
        self.assertEqual(sources.candidates(self.person, 'gallica-portraits', self.fetcher(raw, b'<empty/>')), [])
        raw = self.sru('Portrait de Victor Hugo', 'A photographer', 'Auteur des Misérables. Les Misérables est son roman.', 'Hugo, Victor (1802-1885)')
        rows = sources.candidates(self.person, 'gallica-portraits', self.fetcher(raw, self.manifest('NP')))
        self.assertEqual(rows[0]['identity_evidence'], ['Catalog work mentioned: Les Misérables'])
        self.assertEqual(rows[0]['depiction_kind'], 'historical_depiction')

    def test_gallica_rejects_entity_payload(self):
        with self.assertRaises(ValueError):
            list(sources._dc_records(b'<!DOCTYPE foo [<!ENTITY x "test">]><foo/>'))

    def test_loc_rejects_generic_icon_restricted_item_and_wrong_author(self):
        record = {'id': 'http://www.loc.gov/item/1/', 'title': 'Les Misérables / Victor Hugo',
            'contributor': ['Hugo, Victor, 1802-1885'],
            'image_url': ['https://www.loc.gov/static/images/books.gif', '//cdn.loc.gov/service/rbc/1.jpg']}
        rows = sources.candidates(self.book, 'loc-covers', self.fetcher({'results': [record, {**record, 'access_restricted': True}, {**record, 'contributor': ['Charles Hugo']}]}))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['image_url'], 'https://cdn.loc.gov/service/rbc/1.jpg')
        self.assertEqual(rows[0]['depiction_kind'], 'digitized_book_preview')

    def test_loc_portrait_name_alone_rejected_but_corroborated_dates_accepted(self):
        record = {'id': 'https://www.loc.gov/item/1/', 'title': '[Victor Hugo]', 'subject': ['Hugo, Victor, 1802-1885'],
            'image_url': ['https://cdn.loc.gov/service/pnp/1.jpg']}
        self.assertEqual(sources.candidates(self.person, 'loc-portraits', self.fetcher({'results': [record]}, {'results': []})), [])
        rows = sources.candidates({**self.person, 'birth_year': 1802, 'death_year': 1885}, 'loc-portraits', self.fetcher({'results': [record]}))
        self.assertEqual(rows[0]['identity_evidence'], ['Corroborated life dates: 1802–1885'])

    def test_portrait_can_corroborate_identity_against_same_library_catalog_work(self):
        portrait = self.sru('Portrait de Victor Hugo', 'A photographer', subject='Hugo, Victor (1802-1885). Personne représentée')
        rows = sources.candidates(self.person, 'gallica-portraits', self.fetcher(portrait, self.sru(), self.manifest('NP')))
        self.assertIn('author of catalog work Les Misérables', rows[0]['identity_evidence'][0])
        wrong_dates = self.sru(creator='Hugo, Victor (1902-1985). Auteur du texte')
        self.assertEqual(sources.candidates(self.person, 'gallica-portraits', self.fetcher(portrait, wrong_dates)), [])

    def test_iiif_v3_and_malicious_image_hosts(self):
        manifest = {'items': [{'label': {'en': ['Title page']}, 'items': [{'items': [{'body': {'service': [{'id': 'https://gallica.bnf.fr/iiif/ark:/12148/bpt6k6566991v/f4'}]}}]}]}]}
        rows = sources.candidates(self.book, 'gallica-covers', self.fetcher(self.sru(), manifest))
        self.assertEqual(rows[0]['depiction_kind'], 'title_page')
        manifest = self.manifest('front cover')
        manifest['sequences'][0]['canvases'][0]['images'][0]['resource']['service']['@id'] = 'https://gallica.bnf.fr.evil.test/iiif/ark:/12148/bpt6k6566991v/f1'
        self.assertEqual(sources.candidates(self.book, 'gallica-covers', self.fetcher(self.sru(), manifest)), [])

    def page(self, **overrides):
        book = {'@type': 'Book', 'name': 'Les Misérables', 'author': {'@type': 'Person', 'name': 'Victor Hugo'},
            'isbn': '9780140444308', 'image': {'url': 'https://images.penguinrandomhouse.com/cover/9780140444308'}, **overrides}
        return ('<html><script type="application/ld+json">' + json.dumps({'@type': 'WebPage', 'mainEntity': book}) + '</script></html>').encode()

    def publisher_item(self, **overrides):
        return {**self.book, 'source_urls': ['https://www.penguinrandomhouse.com/books/1/les-miserables/'], **overrides}

    def test_publisher_requires_book_metadata_and_robots_with_exact_hosts(self):
        rows = sources.publisher_candidates(self.publisher_item(), self.fetcher(self.page()))
        self.assertEqual(len(rows), 1)
        self.assertTrue(self.calls[0][1]['respect_robots'])
        self.assertEqual(self.calls[0][1]['allowed_hosts'], {'www.penguinrandomhouse.com'})
        self.assertTrue(rows[0]['image_respect_robots'])
        self.assertEqual(rows[0]['matched_isbns'], ['9780140444308'])
        self.calls.clear()
        self.assertEqual(sources.publisher_candidates(self.publisher_item(source_urls=['https://www.penguinrandomhouse.com.evil.test/books/1/']), self.fetcher()), [])
        self.assertEqual(self.calls, [])

    def test_publisher_does_not_accept_wrong_redirected_book_or_unknown_image_host(self):
        for changes in ({'name': 'No Farm, No Foul', 'author': 'Peg Cochran'}, {'image': 'https://evil.test/image.jpg'}, {'@type': 'Product'}, {'author': 'Charles Hugo'}):
            self.assertEqual(sources.publisher_candidates(self.publisher_item(), self.fetcher(self.page(**changes))), [])

    def test_publisher_credential_seed_is_never_requested_or_saved_in_credit(self):
        public = 'https://www.penguinrandomhouse.com/books/1/?edition=paperback'
        forbidden = [
            'https://www.penguinrandomhouse.com/books/1/?token=private-value',
            'https://www.penguinrandomhouse.com/books/1/?ISBN=9780140444308&API_KEY=private-value',
            'https://www.penguinrandomhouse.com/books/1/?%61ccess_token=private-value',
        ]
        rows = sources.publisher_candidates(self.publisher_item(source_urls=[*forbidden, public]), self.fetcher(self.page()))
        self.assertEqual([url for url, _ in self.calls], [public])
        self.assertEqual(rows[0]['source'], public)
        self.assertNotIn('private-value', json.dumps(rows))

    def test_publisher_discovered_credential_link_is_never_followed(self):
        search = '<a href="/product/private/?signature=private-value">private</a><a href="/product/public/">public</a>'
        page = self.page(image='https://www.faber.co.uk/media/cover.jpg')
        rows = sources.publisher_candidates({**self.book, 'publishers': ['Faber']}, self.fetcher(search, page))
        self.assertEqual(len(self.calls), 2)
        self.assertTrue(self.calls[1][0].endswith('/product/public/'))
        self.assertNotIn('private-value', json.dumps(rows))

    def test_publisher_isbn10_equivalent_passes_but_conflict_or_absence_rejected(self):
        item = self.publisher_item(isbns=['0140444300'])
        self.assertEqual(len(sources.publisher_candidates(item, self.fetcher(self.page()))), 1)
        for isbn in ['9780425282021', None, '9780140444309']:
            self.assertEqual(sources.publisher_candidates(item, self.fetcher(self.page(isbn=isbn))), [])

    def test_publisher_bounded_search_needs_recorded_publisher_hint(self):
        results = '<a href="/product/1/">one</a><a href="https://evil.test/product/2/">bad</a><a href="/product/2/">two</a>'
        page = self.page(image='https://www.faber.co.uk/media/cover.jpg')
        rows = sources.publisher_candidates({**self.book, 'publishers': ['Faber & Faber']}, self.fetcher(results, page, page))
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(self.calls), 3)
        self.assertIn('post_type=product', self.calls[0][0])
        self.assertTrue(all(kwargs['respect_robots'] for _, kwargs in self.calls))

    def test_provider_outage_is_not_converted_to_no_match(self):
        def failing(*args, **kwargs):
            raise TimeoutError('provider temporarily unavailable')
        with self.assertRaises(TimeoutError):
            sources.candidates(self.book, 'loc-covers', failing)

    def test_portrait_evidence_cannot_borrow_other_subject_dates_or_title_substrings(self):
        person = {'title': 'John Smith', 'works': ['The Republic'], 'birth_year': 1800, 'death_year': 1850}
        evidence = sources._portrait_identity(person, ['Smith, John', 'Jones, Bob, 1800-1850'], 'John Smith', ['He wrote The Republican.'])
        self.assertEqual(evidence, [])

    def test_unavailable_publisher_page_advances_to_next_candidate(self):
        def fetch(url, **kwargs):
            if '/missing/' in url:
                raise sources.CandidateRejected('HTTP 404')
            return self.page()
        item = self.publisher_item(source_urls=['https://www.penguinrandomhouse.com/missing/', 'https://www.penguinrandomhouse.com/books/1/'])
        self.assertEqual(len(sources.publisher_candidates(item, fetch)), 1)

    def test_loc_uses_item_details_when_search_has_no_bibliographic_author(self):
        record = {'id': 'https://www.loc.gov/item/1/', 'title': 'Les Misérables', 'image_url': ['https://cdn.loc.gov/service/rbc/1.jpg']}
        details = {'item': {**record, 'item': {'contributor_names': ['Hugo, Victor, 1802-1885'], 'rights': ['Public domain']}}}
        rows = sources.candidates(self.book, 'loc-covers', self.fetcher({'results': [record]}, details))
        self.assertEqual(rows[0]['matched_authors'], ['Hugo, Victor, 1802-1885'])
        self.assertEqual(rows[0]['rights'], 'Public domain')
        self.assertTrue(self.calls[1][0].endswith('/item/1/?fo=json'))

    def test_unavailable_gallica_manifest_advances_to_another_verified_record(self):
        first = self.sru().decode()
        record = first.split('<srw:record>')[1].split('</srw:record>')[0]
        second = record.replace('bpt6k6566991v', 'bpt6k6566992w')
        raw = first.replace('</srw:records>', '<srw:record>' + second + '</srw:record></srw:records>').encode()
        def fetch(url, **kwargs):
            if '/SRU?' in url:
                return raw
            if 'bpt6k6566991v' in url:
                raise sources.CandidateRejected('HTTP 404')
            return self.manifest('page de titre')
        rows = sources.candidates(self.book, 'gallica-covers', fetch)
        self.assertEqual(len(rows), 1)
        self.assertIn('bpt6k6566992w', rows[0]['source'])

    def test_missing_authority_book_advances_to_next_known_work(self):
        person = {**self.person, 'works': ['A Missing Work', 'Les Misérables']}
        def fetch(url, **kwargs):
            if 'A+Missing+Work' in url:
                raise sources.CandidateRejected('HTTP 404')
            return self.sru()
        rows = sources._authorities(person, 'gallica-portraits', fetch)
        self.assertEqual(rows[0]['work'], 'Les Misérables')


if __name__ == '__main__':
    unittest.main()
