"""Import OCLC's ranked Library 100 and two unranked TIME selections.

Run without ``--apply`` for a read-only catalogue reconciliation. The apply
path creates only missing shared catalogue identities, publishes through the
revision-aware external-list importer, and writes target-local provenance.
It never deletes shared data and never writes private reader records.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.settings")

import django

django.setup()

from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from backend.core.models import Person, Ranking, ResearchSource, Work
from research.import_community_published_rankings import TITLE_ALIASES, proposed_form, split_authors
from research.import_historical_published_rankings import make_index, norm, resolve_work, title_keys

CHECKED_ON = "2026-09-14"
RUN = ROOT / "research" / "_runs" / CHECKED_ON / "oclc-time-collections"


TIME_NOVELS = """1984\tGeorge Orwell\t1949
The Adventures of Augie March\tSaul Bellow\t1953
All the King's Men\tRobert Penn Warren\t1946
American Pastoral\tPhilip Roth\t1997
An American Tragedy\tTheodore Dreiser\t1925
Animal Farm\tGeorge Orwell\t1945
Appointment in Samarra\tJohn O'Hara\t1934
Are You There God? It's Me, Margaret\tJudy Blume\t1970
The Assistant\tBernard Malamud\t1957
At Swim-Two-Birds\tFlann O'Brien\t1939
Atonement\tIan McEwan\t2001
Beloved\tToni Morrison\t1987
The Berlin Stories\tChristopher Isherwood\t1935/1939
The Big Sleep\tRaymond Chandler\t1939
The Blind Assassin\tMargaret Atwood\t2000
Blood Meridian\tCormac McCarthy\t1985
Brideshead Revisited\tEvelyn Waugh\t1945
The Bridge of San Luis Rey\tThornton Wilder\t1927
Call It Sleep\tHenry Roth\t1934
Catch-22\tJoseph Heller\t1961
The Catcher in the Rye\tJ. D. Salinger\t1951
A Clockwork Orange\tAnthony Burgess\t1962
The Confessions of Nat Turner\tWilliam Styron\t1967
The Corrections\tJonathan Franzen\t2001
The Crying of Lot 49\tThomas Pynchon\t1966
A Dance to the Music of Time\tAnthony Powell\t1951-1975
The Day of the Locust\tNathanael West\t1939
Death Comes for the Archbishop\tWilla Cather\t1927
A Death in the Family\tJames Agee\t1957
The Death of the Heart\tElizabeth Bowen\t1938
Deliverance\tJames Dickey\t1970
Dog Soldiers\tRobert Stone\t1974
Falconer\tJohn Cheever\t1977
The French Lieutenant's Woman\tJohn Fowles\t1969
The Golden Notebook\tDoris Lessing\t1962
Go Tell It on the Mountain\tJames Baldwin\t1953
Gone with the Wind\tMargaret Mitchell\t1936
The Grapes of Wrath\tJohn Steinbeck\t1939
Gravity's Rainbow\tThomas Pynchon\t1973
The Great Gatsby\tF. Scott Fitzgerald\t1925
A Handful of Dust\tEvelyn Waugh\t1934
The Heart Is a Lonely Hunter\tCarson McCullers\t1940
The Heart of the Matter\tGraham Greene\t1948
Herzog\tSaul Bellow\t1964
Housekeeping\tMarilynne Robinson\t1980
A House for Mr. Biswas\tV. S. Naipaul\t1961
I, Claudius\tRobert Graves\t1934
Infinite Jest\tDavid Foster Wallace\t1996
Invisible Man\tRalph Ellison\t1952
Light in August\tWilliam Faulkner\t1932
The Lion, the Witch and the Wardrobe\tC. S. Lewis\t1950
Lolita\tVladimir Nabokov\t1955
Lord of the Flies\tWilliam Golding\t1954
The Lord of the Rings\tJ. R. R. Tolkien\t1954-1955
Loving\tHenry Green\t1945
Lucky Jim\tKingsley Amis\t1954
The Man Who Loved Children\tChristina Stead\t1940
Midnight's Children\tSalman Rushdie\t1981
Money\tMartin Amis\t1984
The Moviegoer\tWalker Percy\t1961
Mrs. Dalloway\tVirginia Woolf\t1925
Naked Lunch\tWilliam S. Burroughs\t1959
Native Son\tRichard Wright\t1940
Neuromancer\tWilliam Gibson\t1984
Never Let Me Go\tKazuo Ishiguro\t2005
On the Road\tJack Kerouac\t1957
One Flew Over the Cuckoo's Nest\tKen Kesey\t1962
The Painted Bird\tJerzy Kosinski\t1965
Pale Fire\tVladimir Nabokov\t1962
A Passage to India\tE. M. Forster\t1924
Play It as It Lays\tJoan Didion\t1970
Portnoy's Complaint\tPhilip Roth\t1969
Possession\tA. S. Byatt\t1990
The Power and the Glory\tGraham Greene\t1940
The Prime of Miss Jean Brodie\tMuriel Spark\t1961
Rabbit, Run\tJohn Updike\t1960
Ragtime\tE. L. Doctorow\t1975
The Recognitions\tWilliam Gaddis\t1955
Red Harvest\tDashiell Hammett\t1929
Revolutionary Road\tRichard Yates\t1961
The Sheltering Sky\tPaul Bowles\t1949
Slaughterhouse-Five\tKurt Vonnegut\t1969
Snow Crash\tNeal Stephenson\t1992
The Sot-Weed Factor\tJohn Barth\t1960
The Sound and the Fury\tWilliam Faulkner\t1929
The Sportswriter\tRichard Ford\t1986
The Spy Who Came in from the Cold\tJohn le Carré\t1963
The Sun Also Rises\tErnest Hemingway\t1926
Their Eyes Were Watching God\tZora Neale Hurston\t1937
Things Fall Apart\tChinua Achebe\t1958
To Kill a Mockingbird\tHarper Lee\t1960
To the Lighthouse\tVirginia Woolf\t1927
Tropic of Cancer\tHenry Miller\t1934
Ubik\tPhilip K. Dick\t1969
Under the Net\tIris Murdoch\t1954
Under the Volcano\tMalcolm Lowry\t1947
Watchmen\tAlan Moore and Dave Gibbons\t1986-1987
White Noise\tDon DeLillo\t1985
White Teeth\tZadie Smith\t2000
Wide Sargasso Sea\tJean Rhys\t1966"""


TIME_MYSTERY = """2666\tRoberto Bolaño
A Dark-Adapted Eye\tBarbara Vine
A Kiss Before Dying\tIra Levin
A Man Lay Dead\tNgaio Marsh
A Place of Execution\tVal McDermid
Beast in View\tMargaret Millar
Beat Not the Bones\tCharlotte Jay
Big Little Lies\tLiane Moriarty
Blacktop Wasteland\tS. A. Cosby
Blanche Passes Go\tBarbara Neely
Bluebird, Bluebird\tAttica Locke
Bury Your Dead\tLouise Penny
Case Histories\tKate Atkinson
Casino Royale\tIan Fleming
Crime and Punishment\tFyodor Dostoevsky
Dead Time\tEleanor Taylor Bland
Death of a Red Heroine\tQiu Xiaolong
Devil in a Blue Dress\tWalter Mosley
Djinn Patrol on the Purple Line\tDeepa Anappara
Double Indemnity\tJames M. Cain
Drive Your Plow Over the Bones of the Dead\tOlga Tokarczuk
Everything I Never Told You\tCeleste Ng
Faceless Killers\tHenning Mankell
Fade Away\tHarlan Coben
Faithful Place\tTana French
Fingersmith\tSarah Waters
Gaudy Night\tDorothy L. Sayers
Gone Girl\tGillian Flynn
Hollywood Homicide\tKellye Garrett
If He Hollers Let Him Go\tChester Himes
In a Lonely Place\tDorothy B. Hughes
Inner City Blues\tPaula L. Woods
Killing Floor\tLee Child
Lady Joker\tKaoru Takamura
Land of Shadows\tRachel Howzell Hall
Mean Spirit\tLinda Hogan
Mexican Gothic\tSilvia Moreno-Garcia
Miracle Creek\tAngie Kim
Morituri\tYasmina Khadra
My Sister, the Serial Killer\tOyinkan Braithwaite
Mystic River\tDennis Lehane
Ordinary Grace\tWilliam Kent Krueger
Out\tNatsuo Kirino
Postmortem\tPatricia Cornwell
Queenpin\tMegan Abbott
Rebecca\tDaphne du Maurier
Six Four\tHideo Yokoyama
Smilla's Sense of Snow\tPeter Høeg
Snakeskin Shamisen\tNaomi Hirahara
Survivor's Guilt\tRobyn Gigl
A Coffin for Dimitrios\tEric Ambler
The Conjure-Man Dies\tRudolph Fisher
The Crime at Black Dudley\tMargery Allingham
The Daughter of Time\tJosephine Tey
The Decagon House Murders\tYukito Ayatsuji
The Devotion of Suspect X\tKeigo Higashino
The Emperor of Ocean Park\tStephen L. Carter
The Girl with the Dragon Tattoo\tStieg Larsson
The Honjin Murders\tSeishi Yokomizo
The Hound of the Baskervilles\tArthur Conan Doyle
The Hunt for Red October\tTom Clancy
The Ice Princess\tCamilla Läckberg
The Last Good Kiss\tJames Crumley
The Leavenworth Case\tAnna Katharine Green
The Lincoln Lawyer\tMichael Connelly
The Long Goodbye\tRaymond Chandler
The Maltese Falcon\tDashiell Hammett
The Murder of Roger Ackroyd\tAgatha Christie
The Name of the Rose\tUmberto Eco
The Need\tHelen Phillips
The Other Americans\tLaila Lalami
The Patient in Room 18\tMignon G. Eberhart
The Plotters\tUn-su Kim
The Quiet American\tGraham Greene
The Redbreast\tJo Nesbø
The Round House\tLouise Erdrich
The Secret History\tDonna Tartt
The Shadow of the Wind\tCarlos Ruiz Zafón
The Shining\tStephen King
The Silence of the Lambs\tThomas Harris
The Sound of Things Falling\tJuan Gabriel Vásquez
The Spy Who Came in from the Cold\tJohn le Carré
The Surgeon\tTess Gerritsen
The Sympathizer\tViet Thanh Nguyen
The Talented Mr. Ripley\tPatricia Highsmith
The Three Coffins\tJohn Dickson Carr
The Turn of the Key\tRuth Ware
The Turn of the Screw\tHenry James
The Widows of Malabar Hill\tSujata Massey
The Woman in White\tWilkie Collins
The Yiddish Policemen's Union\tMichael Chabon
Those Bones Are Not My Child\tToni Cade Bambara
We Have Always Lived in the Castle\tShirley Jackson
What the Dead Know\tLaura Lippman
When Death Comes Stealing\tValerie Wilson Wesley
When No One Is Watching\tAlyssa Cole
Where Are the Children?\tMary Higgins Clark
Wife of the Gods\tKwei Quartey
Winter Counts\tDavid Heska Wanbli Weiden
Your House Will Pay\tSteph Cha"""


DEFINITIONS = {
    "oclc-library-100": {
        "title": "OCLC · The Library 100",
        "publisher": "OCLC / WorldCat",
        "presentation": "ranked",
        "url": "https://www.oclc.org/en/worldcat/library100.html",
        "publication_date": "2019-01-01",
        "source_edition": "2019 Library 100",
        "method": "All 100 novels in OCLC's published order, ranked by the number of WorldCat libraries holding them.",
        "limitation": "A global library-holdings measure of distribution and institutional availability, not a direct poll of literary merit.",
        "display_semantics": "source_rank",
    },
    "time-100-best-novels-2005": {
        "title": "TIME · 100 Best Novels (1923–2005)",
        "publisher": "TIME",
        "presentation": "unranked",
        "url": "https://time.com/archive/6675063/times-100-best-novels/",
        "publication_date": "2005-10-16",
        "source_edition": "2005 English-language selection",
        "method": "The complete 100-title selection by TIME critics Lev Grossman and Richard Lacayo, displayed alphabetically rather than as merit positions.",
        "limitation": "Restricted to English-language novels published from 1923 through 2005. Alphabetical display order is not a ranking.",
        "display_semantics": "alphabetical_source_display",
    },
    "time-100-mystery-thriller-books-2023": {
        "title": "TIME · 100 Best Mystery and Thriller Books (2023)",
        "publisher": "TIME",
        "presentation": "unranked",
        "url": "https://time.com/collections/best-mystery-thriller-books/",
        "publication_date": "2023-10-03",
        "source_edition": "2023 selection",
        "method": "The complete 100-title selection chosen by a seven-author panel and TIME editors; the publication presents the books chronologically, not as merit positions.",
        "limitation": "TIME's editorial selection is limited to novels matching its broad mystery/thriller definition. Its chronology must not be represented as a quality rank.",
        "display_semantics": "alphabetical_membership_display; source_publication_is_chronological",
    },
}

# OCLC displays cataloguing subtitles for these familiar works. Reuse the
# established shared identities rather than creating subtitle-only duplicates.
TITLE_ALIASES.update({
    norm("The Hobbit, or, There and Back Again"): norm("The Hobbit"),
    norm("Frankenstein, or, the Modern Prometheus"): norm("Frankenstein"),
    norm("Madame Bovary: Patterns of Provincial Life"): norm("Madame Bovary"),
})


def parse_tsv(value: str, include_year: bool = False) -> list[dict]:
    rows = []
    for display_order, line in enumerate(value.splitlines(), 1):
        values = line.split("\t")
        row = {"display_order": display_order, "title": values[0], "author": values[1]}
        if include_year:
            row["year"] = values[2]
        rows.append(row)
    return rows


def source_lists() -> dict[str, list[dict]]:
    oclc_path = ROOT / "research" / "_runs" / "2026-09-13" / "compilation" / "S04-oclc.json"
    oclc = [
        {"display_order": row["position"], "source_rank": row["position"], "title": row["title"], "author": row["author"]}
        for row in json.loads(oclc_path.read_text())["entries"]
    ]
    rows = {
        "oclc-library-100": oclc,
        "time-100-best-novels-2005": parse_tsv(TIME_NOVELS, include_year=True),
        "time-100-mystery-thriller-books-2023": parse_tsv(TIME_MYSTERY),
    }
    for slug, values in rows.items():
        if len(values) != 100 or len({(norm(row["title"]), norm(row["author"])) for row in values}) != 100:
            raise RuntimeError(f"{slug} must contain exactly 100 unique source rows")
    return rows


def ensure_definitions() -> None:
    for slug, definition in DEFINITIONS.items():
        ranking, created = Ranking.objects.get_or_create(slug=slug, defaults={
            "title": definition["title"], "origin": "external", "presentation": definition["presentation"],
            "domain": "collections", "item_type": "work", "is_public": True,
            "source_url": definition["url"], "publisher": definition["publisher"], "status": "pending_import",
            "description": definition["limitation"], "target_size": 100,
            "scope": {"external_metadata": definition},
        })
        if not created and (ranking.origin != "external" or ranking.owner_id or ranking.presentation != definition["presentation"]):
            raise RuntimeError(f"Existing target definition conflicts with {slug}")
        ranking.full_clean()


def prepare(apply: bool) -> dict:
    lists = source_lists()
    by_title = make_index()
    people_by_name = defaultdict(list)
    for person in Person.objects.filter(is_archived=False):
        people_by_name[norm(person.name)].append(person)
    mapped, created_works, created_people, ambiguous = {}, [], [], []
    with transaction.atomic():
        if apply:
            ensure_definitions()
        for slug, rows in lists.items():
            mapped[slug] = []
            used = set()
            for row in rows:
                work, resolution = resolve_work(row, by_title)
                if work is None and resolution.startswith("ambiguous"):
                    ambiguous.append({"target": slug, **row, "reason": resolution})
                    continue
                if work is None and not apply:
                    mapped[slug].append({**row, "work_id": None, "resolution": "would_create"})
                    continue
                if work is None:
                    people = []
                    for name in split_authors(row["author"]):
                        candidates = people_by_name[norm(name)]
                        person = min(candidates, key=lambda item: item.pk) if candidates else None
                        if person is None:
                            person = Person(name=name, source_url=DEFINITIONS[slug]["url"])
                            person.full_clean()
                            person.save()
                            people_by_name[norm(name)].append(person)
                            created_people.append({"id": person.pk, "name": name})
                        people.append(person)
                    work = Work(
                        title=row["title"], form=proposed_form(row["title"]), field="literature",
                        description=f"Source-defined entry in {DEFINITIONS[slug]['title']}; edition and cover metadata pending.",
                    )
                    year = row.get("year", "")
                    if year.isdigit():
                        work.original_year = int(year)
                    work.full_clean()
                    work.save()
                    work.authors.set(people)
                    for key in title_keys(work.title):
                        by_title[key].append(work)
                    created_works.append({"id": work.pk, "title": work.title, "authors": [person.name for person in people], "source": slug})
                    resolution = "created"
                if work.pk in used:
                    ambiguous.append({"target": slug, **row, "reason": f"duplicate_work:{work.pk}"})
                    continue
                used.add(work.pk)
                mapped[slug].append({**row, "work_id": work.pk, "resolution": resolution})
        if ambiguous:
            raise RuntimeError(f"Resolve {len(ambiguous)} rows before import: {json.dumps(ambiguous[:25], ensure_ascii=False)}")
        if not apply:
            transaction.set_rollback(True)
    return {
        "mapped": mapped, "created_works": created_works, "created_people": created_people,
        "would_create": sum(row["resolution"] == "would_create" for values in mapped.values() for row in values),
    }


def source_records(slug: str) -> list[dict]:
    definition = DEFINITIONS[slug]
    records = [{
        "source_id": "PUBLISHED-LIST-01", "underlying_source_id": "published-list:" + definition["url"],
        "title": definition["title"] + " — official publication", "canonical_url": definition["url"],
        "source_family": "institutional_data" if slug == "oclc-library-100" else "media_editorial_selection",
        "publisher": definition["publisher"], "target_ids": [slug],
        "relevance_by_target": {slug: definition["method"]}, "evidence_notes": definition["method"],
        "accessed_at": CHECKED_ON, "eligible": True, "limitations": definition["limitation"],
    }]
    if slug == "time-100-best-novels-2005":
        records.extend([
            {
                "source_id": "PUBLISHED-LIST-02", "underlying_source_id": "transcription:https://private.michaelhan.net/snapshots/book-list-1.pdf",
                "title": "Archived PDF of TIME's complete alphabetical list", "canonical_url": "https://private.michaelhan.net/snapshots/book-list-1.pdf",
                "source_family": "list_transcription", "publisher": "Archived TIME page", "target_ids": [slug],
                "relevance_by_target": {slug: "Complete title-level snapshot of TIME's displayed list, used to verify membership and alphabetical presentation."},
                "evidence_notes": "Complete title-level snapshot of TIME's displayed list, used to verify membership and alphabetical presentation.",
                "accessed_at": CHECKED_ON, "eligible": True, "limitations": "Mirror of the same TIME list; not an independent editorial source.",
            },
            {
                "source_id": "PUBLISHED-LIST-03", "underlying_source_id": "transcription:https://de.wikipedia.org/wiki/Time-Auswahl_der_besten_100_englischsprachigen_Romane_von_1923_bis_2005",
                "title": "German Wikipedia — TIME selection title/author table", "canonical_url": "https://de.wikipedia.org/wiki/Time-Auswahl_der_besten_100_englischsprachigen_Romane_von_1923_bis_2005",
                "source_family": "list_transcription", "publisher": "Wikipedia contributors", "target_ids": [slug],
                "relevance_by_target": {slug: "Complete author/year table cross-checked against the archived official title list."},
                "evidence_notes": "Complete author/year table cross-checked against the archived official title list.",
                "accessed_at": CHECKED_ON, "eligible": True, "limitations": "Secondary transcription; title spellings and dates were corrected against TIME's own displayed list.",
            },
        ])
    elif slug == "time-100-mystery-thriller-books-2023":
        records.extend([
            {
                "source_id": "PUBLISHED-LIST-02", "underlying_source_id": "published-list:https://time.com/6316204/how-we-chose-100-best-mystery-thriller-books/",
                "title": "TIME — How We Chose the 100 Best Mystery and Thriller Books", "canonical_url": "https://time.com/6316204/how-we-chose-100-best-mystery-thriller-books/",
                "source_family": "methodology", "publisher": "TIME", "target_ids": [slug],
                "relevance_by_target": {slug: "Official panel, nomination, rating, eligibility and editorial methodology."},
                "evidence_notes": "Official panel, nomination, rating, eligibility and editorial methodology.",
                "accessed_at": CHECKED_ON, "eligible": True, "limitations": "Methodology page supports selection process, not additional independent votes.",
            },
            {
                "source_id": "PUBLISHED-LIST-03", "underlying_source_id": "transcription:https://topshelfbooks.org/list.php?id=83",
                "title": "TopShelf Books — complete TIME mystery/thriller membership transcription", "canonical_url": "https://topshelfbooks.org/list.php?id=83",
                "source_family": "list_transcription", "publisher": "TopShelf Books", "target_ids": [slug],
                "relevance_by_target": {slug: "Complete two-page membership transcription, reconciled against TIME's visible chronological entries."},
                "evidence_notes": "Complete two-page membership transcription, reconciled against TIME's visible chronological entries.",
                "accessed_at": CHECKED_ON, "eligible": True,
                "limitations": "Secondary mirror of the same list, not independent evidence. Two incorrect work-title substitutions were repaired from TIME's official page; alternate titles were normalized.",
            },
            {
                "source_id": "PUBLISHED-LIST-04", "underlying_source_id": "index:https://www.ebsco.com/articles/literature-and-writing/d9736e06-40bc-591f-a975-d5bee72a6979/the-100-best-mystery-amp-thriller-books-of-all-time/",
                "title": "EBSCO — indexed TIME magazine print feature", "canonical_url": "https://www.ebsco.com/articles/literature-and-writing/d9736e06-40bc-591f-a975-d5bee72a6979/the-100-best-mystery-amp-thriller-books-of-all-time/",
                "source_family": "periodical_index", "publisher": "EBSCO / TIME Magazine", "target_ids": [slug],
                "relevance_by_target": {slug: "Print-feature index used to confirm chronological presentation and the early sequence."},
                "evidence_notes": "Print-feature index used to confirm chronological presentation and the early sequence.",
                "accessed_at": CHECKED_ON, "eligible": True, "limitations": "Public abstract exposes only the beginning of the print table; it is corroboration, not a complete row source.",
            },
        ])
    return records


def save_artifacts(result: dict) -> dict:
    RUN.mkdir(parents=True, exist_ok=True)
    audit = {
        "checked_on": CHECKED_ON, "targets": {},
        "catalog": {"created_works": result["created_works"], "created_people": result["created_people"]},
        "source_snapshots": {},
    }
    for path in [
        Path("/private/tmp/time-novels-official-snapshot.pdf"), Path("/private/tmp/time-novels-de.html"),
        Path("/private/tmp/time-mystery-mirror.html"), Path("/private/tmp/time-mystery-mirror-page2.html"),
        Path("/private/tmp/time-mystery-ebsco.html"),
    ]:
        if path.is_file():
            audit["source_snapshots"][path.name] = {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    for slug, rows in result["mapped"].items():
        definition = DEFINITIONS[slug]
        directory = ROOT / "research" / slug
        directory.mkdir(parents=True, exist_ok=True)
        reviewed = [{key: row[key] for key in ("display_order", "source_rank", "title", "author", "year") if key in row} for row in rows]
        reviewed_path = directory / "source-list-reviewed-20260914.json"
        reviewed_path.write_text(json.dumps(reviewed, ensure_ascii=False, indent=2) + "\n")
        records = source_records(slug)
        ledger = {"target_id": slug, "status": "named_external_list_import", "saved_at": CHECKED_ON, "sources": records}
        (directory / "sources.json").write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n")

        ranking = Ranking.objects.get(slug=slug)
        entries = []
        for row in rows:
            note = f"{row['author']} — source-defined selection"
            if row.get("year"):
                note += f"; first published {row['year']}"
            entry = {"work_id": row["work_id"], "note": note}
            if definition["presentation"] == "ranked":
                entry["source_rank"] = row["source_rank"]
            entries.append(entry)
        payload = {
            "target": slug, "presentation": definition["presentation"], "expected_revision": ranking.revision,
            "source_checked_on": CHECKED_ON, "status": "imported", "unresolved_count": 0,
            "method_note": definition["method"],
            "allow_reviewed_replacement": bool(ranking.entries.filter(is_archived=False).exists()), "entries": entries,
        }
        input_path = directory / "reviewed-contents-20260914.json"
        input_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")

        current = list(ranking.entries.filter(is_archived=False).order_by("position").values_list("work_id", "source_rank"))
        desired = [(entry["work_id"], entry.get("source_rank")) for entry in entries]
        imported = current != desired or ranking.status != "imported"
        if imported:
            call_command("import_external_list", str(input_path))
            ranking.refresh_from_db()

        now = timezone.now()
        ranking.title = definition["title"]
        ranking.publisher = definition["publisher"]
        ranking.source_url = definition["url"]
        ranking.description = definition["limitation"]
        ranking.target_size = 100
        ranking.last_researched_at = now
        ranking.last_sources_checked_at = now
        ranking.scope = {
            **ranking.scope, "external_metadata": definition, "entry_semantics": "publisher-defined individual works",
            "source_entry_count": 100, "source_method": definition["method"],
            "source_limitations": definition["limitation"], "display_semantics": definition["display_semantics"],
        }
        ranking.full_clean()
        ranking.save()

        for record in records:
            source, created = ResearchSource.objects.get_or_create(
                ranking=ranking, underlying_source_id=record["underlying_source_id"],
                defaults={
                    "source_id": record["source_id"], "title": record["title"], "url": record["canonical_url"],
                    "family": record["source_family"], "publisher": record["publisher"],
                    "evidence": record["evidence_notes"], "limitations": record["limitations"],
                    "consulted_on": date.fromisoformat(CHECKED_ON), "eligible": True, "metadata": record,
                },
            )
            if created:
                source.full_clean()

        section = "Published ranking" if definition["presentation"] == "ranked" else "Reading collection"
        (directory / "RESEARCH.md").write_text(
            f"# {definition['title']}\n\nStatus: fully imported named {section.lower()} (100 entries), checked {CHECKED_ON}.\n\n"
            f"Official source: {definition['url']}\n\nMethod: {definition['method']}\n\n"
            f"Presentation: {section}. "
            + ("Exact source ranks are retained. " if definition["presentation"] == "ranked" else "`source_rank` is null for every entry; display order does not imply merit. ")
            + "No criteria, weights, personal scores, editions or covers were invented.\n\n"
            f"Limitations: {definition['limitation']}\n\nArtifacts: `{reviewed_path.name}`, `{input_path.name}`, its import receipt when changed, and `sources.json`.\n"
        )
        audit["targets"][slug] = {
            "ranking_id": ranking.pk, "entries": len(entries), "revision": ranking.revision,
            "presentation": ranking.presentation, "null_source_ranks": ranking.entries.filter(is_archived=False, source_rank__isnull=True).count(),
            "source_count": ranking.sources.filter(is_archived=False).count(), "imported_this_run": imported,
            "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        }
    (RUN / "publication-audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
    return audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        result = prepare(False)
        print(json.dumps({
            "mode": "read_only", "counts": {slug: len(rows) for slug, rows in result["mapped"].items()},
            "would_create": result["would_create"],
            "resolution_counts": {
                slug: {kind: sum(row["resolution"] == kind for row in rows) for kind in sorted({row["resolution"] for row in rows})}
                for slug, rows in result["mapped"].items()
            },
        }, ensure_ascii=False, indent=2))
        return
    with transaction.atomic():
        result = prepare(True)
        audit = save_artifacts(result)
    print(json.dumps({
        "mode": "applied", "counts": {slug: len(rows) for slug, rows in result["mapped"].items()},
        "created_works": len(result["created_works"]), "created_people": len(result["created_people"]),
        "targets": audit["targets"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
