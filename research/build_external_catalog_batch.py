"""Build a factual catalog batch from author-attributed external-list rows."""
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / "research" / "_runs" / "2026-09-13" / "external-lists"
rows = json.loads((RUN / "guardian-readers-2026-unresolved.json").read_text())
rows += json.loads((RUN / "mcevoy-favourites-unresolved.json").read_text())
rows += json.loads((RUN / "guardian-critics-2026-unresolved.json").read_text())

def key(value):
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]+", "", value)[:100]

works = []
for row in rows:
    author = row["author_as_printed"]
    authors = ["Alexandre Dumas", "Auguste Maquet"] if author == "Alexandre Dumas and Auguste Maquet" else [author]
    source_url = "https://benjaminmcevoy.com/reading-list/" if "position" in row else ("https://www.theguardian.com/books/ng-interactive/2026/may/12/the-100-best-novels-of-all-time" if row.get("source_rank_label") is None else "https://www.theguardian.com/books/ng-interactive/2026/jun/06/readers-top-100-novels-of-all-time")
    works.append({
        "key": key(row["title"] + "-" + author), "title": row["title"], "authors": authors,
        "form": "collection" if row["title"].startswith(("The Complete Works", "The Short Stories")) else "book",
        "field": "literature", "original_year": None, "original_language": "", "countries": [],
        "description": "", "work_source_url": source_url,
        "evidence_ids": ["EXTERNAL-LIST-SOURCE"], "edition": None,
        "english_availability_note": "Named in English with its author on the preserved public source list; edition, pagination and cover remain pending."
    })
payload = {"schema_version": 1, "consulted_on": "2026-09-13", "allow_pending_editions": True, "works": works}
path = ROOT / "research" / "catalog" / "external-lists-2026-09-13.json"
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
print(path, len(works))
