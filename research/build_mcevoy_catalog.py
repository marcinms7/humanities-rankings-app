"""Create missing work identities from McEvoy's explicitly attributed reading list."""
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
from backend.core.models import Person, Work


def norm(value):
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().casefold()
    return re.sub(r'[^a-z0-9]', '', value)


people = list(Person.objects.filter(is_archived=False))
aliases = {'Hemingway': 'Ernest Hemingway', 'Faulkner': 'William Faulkner', 'Shakespeare': 'William Shakespeare',
           'Tolstoy': 'Leo Tolstoy', 'Dostoevsky': 'Fyodor Dostoevsky', 'Nietzsche': 'Friedrich Nietzsche',
           'Freud': 'Sigmund Freud', 'Aquinas': 'Thomas Aquinas'}
dramatists = {'Aeschylus', 'Euripides', 'Sophocles', 'Aristophanes', 'Shakespeare', 'Molière', 'Ibsen'}
source = json.loads((ROOT / 'research/_runs/2026-09-13/external-lists/mcevoy-extracted.json').read_text())['reading']
existing = {(norm(w.title), tuple(sorted(norm(a.name) for a in w.authors.all()))) for w in Work.objects.prefetch_related('authors')}
rows = []
seen = set()
for row in source:
    printed = row['author_as_printed']
    author = aliases.get(printed)
    if not author:
        exact = [p.name for p in people if norm(p.name) == norm(printed)]
        surname = [p.name for p in people if norm(p.name).endswith(norm(printed))]
        author = exact[0] if len(exact) == 1 else surname[0] if len(surname) == 1 else printed
    title = {'The Iliad': 'Iliad', 'The Odyssey': 'Odyssey', 'Ethics': 'Nicomachean Ethics',
             'Meditations': 'Meditations on First Philosophy'}.get(row['title'], row['title'])
    identity = (norm(title), (norm(author),))
    if identity in existing or identity in seen:
        continue
    seen.add(identity)
    form = 'play' if printed in dramatists else 'book'
    field = 'philosophy' if printed in {'Plato', 'Aristotle', 'Epictetus', 'Marcus Aurelius', 'Cicero', 'Aquinas',
                                        'Machiavelli', 'Descartes', 'Hobbes', 'Locke', 'Hume', 'Kant', 'Rousseau',
                                        'Adam Smith', 'Marx', 'Nietzsche', 'Freud'} else 'literature'
    rows.append({'key': norm(title) + '-' + norm(author), 'title': title, 'authors': [author], 'form': form,
                 'field': field, 'original_year': None, 'original_language': '', 'countries': [], 'description': '',
                 'work_source_url': 'https://benjaminmcevoy.com/reading-list/', 'evidence_ids': ['S01'],
                 'edition': None, 'english_availability_note': 'Named in English with author on Benjamin McEvoy’s public reading-list page; edition, pagination and media pending.'})
path = ROOT / 'research/catalog/mcevoy-reading-list-01.json'
path.write_text(json.dumps({'schema_version': 1, 'consulted_on': '2026-09-13', 'allow_pending_editions': True,
                            'works': rows}, ensure_ascii=False, indent=2) + '\n')
print(len(rows), 'missing work identities prepared')
