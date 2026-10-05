"""Bibliographic evidence for a person's portrait, never edition equivalence.

Full titles can corroborate a biography. Short titles and omitted subtitles
need bibliographic context; a common word or a named research project cannot.
"""
from __future__ import annotations

from html.parser import HTMLParser
import re

from research.media_matching import norm, same_title, words_in_order


def portrait_work_records(item):
    aliases = item.get('work_aliases', {})
    records = []
    for work in item.get('works', item.get('authors', [])):
        record = dict(work) if isinstance(work, dict) else {'title': work}
        title = record.get('title')
        if not isinstance(title, str) or not title.strip():
            continue
        variants = [*record.get('title_aliases', []), *aliases.get(title, [])]
        records.append({**record, 'title_aliases': list(dict.fromkeys(
            value for value in variants if isinstance(value, str) and value.strip()))})
    return records


def _clean(value):
    return value.replace('\u00ad', '').replace('\ufeff', '')


_AUTHORED_SECTION = re.compile(
    r'^(?:(?:selected|major|notable|published|literary|principal|partial|complete) )?'
    r'(?:works|bibliography|publications|books|novels|essays|poetry|plays|short stories)'
    r'(?: by .+)?$', re.I)
_EXCLUDED_SECTION = re.compile(r'\b(?:references|further reading|sources|about|criticism|external links)\b', re.I)
_YEAR = re.compile(r'^\s*[,;:(\[]?\s*(?:published\s+)?(?:1\d{3}|20\d{2})(?!\d)')
_SCOPE = re.compile(r'\b(?:vol(?:ume)?s?|parts?|books?|tomes?)\.?\s+(?:\d+|[ivxlcdm]+|one|two|three)\b|'
                    r'\b(?:study guide|commentary|abridged|adaptation|retelling)\b', re.I)
_OTHER_CONTEXT = re.compile(r'\b(?:reviewed|discussed|read|praised|admired|criticized|critiqued|cited|'
                            r'quoted|translated|edited|illustrated|performed|adapted)\b', re.I)


class _Article(HTMLParser):
    """Retain title emphasis and section boundaries lost by plaintext extracts."""
    def __init__(self, value):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.text_length = 0
        self.titles = []
        self.emphasis = []
        self.heading = None
        self.sections = []
        self.exclusions = [(0, False)]
        self.authored = False
        self.ignored = 0
        self.feed(_clean(value))
        self.close()
        self.text = ''.join(self.parts)
        ends = [start for start, _ in self.exclusions[1:]] + [len(self.text)]
        # Tokenize once per response, retaining block/section boundaries.
        self.blocks = [words_in_order(line) for (start, excluded), end in zip(self.exclusions, ends)
                       if not excluded for line in self.text[start:end].splitlines() if line.strip()]

    def excluded_at(self, offset):
        return next(excluded for start, excluded in reversed(self.exclusions) if start <= offset)

    def _append(self, value):
        self.parts.append(value)
        self.text_length += len(value)

    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style'}:
            self.ignored += 1
        if self.ignored:
            return
        if re.fullmatch(r'h[1-6]', tag):
            self._append('\n')
            self.heading = (int(tag[1]), self.text_length)
        elif tag in {'p', 'li', 'div', 'br', 'tr', 'section'}:
            self._append('\n')
        elif tag in {'i', 'em', 'cite'}:
            self.emphasis.append((tag, self.text_length, self.authored))

    def handle_endtag(self, tag):
        if tag in {'script', 'style'}:
            self.ignored = max(0, self.ignored - 1)
            return
        if self.ignored:
            return
        if self.heading and re.fullmatch(r'h[1-6]', tag):
            level, start = self.heading
            label = ' '.join(''.join(self.parts)[start:].split())
            while self.sections and self.sections[-1][0] >= level:
                self.sections.pop()
            inherited = self.sections[-1][1] if self.sections else False
            excluded = bool(_EXCLUDED_SECTION.search(label) or
                            (self.sections and self.sections[-1][2]))
            authored = (not excluded and
                        (bool(_AUTHORED_SECTION.fullmatch(label)) or inherited))
            self.sections.append((level, authored, excluded))
            self.exclusions.append((start, excluded))
            self.authored = authored
            self.heading = None
            self._append('\n')
        elif tag in {'i', 'em', 'cite'} and self.emphasis:
            # Unbalanced markup never manufactures a bibliographic title.
            if self.emphasis[-1][0] == tag:
                _, start, authored = self.emphasis.pop()
                value = ''.join(self.parts)[start:self.text_length]
                if value.strip() and '\n' not in value:
                    self.titles.append((value.strip(), start, self.text_length, authored))
            else:
                self.emphasis.clear()
        elif tag in {'p', 'li', 'div', 'tr', 'section'}:
            self._append('\n')

    def handle_data(self, data):
        if not self.ignored:
            self._append(data)


