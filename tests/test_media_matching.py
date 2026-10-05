import unittest

from research.media_matching import match_item_author, match_item_title, norm, same_author, same_title, words_in_order


class MediaMatchingTests(unittest.TestCase):
    def test_non_latin_titles_and_authors_match_without_collapsing(self):
        for title in ['紅樓夢', 'Война и мир', 'रामायण']:
            self.assertEqual(same_title(title, title), (True, 100))
        self.assertTrue(same_author(['李白'], ['李白']))
        self.assertFalse(same_author(['李白'], ['杜甫']))
        self.assertNotEqual(norm('राम'), norm('रम'))

    def test_accents_case_and_composed_unicode_are_normalized(self):
        self.assertEqual(same_title('ÉMILE', 'Emile'), (True, 100))
        self.assertEqual(norm('cafe\u0301'), norm('café'))
        self.assertEqual(words_in_order('Война и мир'), ['война', 'и', 'мир'])

    def test_empty_and_punctuation_only_titles_do_not_match(self):
        self.assertFalse(same_title('', '---')[0])
        self.assertFalse(same_author([''], ['']))

    def test_subtitle_and_volume_scope_are_not_guessed(self):
        self.assertFalse(same_title('War and Peace', 'War and Peace: A Study Guide')[0])
        self.assertFalse(same_title('Collected Poems', 'Collected Poems Volume 2')[0])
        self.assertEqual(same_title('The Republic', 'Republic'), (True, 98))

    def test_library_surname_and_life_dates(self):
        for found in ['Austen, Jane', 'Austen, Jane, 1775–1817', 'Austen, Jane (1775-1817)']:
            self.assertTrue(same_author(['Jane Austen'], [found]))
        self.assertTrue(same_author(['Victor Hugo'], ['Hugo, Victor (1802-1885). Auteur du texte']))
        self.assertFalse(same_author(['Jane Austen'], ['Austen, Jane, editor']))

    def test_initials_require_complete_surname_and_given_name_count(self):
        self.assertTrue(same_author(['John Ronald Reuel Tolkien'], ['Tolkien, J. R. R.']))
        self.assertFalse(same_author(['Jane Austen'], ['James Austen']))
        self.assertFalse(same_author(['Jane Austen'], ['Austen']))
        self.assertFalse(same_author(['John Ronald Reuel Tolkien'], ['John Tolkien']))

    def test_only_explicit_aliases_allow_translation_and_name_variants(self):
        item = {'title': 'The Brothers Karamazov', 'authors': ['Fyodor Dostoevsky']}
        self.assertFalse(match_item_title(item, 'Братья Карамазовы')[0])
        self.assertFalse(match_item_author(item, ['Фёдор Достоевский']))
        item.update(title_aliases=['Братья Карамазовы'], author_aliases=['Фёдор Достоевский'])
        self.assertTrue(match_item_title(item, 'Братья Карамазовы')[0])
        self.assertTrue(match_item_author(item, ['Фёдор Достоевский']))
        self.assertFalse(match_item_author(item, ['Anonymous']))
