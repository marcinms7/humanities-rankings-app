"""Bibliographic identity evidence for portraits, never cover/edition identity.

Relaxed title forms require an explicit reciprocal Open Library author role.
Callers must independently check the person's complete name against that author.
Plain strings (including search ``top_work`` hints) only support exact titles or
reviewed aliases. No translations or arbitrary shortened titles are inferred.
"""
from __future__ import annotations

import re

from research.media_matching import norm, same_author, same_title, words_in_order
from research.media_text_evidence import portrait_work_records


POLICY_VERSION = 'portrait-structured-bibliography-v1'
_AUTHOR = re.compile(r'(?:/authors/)?(OL[1-9]\d*A)')
_AUTHOR_REFERENCE = re.compile(r'/authors/(OL[1-9]\d*A)')
_STOPWORDS = {
    'a', 'an', 'the', 'and', 'or', 'of', 'on', 'in', 'at', 'to', 'for', 'from',
    'by', 'with', 'into', 'toward', 'towards', 'collected', 'selected', 'complete',
    'works', 'book', 'books', 'volume', 'volumes', 'poems', 'poetry', 'essays',
    'letters', 'stories', 'trilogy', 'series', 'saga', 'cycle', 'sequence',
}
_SCOPE = re.compile(
    r'\b(?:vol(?:ume)?s?|books?|parts?|tomes?)\.?\s+'
    r'(?:\d+|[ivxlcdm]+|one|two|three|four|five|six|seven|eight|nine|ten)\b', re.I)
_DERIVATIVE = re.compile(
    r'\b(?:study\s+guides?|summar(?:y|ies)|companion|commentar(?:y|ies)|'
    r'workbooks?|adaptations?|abridg(?:ed|ement|ment)|retellings?)\b', re.I)
_BUNDLE = re.compile(
    r'(?:(?:series|trilogy)\s+)?(?:[1-9]\d?\s+books?\s+)'
    r'(?:bundle|collection(?:\s+set)?|set)')
_BOOK_RANGE = re.compile(r'books\s+([1-9]\d?)\s*[-–—]\s*([1-9]\d?)', re.I)


def _strings(value):
    if isinstance(value, str):
        return [value]
    return [item for item in value if isinstance(item, str)] if isinstance(value, (list, tuple)) else []


def _distinctive(title):
    tokens = [word for word in words_in_order(title) if word not in _STOPWORDS]
    return len(tokens) >= 2 and len(norm(title)) >= 10 and not _SCOPE.search(title)


def _reciprocal_author(record, author_key):
    expected = _AUTHOR.fullmatch(author_key) if isinstance(author_key, str) else None
    if not expected or not isinstance(record.get('authors'), list):
        return False
    for entry in record['authors']:
        if not isinstance(entry, dict) or not isinstance(entry.get('author'), dict):
            continue
        key = entry['author'].get('key')
        matched = _AUTHOR_REFERENCE.fullmatch(key) if isinstance(key, str) else None
        if not matched or matched[1] != expected[1]:
            continue
        # Open Library's ordinary author role omits ``role``. Other explicit
        # roles must not turn a translator/editor into the work's author.
        kind = entry.get('type', {})
        if kind and (not isinstance(kind, dict) or kind.get('key') != '/type/author_role'):
            continue
        role = entry.get('role')
        if role is None or (isinstance(role, str) and role.strip().casefold() in {'', 'author'}):
            return True
    return False


def _tokens_without_article(value):
    tokens = words_in_order(value)
    return tokens[1:] if tokens and tokens[0] in {'a', 'an', 'the'} else tokens


def _bundle_match(expected, found, item):
    if not _distinctive(expected) or ':' in expected or _DERIVATIVE.search(found):
        return False
    # A byline is accepted only when it names this same catalog person. It is
    # not discarded as generic punctuation or used as a substitute for the
    # reciprocal author-role check performed by the caller below.
    byline = re.search(r'\s+by\s+(.+)$', found, re.I)
    if byline:
        names = [item.get('title', ''), *_strings(item.get('title_aliases'))]
        if not same_author(names, [byline[1]]):
            return False
        found = found[:byline.start()]
    # Preserve punctuation for a bounded "Books 1-4" range. A catalog work
    # that already specifies a volume never reaches this relaxed path.
    if ':' in found:
        primary, suffix = found.split(':', 1)
        book_range = _BOOK_RANGE.fullmatch(suffix.strip())
        return bool(same_title(expected, primary)[0] and book_range
                    and int(book_range[1]) < int(book_range[2]))
    left, right = _tokens_without_article(expected), _tokens_without_article(found)
    if right[:len(left)] != left or len(right) == len(left):
        return False
    return bool(_BUNDLE.fullmatch(' '.join(right[len(left):])))


def _relaxed_match(expected, record, item):
    found = record.get('title', '')
    if not isinstance(found, str) or _DERIVATIVE.search(expected) or _DERIVATIVE.search(found):
        return False
    subtitle = record.get('subtitle')
    # An independently supplied subtitle is evidence, not text to throw away.
    # A conflicting subtitle must never be hidden by the primary-title rule.
    if subtitle:
        return False
    if ':' in expected:
        primary, remainder = expected.split(':', 1)
        if (remainder.strip() and _distinctive(primary) and not _SCOPE.search(remainder)
                and ':' not in found and same_title(primary, found)[0]):
            return True
    # Only an explicitly declared series can justify removing its parenthesis.
    # A matching suffix in an unstructured title is insufficient.
    parenthesis = re.fullmatch(r'(.+?)\s+\(([^()]*)\)', found)
    if parenthesis and _distinctive(expected) and same_title(expected, parenthesis[1])[0]:
        if any(same_title(parenthesis[2], series)[0] for series in _strings(record.get('series'))):
            return True
    return _bundle_match(expected, found, item)


def matched_work_titles(item, remote_works, *, author_key=None):
    """Return canonical catalog titles corroborated by a remote bibliography.

    ``item.work_aliases`` and any existing work dictionaries are normalized by
    :func:`portrait_work_records`. Only Open Library dictionaries with the
    requested reciprocal author role allow relaxed bibliographic forms.
    """
    records = []
    for record in remote_works:
        if isinstance(record, str):
            records.append((record, None, False))
        elif isinstance(record, dict) and isinstance(record.get('title'), str):
            reciprocal = _reciprocal_author(record, author_key)
            if author_key is not None and not reciprocal:
                continue
            records.append((record['title'], record, reciprocal))
    matches = []
    for work in portrait_work_records(item):
        titles = [work['title'], *work.get('title_aliases', [])]
        for found, record, reciprocal in records:
            remote_titles = [found]
            if record and isinstance(record.get('subtitle'), str) and record['subtitle'].strip():
                remote_titles = [found + ': ' + record['subtitle'].strip()]
            if any(same_title(title, remote)[0] for title in titles for remote in remote_titles):
                matches.append(work['title'])
                break
            if reciprocal and any(_relaxed_match(title, record, item) for title in titles):
                matches.append(work['title'])
                break
    return list(dict.fromkeys(matches))
