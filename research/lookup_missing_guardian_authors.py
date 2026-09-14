"""Resolve absent Guardian title authors through Open Library search metadata."""
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / 'research/_runs/2026-09-13/external-lists'
missing = json.loads((RUN / 'guardian-critics-2026-unresolved.json').read_text())
results = []
for row in missing:
    query = urllib.parse.urlencode({'title': row['title'], 'limit': 5, 'fields': 'title,author_name,first_publish_year,key'})
    request = urllib.request.Request('https://openlibrary.org/search.json?' + query,
                                     headers={'User-Agent': 'MarginaliaResearch/1.0 (local catalog reconciliation)'})
    with urllib.request.urlopen(request, timeout=20) as response:
        docs = json.load(response).get('docs', [])
    exact = [doc for doc in docs if doc.get('title', '').casefold() == row['title'].casefold() and doc.get('author_name')]
    choice = exact[0] if exact else next((doc for doc in docs if doc.get('author_name')), None)
    results.append({**row, 'lookup': choice, 'status': 'candidate_match_needs_title_review' if choice else 'not_found'})
    time.sleep(0.1)
(RUN / 'guardian-critics-author-lookups.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n')
print(len(results), 'lookups saved', sum(bool(row['lookup']) for row in results), 'with candidates')