def _contains(title, article):
    needle = words_in_order(title)
    return bool(needle and any(hay[i:i + len(needle)] == needle for hay in article.blocks
                              for i in range(len(hay) - len(needle) + 1)))


def _bibliographic(title, article):
    def conflicting_context(start, end):
        before = re.split(r'[.!?\n;]', article.text[max(0, start - 120):start])[-1]
        after = article.text[end:end + 80]
        # Publication dates do not turn reviews, translations, or another
        # author's explicitly credited book into this person's own work.
        return bool(_OTHER_CONTEXT.search(before) or
                    re.match(r'^\s*(?:\(\s*(?:1\d{3}|20\d{2})\s*\))?\s*,?\s+by\s+\w', after, re.I))

    for value, start, end, authored in article.titles:
        if article.excluded_at(start) or conflicting_context(start, end) or not same_title(title, value)[0]:
            continue
        before = article.text[max(0, start - 100):start]
        # Explicit authorship verbs must be local to this sentence. A review,
        # quotation or passing admiration of another book does not suffice.
        clause = re.split(r'[.!?\n;]', before)[-1]
        own_work = bool(re.search(r'\b(?:wrote|authored|published)\s+(?:(?:the|a|his|her|their)\s+)?'
                                 r'(?:(?:book|novel|essay|play|poem)\s+)?$', clause, re.I))
        if authored or own_work or _YEAR.match(article.text[end:end + 40]):
            return True
    # Plain extracts still carry compact publication dates. Exact casing and
    # punctuation prevent generic lower-case prose from opening short titles.
    pattern = r'(?<!\w)' + re.escape(title) + r'(?!\w)'
    return any(not article.excluded_at(match.start()) and not conflicting_context(match.start(), match.end())
               and _YEAR.match(article.text[match.end():match.end() + 40])
               for match in re.finditer(pattern, article.text))


def corroborated_works(works, text, work_aliases=None):
    if not isinstance(text, str) or not text:
        return []
    article = _Article(text)
    records = portrait_work_records({'works': works, 'work_aliases': work_aliases or {}})
    matched = []
    for record in records:
        for title in [record['title'], *record['title_aliases']]:
            # Keep exact full-title matching, with extra support for short
            # titles such as It or The Road in actual lists of authored works.
            if (_contains(title, article) and
                    (len(norm(title)) >= 8 or _bibliographic(title, article))):
                matched.append(record['title'])
                break
            # A subtitle is often absent in a biography, but only an explicitly
            # bibliographic main title can establish the relationship. Never
            # truncate one-word geographic/person/project names in prose.
            main, separator, subtitle = title.partition(':')
            main = main.strip()
            if (separator and not _SCOPE.search(title)
                    and subtitle.strip() and len(words_in_order(main)) >= 2 and len(norm(main)) >= 6
                    and _bibliographic(main, article)):
                matched.append(record['title'])
                break
    return list(dict.fromkeys(matched))
