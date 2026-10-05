import unittest

from research.media_text_evidence import corroborated_works, portrait_work_records


class PortraitTextEvidenceTests(unittest.TestCase):
    def test_short_title_in_authored_bibliography(self):
        self.assertEqual(corroborated_works(['It'], '<h2>Bibliography</h2><ul><li><i>It</i></li></ul>'), ['It'])

    def test_nested_markup_and_inherited_section(self):
        self.assertEqual(corroborated_works(['The Road'], '<h2>Works</h2><h3>Novels</h3><p><i>The <span>Road</span></i></p>'), ['The Road'])

    def test_references_and_about_sections_do_not_supply_short_evidence(self):
        for heading in ['References', 'Further reading', 'Works about the author']:
            self.assertEqual(corroborated_works(['It'], f'<h2>{heading}</h2><p><i>It</i></p>'), [])
            self.assertEqual(corroborated_works(['It'], f'<h2>{heading}</h2><h3>Books</h3><p><i>It</i> (1986)</p>'), [])

    def test_common_prose_and_review_do_not_supply_evidence(self):
        for text in ['It was a long journey.', 'She admired <i>It</i>.', 'He reviewed the novel <i>It</i>.',
                     'She reviewed <i>It</i> (1986) in a magazine.', 'She reviewed It (1986).']:
            self.assertEqual(corroborated_works(['It'], text), [])

    def test_dates_do_not_override_other_authorship_or_excluded_sections(self):
        for text in ['She discussed <i>The Nude</i> (1956), by Kenneth Clark.',
                     'She discussed The Nude (1956), by Kenneth Clark.',
                     '<h2>Bibliography</h2><i>The Nude</i> (1956), by Kenneth Clark.']:
            self.assertEqual(corroborated_works(['The Nude: A Study of Ideal Art'], text), [])
        self.assertEqual(corroborated_works(['The Magic Mountain'], '<h2>Further reading</h2><i>The Magic Mountain</i>'), [])

    def test_explicit_authorship(self):
        self.assertEqual(corroborated_works(['It'], 'He wrote the novel <i>It</i>.'), ['It'])

    def test_plain_publication_year(self):
        title = 'The Nude: A Study of Ideal Art'
        self.assertEqual(corroborated_works([title], "Clark's The Nude (1956, based on his lectures)"), [title])

    def test_reject_generic_subtitle_and_project(self):
        self.assertEqual(corroborated_works(['China: A Macro History'], 'Science and Civilisation in China (1954)'), [])
        self.assertEqual(corroborated_works(['Sage Philosophy: Indigenous Thinkers'], 'best known for "Sage Philosophy". It was a project'), [])
        self.assertEqual(corroborated_works(['Vermeer'], 'monographs on masters such as Vermeer'), [])

    def test_reviewed_alias_returns_canonical(self):
        title = 'The Magic Mountain'
        self.assertEqual(corroborated_works([title], '<i>Der Zauberberg</i>', {title: ['Der Zauberberg']}), [title])
        self.assertEqual(corroborated_works([title], '<i>Der Zauberberg</i>'), [])

    def test_no_partial_volume_match(self):
        self.assertEqual(corroborated_works(['History Volume II'], 'History Volume III was published.'), [])
        self.assertEqual(corroborated_works(['Roman History: Volume II'], '<h2>Works</h2><i>Roman History</i>'), [])
        self.assertEqual(corroborated_works(['The Magic Mountain: Study Guide'], '<h2>Works</h2><i>The Magic Mountain</i>'), [])

    def test_unicode_and_soft_hyphen(self):
        self.assertEqual(corroborated_works(['The Invisible Cities'], 'The Invi\u00adsible Cities'), ['The Invisible Cities'])
        self.assertEqual(corroborated_works(['कामायनी'], '<h2>Works</h2><i>कामायनी</i>'), ['कामायनी'])

    def test_scripts_and_malformed_emphasis_do_not_supply_evidence(self):
        self.assertEqual(corroborated_works(['It'], '<script>It (1986)</script>'), [])
        self.assertEqual(corroborated_works(['It'], '<h2>Works</h2><i>It</em>'), [])

    def test_work_aliases_merge_without_changing_titles(self):
        self.assertEqual(portrait_work_records({'works': [{'title': 'A', 'title_aliases': ['B']}], 'work_aliases': {'A': ['B', 'C']}}),
                         [{'title': 'A', 'title_aliases': ['B', 'C']}])
