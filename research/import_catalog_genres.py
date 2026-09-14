"""Import conservative shared genres from evidence already saved in this project.

This importer is additive: it never removes taxonomy assignments or changes
catalog, ranking, edition, or private-library records.  The owner-supplied manga
catalog has a structured ``Genres/themes`` clause for every work; only phrases
that map clearly to Marginalia's controlled genre vocabulary are used here.
Every proposed/created relationship is written to an audit ledger.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SOURCES = (
    ROOT / "research" / "manga-all-time" / "owner-paste-catalog.json",
    ROOT / "research" / "comics-graphic-novels-all-time" / "owner-paste-catalog.json",
)
RUN = ROOT / "research" / "_runs" / "2026-09-14" / "catalog-genres"


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Action", ("action",)),
    ("Adventure", ("adventure", "exploration", "mountaineering", "travel")),
    ("Arts & Artists", ("art", "artistic", "film", "manga creation")),
    ("Autobiographical", ("autobiography", "autobiographical", "memoir")),
    ("Boys' Love", ("bl",)),
    ("Comedy", ("comedy", "farce", "gag manga", "gag comedy", "slapstick")),
    ("Coming of Age", ("coming of age", "adolescence", "young adulthood")),
    ("Crime", ("crime", "espionage", "police")),
    ("Cyberpunk", ("cyberpunk",)),
    ("Dark Fantasy", ("dark fantasy", "dark fairy tale")),
    ("Drama", ("drama", "melodrama", "tragedy")),
    ("Dystopian", ("dystopia",)),
    ("Fantasy", ("fantasy", "dark fairy tale")),
    ("Family", ("family", "relationships", "relationships")),
    ("Food", ("food", "wine")),
    ("Gekiga", ("gekiga",)),
    ("Girls' Love", ("yuri",)),
    ("Gothic", ("gothic",)),
    ("Historical Fiction", ("historical", "alternate history", "renaissance", "samurai", "ninja")),
    ("Horror", ("horror",)),
    ("Isekai", ("isekai",)),
    ("Literary Fiction", ("literary fiction",)),
    ("Magical Girl", ("magical girl",)),
    ("Martial Arts", ("martial arts",)),
    ("Mecha", ("mecha",)),
    ("Music", ("music", "jazz", "piano", "rock")),
    ("Mystery", ("mystery",)),
    ("Myth & Folklore", ("myth", "folklore", "yokai")),
    ("Performing Arts", ("acting", "ballet", "theatre")),
    ("Post-Apocalyptic", ("post apocalyptic", "apocalypse", "apocalyptic")),
    ("Psychological", ("psychological", "mental health")),
    ("Romance", ("romance", "romantic", "queer love")),
    ("Satire", ("satire",)),
    ("School Life", ("school", "college")),
    ("Science Fiction", ("science fiction", "science-fiction", "space", "robots")),
    ("Slice of Life", ("slice of life", "everyday life", "domestic life", "urban life")),
    ("Sports", ("sports", "baseball", "basketball", "boxing", "diving", "figure skating", "football", "karuta", "mountaineering", "table tennis", "volleyball", "wrestling")),
    ("Superhero", ("superhero", "superheroes")),
    ("Supernatural", ("supernatural", "demons", "reincarnation", "vampire", "vampires", "yokai")),
    ("Surrealism", ("surrealism", "dream narrative")),
    ("Thriller", ("thriller", "suspense")),
    ("War", ("war", "military")),
    ("Western", ("western",)),
    ("Workplace", ("work", "workplace")),
)


def genre_clause(description: str) -> list[str]:
    match = re.search(r"Genres/themes:\s*(.*?)(?:\. Manga/Asian-comics|\. Editorial rationale:)", description)
    return [part.strip() for part in match.group(1).split(";") if part.strip()] if match else []


def mapped_genres(phrases: list[str]) -> list[str]:
    values = [norm(phrase) for phrase in phrases]
    genres = []
    for genre, needles in RULES:
        if any(any(re.search(rf"(?:^| )%s(?: |$)" % re.escape(norm(needle)), value) for needle in needles) for value in values):
            genres.append(genre)
    return genres


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Create the audited additive assignments.")
    args = parser.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.settings")
    import django
    django.setup()
    from django.db import transaction
    from backend.core.models import Tag, Work

    records = [(source, record) for source in SOURCES for record in json.loads(source.read_text())["works"]]
    ledger: dict = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "dry-run",
        "sources": [str(source.relative_to(ROOT)) for source in SOURCES],
        "policy": "Strict title plus credited-author match; additive controlled genres from the source's explicit Genres/themes clause only.",
        "assignments": [],
        "unmatched": [],
        "ambiguous": [],
        "unresolved_genre_phrases": [],
    }
    unresolved = Counter()
    plans = []
    for source, record in records:
        query = Work.objects.filter(is_archived=False, title__iexact=record["title"])
        if source.parent.name == "manga-all-time":
            query = query.filter(field="manga")
        candidates = list(query.prefetch_related("authors", "tags"))
        expected = {norm(name) for name in record.get("authors", [])}
        candidates = [work for work in candidates if expected & {norm(person.name) for person in work.authors.all()}]
        if len(candidates) > 1:
            source_described = [work for work in candidates if not work.description.startswith("Source-defined entry in")]
            if len(source_described) == 1:
                candidates = source_described
        if not candidates:
            ledger["unmatched"].append({"key": record["key"], "title": record["title"], "authors": record.get("authors", [])})
            continue
        if len(candidates) != 1:
            ledger["ambiguous"].append({"key": record["key"], "title": record["title"], "work_ids": [work.pk for work in candidates]})
            continue
        phrases = genre_clause(record.get("description", ""))
        genres = mapped_genres(phrases)
        for phrase in phrases:
            if not mapped_genres([phrase]):
                unresolved[phrase] += 1
        work = candidates[0]
        existing = {tag.name for tag in work.tags.all() if tag.kind == "genre" and not tag.is_archived}
        additions = [genre for genre in genres if genre not in existing]
        plans.append((work.pk, additions))
        ledger["assignments"].append({
            "source": str(source.relative_to(ROOT)), "source_key": record["key"], "work_id": work.pk, "title": work.title,
            "source_phrases": phrases, "mapped_genres": genres, "existing_genres": sorted(existing),
            "genres_to_add": additions,
        })

    ledger["unresolved_genre_phrases"] = [{"phrase": phrase, "uses": uses} for phrase, uses in sorted(unresolved.items(), key=lambda row: (-row[1], row[0].casefold()))]
    if args.apply and (ledger["unmatched"] or ledger["ambiguous"]):
        raise SystemExit("Refusing partial apply: resolve unmatched or ambiguous owner-supplied manga records first.")
    if args.apply:
        with transaction.atomic():
            terms = {}
            for name in Tag.GENRES:
                term, _ = Tag.objects.get_or_create(name=name, defaults={"kind": "genre"})
                if term.kind != "genre":
                    raise RuntimeError(f"Taxonomy name collision: {name!r} is {term.kind!r}.")
                terms[name] = term
            for work_id, additions in plans:
                if additions:
                    Work.objects.get(pk=work_id).tags.add(*(terms[name] for name in additions))

    ledger["summary"] = {
        "source_records": len(records),
        "matched_works": len(plans),
        "works_with_at_least_one_mapped_genre": sum(bool(row[1]) or bool(item["existing_genres"]) for row, item in zip(plans, ledger["assignments"])),
        "relationships_to_add": sum(len(additions) for _, additions in plans),
        "unmatched": len(ledger["unmatched"]),
        "ambiguous": len(ledger["ambiguous"]),
    }
    RUN.mkdir(parents=True, exist_ok=True)
    output = RUN / ("import-audit-v2.json" if args.apply else "dry-run-audit-v2.json")
    output.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(ledger["summary"], indent=2))
    print(f"Audit: {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
