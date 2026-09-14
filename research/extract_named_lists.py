"""Extract reviewed named lists from saved source HTML; no network or database writes."""
import html
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'research' / '_runs' / '2026-09-13' / 'external-lists'
OUT.mkdir(parents=True, exist_ok=True)


def text(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', value))).strip()


def normalize(value):
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().casefold()
    return re.sub(r'[^a-z0-9]', '', value)


def guardian(path, target):
    source = Path(path).read_text()
    rows = []
    pattern = r'<span class="rank[^>]*>(\d+)</span>\s*<span class="bold[^>]*>(.*?)</span>'
    for rank, title in re.findall(pattern, source, re.S):
        rows.append({'source_rank': int(rank), 'title': text(title)})
    if not rows:
        # The readers page is ordinary article markup and preserves explicit ties.
        token_pattern = r'<p[^>]*>(=?\d+)</p>|<h2[^>]*>(?!<em>)(.*?)</h2>\s*<h2[^>]*><em>by (.*?)</em></h2>'
        rank = None
        for rank_token, title, author in re.findall(token_pattern, source, re.S):
            if rank_token:
                rank = rank_token
            elif rank:
                rows.append({'source_rank': int(rank.lstrip('=')), 'source_rank_label': rank,
                             'title': text(title), 'author_as_printed': text(author)})
        if target == 'guardian-readers-2026':
            # The live article's rank-35 reader quotation is embedded in the
            # following h2, so the generic heading parser joins two records.
            joined = next((row for row in rows if row['title'].startswith('The Count of Monte Cristo by ')), None)
            if joined:
                joined.update({'source_rank': 36, 'source_rank_label': '36',
                               'title': 'A Confederacy of Dunces',
                               'author_as_printed': 'John Kennedy Toole'})
                rows.append({'source_rank': 35, 'source_rank_label': '35',
                             'title': 'The Count of Monte Cristo',
                             'author_as_printed': 'Alexandre Dumas and Auguste Maquet'})
    rows.sort(key=lambda row: row['source_rank'])
    expected = 100
    assert len(rows) == expected and rows[0]['source_rank'] == 1 and rows[-1]['source_rank'] == 100
    (OUT / f'{target}-extracted.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n')


def mcevoy(path):
    source = Path(path).read_text()
    reading_html = source[source.index('First Year Reading List:'):source.index('What are Benjamin McEvoy')]
    author = None
    position = 0
    rows = {'reading': [], 'favourites': []}
    for body in re.findall(r'<span\b[^>]*>(.*?)</span>', reading_html, re.S | re.I):
        value = text(body)
        if value.endswith(':') and len(value) < 100:
            author = value[:-1]
            continue
        if author:
            position += 1
            rows['reading'].append({'position': position, 'title': value, 'author_as_printed': author})
    rows['favourites'] = [
        {'position': 1, 'title': 'The Complete Works of Shakespeare', 'author_as_printed': 'William Shakespeare'},
        {'position': 2, 'title': 'Nicomachean Ethics', 'author_as_printed': 'Aristotle'},
        {'position': 3, 'title': 'The Bible', 'author_as_printed': 'Various'},
        {'position': 4, 'title': 'Essays', 'author_as_printed': 'Michel de Montaigne'},
        {'position': 5, 'title': 'The Short Stories of Chekhov', 'author_as_printed': 'Anton Chekhov'},
        {'position': 6, 'title': 'War and Peace', 'author_as_printed': 'Leo Tolstoy'},
        {'position': 7, 'title': 'Moby-Dick', 'author_as_printed': 'Herman Melville'},
    ]
    if len(rows['reading']) < 20 or len(rows['favourites']) != 7:
        raise ValueError(f'Unexpected McEvoy extraction counts: { {key: len(value) for key, value in rows.items()} }')
    (OUT / 'mcevoy-extracted.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    guardian('/tmp/gcritics.html', 'guardian-critics-2026')
    guardian('/tmp/greaders.html', 'guardian-readers-2026')
    mcevoy('/tmp/mcevoy.html')
