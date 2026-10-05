"""Conservative, Unicode-aware identities shared by public media adapters.

Aliases are supplied only from the catalog's reviewed ID-keyed registry. Neither
transliterations nor shortened titles are guessed here.
"""
from __future__ import annotations

import re
import unicodedata

MATCHER_VERSION = 'unicode-library-headings-v1'


def _characters(value: str) -> str:
    # Remove Latin accents for legacy catalog spellings, but retain meaningful
    # vowel/other marks in scripts such as Devanagari instead of losing them.
    result = []
    latin_base = False
    for char in unicodedata.normalize('NFKD', str(value or '')).casefold():
        if unicodedata.category(char).startswith('M'):
            if not latin_base:
                result.append(char)
        else:
            latin_base = 'LATIN' in unicodedata.name(char, '')
            result.append(char)
    return unicodedata.normalize('NFC', ''.join(result))


def words_in_order(value: str) -> list[str]:
    cleaned = ''.join(char if char.isalnum() or unicodedata.category(char).startswith('M') else ' '
                      for char in _characters(value))
    return cleaned.split()


def norm(value: str) -> str:
    return ''.join(words_in_order(value))


def words(value: str) -> set[str]:
    return set(words_in_order(value))


def same_title(expected: str, found: str) -> tuple[bool, int]:
    left, right = norm(expected), norm(found)
    if left and right and left == right:
        return True, 100
    left_words, right_words = words_in_order(expected), words_in_order(found)
    if left_words and left_words[0] in {'a', 'an', 'the'}:
        left_words = left_words[1:]
    if right_words and right_words[0] in {'a', 'an', 'the'}:
        right_words = right_words[1:]
    return (True, 98) if left_words and left_words == right_words else (False, 0)


# Remove only an entire recognizable life-date component, never arbitrary
# trailing descriptors or a numeric part embedded in an identity.
_LIFE_DATES = re.compile(r'(?:[bc]\.\s*)?\d{3,4}\??\s*[-–—]\s*(?:\d{3,4}\??)?|(?:b|d)\.\s*\d{3,4}\??', re.I)


def _name_parts(value: str) -> list[str]:
    value = re.sub(r'\.\s*(?:Auteur du texte|Author|Writer)\.?$', '', str(value or ''), flags=re.I).strip()
    parenthetical = re.search(r'\s*\(([^()]*)\)\.?$', value)
    if parenthetical and _LIFE_DATES.fullmatch(parenthetical.group(1)):
        value = value[:parenthetical.start()]
    components = [part.strip() for part in value.split(',')]
    if len(components) > 1 and _LIFE_DATES.fullmatch(components[-1]):
        components.pop()
    # Standard library headings: family name, given names[, life dates].
    # More components may carry roles/suffixes and are deliberately not guessed.
    if len(components) == 2 and all(components):
        value = components[1] + ' ' + components[0]
    else:
        value = ' '.join(components)
    return words_in_order(value)


def same_author(expected: list[str], found: list[str]) -> bool:
    for left in expected:
        left_parts = _name_parts(left)
        if not left_parts:
            continue
        for right in found:
            right_parts = _name_parts(right)
            if left_parts == right_parts:
                return True
            # Complete surname plus equally many compatible given names. A
            # surname alone or a missing middle name never supplies identity.
            if len(left_parts) >= 2 and len(left_parts) == len(right_parts):
                if left_parts[-1] == right_parts[-1] and all(
                    a == b or ((len(a) == 1 or len(b) == 1) and a[0] == b[0])
                    for a, b in zip(left_parts[:-1], right_parts[:-1])
                ):
                    return True
    return False


def match_item_title(item: dict, found: str) -> tuple[bool, int]:
    return max((same_title(title, found) for title in [item['title'], *item.get('title_aliases', [])]),
               key=lambda result: result[1])


def match_item_author(item: dict, found: list[str]) -> bool:
    expected = [name for name in [*item.get('authors', []), *item.get('author_aliases', [])]
                if name.casefold() not in {'anonymous', 'collaborators'}]
    return same_author(expected, found)
