"""Resolve extracted named lists against the existing catalog."""
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.config.settings')
import django
django.setup()
from backend.core.models import Ranking, Work

RUN = ROOT / 'research' / '_runs' / '2026-09-13' / 'external-lists'


def norm(value):
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().casefold()
    return re.sub(r'[^a-z0-9]', '', value)


ALIASES = {
    norm('The Iliad'): norm('Iliad'),
    norm('The Odyssey'): norm('Odyssey'),
    norm('The Outsider'): norm('The Stranger'),
    norm('Moby Dick'): norm('Moby-Dick'),
    norm('Ethics'): norm('Nicomachean Ethics'),
    norm('Meditations'): norm('Meditations on First Philosophy'),
    norm('Mrs. Dalloway'): norm('Mrs Dalloway'),
}
AUTHOR_ALIASES = {'Thomas Hobbe': 'Thomas Hobbes', 'Milton': 'John Milton'}
CRITIC_AUTHORS = {
    'The Portrait of a Lady': 'Henry James', 'The Brothers Karamazov': 'Fyodor Dostoevsky',
    'Their Eyes Were Watching God': 'Zora Neale Hurston', 'Song of Solomon': 'Toni Morrison',
    'Housekeeping': 'Marilynne Robinson', 'The Leopard': 'Giuseppe Tomasi di Lampedusa',
    'The Metamorphosis': 'Franz Kafka', 'My Brilliant Friend': 'Elena Ferrante',
    'The Transit of Venus': 'Shirley Hazzard', 'The Waves': 'Virginia Woolf',
    'Disgrace': 'J. M. Coetzee', 'The Rings of Saturn': 'W. G. Sebald',
    'Half of a Yellow Sun': 'Chimamanda Ngozi Adichie', 'White Teeth': 'Zadie Smith',
    'The Color Purple': 'Alice Walker', 'Crime and Punishment': 'Fyodor Dostoevsky',
    'Kindred': 'Octavia E. Butler', 'Our Mutual Friend': 'Charles Dickens',
    'Austerlitz': 'W. G. Sebald', 'Nervous Conditions': 'Tsitsi Dangarembga',
    'The Bluest Eye': 'Toni Morrison', 'The End of the Affair': 'Graham Greene',
    'The Talented Mr Ripley': 'Patricia Highsmith', 'The Vegetarian': 'Han Kang',
    'The Line of Beauty': 'Alan Hollinghurst', 'The Left Hand of Darkness': 'Ursula K. Le Guin',
    "Jacob's Room": 'Virginia Woolf', 'Life and Fate': 'Vasily Grossman',
    'Invisible Cities': 'Italo Calvino', 'The Known World': 'Edward P. Jones',
}


def resolve(rows):
    by_title = {}
    for work in Work.objects.filter(is_archived=False).prefetch_related('authors'):
        by_title.setdefault(norm(work.title), []).append(work)
    found, unresolved = [], []
    for row in rows:
        key = ALIASES.get(norm(row['title']), norm(row['title']))
        matches = by_title.get(key, [])
        printed_author = row.get('author_as_printed', '')
        author = norm(AUTHOR_ALIASES.get(printed_author, printed_author))
        if len(matches) > 1 and author:
            narrowed = [w for w in matches if any(norm(a.name) == author for a in w.authors.all())]
            if not narrowed:
                narrowed = [w for w in matches if any(norm(a.name) in author or author in norm(a.name) for a in w.authors.all())]
            if len(narrowed) == 1:
                matches = narrowed
        if len(matches) == 1:
            found.append({**row, 'work_id': matches[0].pk})
        else:
            unresolved.append({**row, 'reason': 'catalog identity absent or ambiguous'})
    return found, unresolved


def save(target, presentation, rows, note):
    ranking = Ranking.objects.get(slug=target)
    if target == 'guardian-critics-2026':
        rows = [{**row, 'author_as_printed': CRITIC_AUTHORS.get(row['title'], row.get('author_as_printed', ''))} for row in rows]
    found, unresolved = resolve(rows)
    entries = []
    seen = set()
    for row in found:
        if row['work_id'] in seen:
            unresolved.append({**row, 'reason': 'duplicate work occurrence; first source occurrence retained'})
            continue
        seen.add(row['work_id'])
        entry = {'work_id': row['work_id'], 'note': row.get('author_as_printed', '')}
        if presentation == 'ranked':
            entry['source_rank'] = row['source_rank']
        entries.append(entry)
    payload = {'target': target, 'presentation': presentation, 'expected_revision': ranking.revision,
               'source_checked_on': '2026-09-13', 'status': 'partially_imported' if unresolved else 'imported',
               'method_note': note, 'unresolved_count': len(unresolved), 'entries': entries}
    if target == 'mcevoy-reading-list':
        payload['allow_reviewed_replacement'] = True
    path = ROOT / 'research' / target / 'source-list-import.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    (RUN / f'{target}-unresolved.json').write_text(json.dumps(unresolved, ensure_ascii=False, indent=2) + '\n')
    print(target, len(found), 'resolved', len(unresolved), 'unresolved')


critics = json.loads((RUN / 'guardian-critics-2026-extracted.json').read_text())
readers = json.loads((RUN / 'guardian-readers-2026-extracted.json').read_text())
mcevoy = json.loads((RUN / 'mcevoy-extracted.json').read_text())
save('guardian-critics-2026', 'ranked', critics, 'Exact Guardian 2026 source ranks; title identities matched to catalog. Missing identities remain in the unresolved register.')
save('guardian-readers-2026', 'ranked', readers, 'Guardian reader ranks preserve published ties. The live corrected page yielded 99 displayed work records; no missing hundredth identity was invented.')
save('mcevoy-reading-list', 'reading_sequence', mcevoy['reading'], 'Sequence follows the five-year page order. Compound selections and absent identities remain unresolved rather than flattened.')
save('mcevoy-favourites', 'unranked', mcevoy['favourites'], 'Unranked desert-island favourites section; page order is display order, not merit rank.')
