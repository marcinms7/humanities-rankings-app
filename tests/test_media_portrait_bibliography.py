import unittest

from research.media_portrait_bibliography import matched_work_titles


def work(title, author='OL31197A', **extra):
    return {'title': title, 'authors': [{'type': {'key': '/type/author_role'},
            'author': {'key': '/authors/' + author}}], **extra}


class PortraitBibliographyTests(unittest.TestCase):
    def test_cached_distinctive_subtitles_can_be_omitted_in_authored_records(self):
        for person, expected, found, key in [
            ('Vijay Prashad', 'The Darker Nations: A People’s History of the Third World',
             'The Darker Nations', 'OL31197A'),
            ('Marcel van der Linden', 'Workers of the World: Essays toward a Global Labor History',
             'Workers of the World', 'OL1569604A'),
        ]:
            with self.subTest(person=person):
                item = {'title': person, 'works': [expected]}
                self.assertEqual(matched_work_titles(item, [work(found, key)], author_key=key), [expected])
                self.assertEqual(matched_work_titles(item, [found]), [])

    def test_reviewed_alias_matches_exactly_and_returns_canonical_title(self):
        item = {'title': 'Andreas Vesalius', 'works': ['On the Fabric of the Human Body'],
                'work_aliases': {'On the Fabric of the Human Body': ['De Humani Corporis Fabrica Libri Septem']}}
        self.assertEqual(matched_work_titles(item, ['De Humani Corporis Fabrica Libri Septem']), item['works'])
        item.pop('work_aliases')
        self.assertEqual(matched_work_titles(item, ['De Humani Corporis Fabrica Libri Septem']), [])

    def test_exact_titles_do_not_need_relaxed_evidence_for_plain_strings(self):
        item = {'title': 'Example Author', 'works': ['The Republic', 'War and Peace']}
        self.assertEqual(matched_work_titles(item, ['Republic', 'War and Peace']), item['works'])

    def test_reciprocal_author_role_is_required_for_dictionary_records(self):
        item = {'title': 'Vijay Prashad', 'works': ['The Darker Nations: A People’s History of the Third World']}
        for record in [
            {'title': 'The Darker Nations'},
            work('The Darker Nations', 'OL999A'),
            {'title': 'The Darker Nations', 'authors': [{'author': {'key': 'OL31197A'}}]},
            {'title': 'The Darker Nations', 'authors': [{'author': {'key': '/authors/OL31197A/other'}}]},
        ]:
            with self.subTest(record=record):
                self.assertEqual(matched_work_titles(item, [record], author_key='OL31197A'), [])
        self.assertEqual(matched_work_titles(item, [work('The Darker Nations')], author_key='OL31197'), [])
        self.assertEqual(matched_work_titles(item, [work('The Darker Nations')], author_key='/authors/OL31197A'), item['works'])

    def test_translator_and_editor_roles_cannot_corroborate_even_exact_title(self):
        item = {'title': 'Vijay Prashad', 'works': ['The Darker Nations']}
        for role in ['translator', 'editor', 'illustrator', {'key': 'author'}]:
            record = work('The Darker Nations')
            record['authors'][0]['role'] = role
            with self.subTest(role=role):
                self.assertEqual(matched_work_titles(item, [record], author_key='OL31197A'), [])
        record['authors'].append({'author': {'key': '/authors/OL31197A'}, 'role': 'author'})
        self.assertEqual(matched_work_titles(item, [record], author_key='OL31197A'), item['works'])

    def test_generic_short_or_collection_titles_are_not_relaxed(self):
        for expected, found in [('China: A Macro History', 'China'),
                                ('Vermeer: His Art', 'Vermeer'),
                                ('Collected Poems: An Anthology', 'Collected Poems'),
                                ('The Nude: A Study of Ideal Art', 'The Nude')]:
            with self.subTest(expected=expected):
                self.assertEqual(matched_work_titles({'title': 'Example Author', 'works': [expected]},
                    [work(found)], author_key='OL31197A'), [])

    def test_subtitle_conflicts_and_derivative_works_are_not_discarded(self):
        item = {'title': 'Vijay Prashad', 'works': ['The Darker Nations: A People’s History of the Third World']}
        for found in [work('The Darker Nations', subtitle='A Study Guide'),
                      work('The Darker Nations: A Different Book'),
                      work('The Darker Nations: A Study Guide')]:
            self.assertEqual(matched_work_titles(item, [found], author_key='OL31197A'), [])
        for expected in ['The Darker Nations: A Study Guide', 'The Darker Nations: Volume 2']:
            self.assertEqual(matched_work_titles({'title': 'Vijay Prashad', 'works': [expected]},
                [work('The Darker Nations')], author_key='OL31197A'), [])

    def test_structured_subtitle_can_complete_an_exact_title(self):
        expected = 'The Darker Nations: A People’s History of the Third World'
        self.assertEqual(matched_work_titles({'title': 'Vijay Prashad', 'works': [expected]},
            [work('The Darker Nations', subtitle='A People’s History of the Third World')],
            author_key='OL31197A'), [expected])

    def test_remote_structured_subtitle_cannot_be_hidden_by_exact_main_title(self):
        item = {'title': 'Vijay Prashad', 'works': ['The Darker Nations']}
        self.assertEqual(matched_work_titles(item, [work('The Darker Nations', subtitle='A Study Guide')],
            author_key='OL31197A'), [])

    def test_cached_authored_bundle_titles_can_corroborate_person_only(self):
        for person, expected, found, key in [
            ('Steven Erikson', 'Malazan Book of the Fallen', 'Malazan Book of the Fallen : Books 1-4', 'OL1394250A'),
            ('Robin Hobb', 'The Liveship Traders trilogy', 'Liveship Traders Trilogy 3-Book Bundle', 'OL395837A'),
            ('Fonda Lee', 'The Green Bone Saga', 'The Green Bone Saga Series 3 Books Collection Set By Fonda Lee', 'OL7469465A'),
        ]:
            with self.subTest(person=person):
                item = {'title': person, 'works': [expected]}
                self.assertEqual(matched_work_titles(item, [work(found, key)], author_key=key), [expected])
                self.assertEqual(matched_work_titles(item, [found]), [])

    def test_bundle_byline_requires_compatible_complete_author(self):
        item = {'title': 'Fonda Lee', 'works': ['The Green Bone Saga']}
        for byline in ['Fiona Lee', 'Lee', 'Fonda Lee and John Smith']:
            self.assertEqual(matched_work_titles(item,
                [work('The Green Bone Saga Series 3 Books Collection Set By ' + byline)],
                author_key='OL31197A'), [])

    def test_unbounded_bundle_suffixes_and_partial_words_are_rejected(self):
        item = {'title': 'Fonda Lee', 'works': ['The Green Bone Saga']}
        for found in ['The Green Bone Sagaology Series 3 Books Collection Set',
                      'The Green Bone Saga Study Guide 3 Book Bundle',
                      'The Green Bone Saga and Other Stories',
                      'The Green Bone Saga Series 3 Books Collection Set plus Extras',
                      'The Green Bone Saga: Books 4-1', 'The Green Bone Saga: Book 2']:
            self.assertEqual(matched_work_titles(item, [work(found)], author_key='OL31197A'), [])

    def test_volume_scope_cannot_be_relaxed(self):
        for expected, found in [('Collected Essays Volume 1', 'Collected Essays Volume 2'),
                                ('Malazan Book of the Fallen Book 1', 'Malazan Book of the Fallen Book 1 3 Book Bundle'),
                                ('Workers of the World: Volume II', 'Workers of the World')]:
            self.assertEqual(matched_work_titles({'title': 'Example Author', 'works': [expected]},
                [work(found)], author_key='OL31197A'), [])

    def test_parenthetical_series_requires_matching_explicit_metadata(self):
        expected = 'Workers and Peasants in the Modern Middle East'
        found = expected + ' (The Contemporary Middle East)'
        item = {'title': 'Joel Beinin', 'works': [expected]}
        self.assertEqual(matched_work_titles(item, [work(found)], author_key='OL31197A'), [])
        self.assertEqual(matched_work_titles(item, [work(found, series=['Unrelated Series'])], author_key='OL31197A'), [])
        self.assertEqual(matched_work_titles(item, [work(found, series=['The Contemporary Middle East'])], author_key='OL31197A'), [expected])

    def test_results_preserve_canonical_order_without_duplicates(self):
        item = {'title': 'Example Author', 'works': ['Second Work', 'First Work', 'Second Work']}
        self.assertEqual(matched_work_titles(item, ['First Work', 'Second Work', 'Second Work']), ['Second Work', 'First Work'])

    def test_non_openlibrary_dictionaries_only_support_exact_titles(self):
        item = {'title': 'Vijay Prashad', 'works': ['The Darker Nations: A People’s History of the Third World']}
        self.assertEqual(matched_work_titles(item, [work('The Darker Nations')]), [])
        self.assertEqual(matched_work_titles(item, [{'title': item['works'][0]}]), item['works'])

    def test_malformed_series_metadata_cannot_grant_parenthesis_removal(self):
        item = {'title': 'Joel Beinin', 'works': ['Workers and Peasants in the Modern Middle East']}
        for metadata in [7, {'The Contemporary Middle East': True}, [None, 7]]:
            self.assertEqual(matched_work_titles(item,
                [work(item['works'][0] + ' (The Contemporary Middle East)', series=metadata)],
                author_key='OL31197A'), [])
