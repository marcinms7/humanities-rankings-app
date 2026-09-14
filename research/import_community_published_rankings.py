"""Prepare and import six reviewed Reddit and 4chan published rankings.

The spreadsheets are source snapshots downloaded from the result posts. The
three image/text-only lists are transcribed below so the reviewed input remains
reproducible even when an image host disappears. Run without --apply for a
read-only reconciliation report; --apply creates only missing public catalog
records, then delegates list publication to import_external_list.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.settings")

import django

django.setup()

from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from backend.core.models import Person, Ranking, ResearchSource, Work


CHECKED_ON = "2026-09-13"
RUN = ROOT / "research" / "_runs" / CHECKED_ON / "community-published-rankings"
XLSX_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


CLASSICLITERATURE = """1\tMoby-Dick\tHerman Melville
2\tThe Brothers Karamazov\tFyodor Dostoevsky
3\tEast of Eden\tJohn Steinbeck
4\tCrime and Punishment\tFyodor Dostoevsky
5\tThe Count of Monte Cristo\tAlexandre Dumas
6\tFrankenstein\tMary Shelley
7\tAnna Karenina\tLeo Tolstoy
8\t1984\tGeorge Orwell
9\tPride and Prejudice\tJane Austen
10\tOne Hundred Years of Solitude\tGabriel García Márquez
11\tThe Master and Margarita\tMikhail Bulgakov
12\tThe Lord of the Rings\tJ. R. R. Tolkien
13\tDon Quixote\tMiguel de Cervantes
14\tWar and Peace\tLeo Tolstoy
15\tJane Eyre\tCharlotte Brontë
16\tBlood Meridian\tCormac McCarthy
17\tWuthering Heights\tEmily Brontë
18\tUlysses\tJames Joyce
19\tThe Great Gatsby\tF. Scott Fitzgerald
20\tLes Misérables\tVictor Hugo
21\tThe Picture of Dorian Gray\tOscar Wilde
22\tStoner\tJohn Williams
23\tLolita\tVladimir Nabokov
24\tIn Search of Lost Time\tMarcel Proust
25\tCatch-22\tJoseph Heller
26\tThe Iliad\tHomer
27\tThe Grapes of Wrath\tJohn Steinbeck
28\tHamlet\tWilliam Shakespeare
29\tDracula\tBram Stoker
30\tThe Catcher in the Rye\tJ. D. Salinger
31\tThe Magic Mountain\tThomas Mann
32\tTo the Lighthouse\tVirginia Woolf
33\tThe Stranger\tAlbert Camus
34\tMrs Dalloway\tVirginia Woolf
35\tMadame Bovary\tGustave Flaubert
36\tThe Metamorphosis\tFranz Kafka
37\tMiddlemarch\tGeorge Eliot
38\tParadise Lost\tJohn Milton
39\tAbsalom, Absalom!\tWilliam Faulkner
40\tThe Idiot\tFyodor Dostoevsky
41\tThe Trial\tFranz Kafka
42\tInfinite Jest\tDavid Foster Wallace
43\tFahrenheit 451\tRay Bradbury
44\tGreat Expectations\tCharles Dickens
45\tNotes from Underground\tFyodor Dostoevsky
46\tAs I Lay Dying\tWilliam Faulkner
47\tA Tale of Two Cities\tCharles Dickens
48\tRebecca\tDaphne du Maurier
49\tBrave New World\tAldous Huxley
50\tFicciones\tJorge Luis Borges
51\tCandide\tVoltaire
52\tThe Sound and the Fury\tWilliam Faulkner
53\tThe Old Man and the Sea\tErnest Hemingway
54\tEmma\tJane Austen
55\tThe Plague\tAlbert Camus
56\tOf Mice and Men\tJohn Steinbeck
57\tSiddhartha\tHermann Hesse
58\tDune\tFrank Herbert
59\tAdventures of Huckleberry Finn\tMark Twain
60\tGiovanni's Room\tJames Baldwin
61\tDavid Copperfield\tCharles Dickens
62\tThe Remains of the Day\tKazuo Ishiguro
63\tPale Fire\tVladimir Nabokov
64\tThe Leopard\tGiuseppe Tomasi di Lampedusa
65\tTo Kill a Mockingbird\tHarper Lee
66\tLord of the Flies\tWilliam Golding
67\tA Christmas Carol\tCharles Dickens
68\tThe Bell Jar\tSylvia Plath
69\tAll Quiet on the Western Front\tErich Maria Remarque
70\tThe Name of the Rose\tUmberto Eco
71\tA Farewell to Arms\tErnest Hemingway
72\tMacbeth\tWilliam Shakespeare
73\tThe Canterbury Tales\tGeoffrey Chaucer
74\tHeart of Darkness\tJoseph Conrad
75\tDangerous Liaisons\tPierre Choderlos de Laclos
76\tThe Sun Also Rises\tErnest Hemingway
77\tSeptology\tJon Fosse
78\tMetamorphoses\tOvid
79\tThe Three Musketeers\tAlexandre Dumas
80\tPersuasion\tJane Austen
81\tDead Souls\tNikolai Gogol
82\tThe Divine Comedy\tDante Alighieri
83\tThe Road\tCormac McCarthy
84\tThe Phantom of the Opera\tGaston Leroux
85\t2666\tRoberto Bolaño
86\tA Game of Thrones\tGeorge R. R. Martin
87\tThe Secret History\tDonna Tartt
88\tWatership Down\tRichard Adams
89\tKing Lear\tWilliam Shakespeare
90\tDubliners\tJames Joyce
91\tSong of Solomon\tToni Morrison
92\tThe Aeneid\tVirgil
93\tThe Red and the Black\tStendhal
94\tDemons\tFyodor Dostoevsky
95\tMemoirs of Hadrian\tMarguerite Yourcenar
96\tThe Hunchback of Notre-Dame\tVictor Hugo
97\tAnimal Farm\tGeorge Orwell
98\tNever Let Me Go\tKazuo Ishiguro
99\tCat's Cradle\tKurt Vonnegut
100\tThe Odyssey\tHomer"""


LIT_2025 = """1\tThe Holy Bible\tVarious authors
2\tThe Brothers Karamazov\tFyodor Dostoevsky
3\tMoby-Dick\tHerman Melville
4\tThe Iliad\tHomer
5\tThe Odyssey\tHomer
6\tCrime and Punishment\tFyodor Dostoevsky
7\tBlood Meridian\tCormac McCarthy
8\tThe Metamorphosis\tFranz Kafka
9\tThe Trial\tFranz Kafka
10\tLolita\tVladimir Nabokov
11\tDon Quixote\tMiguel de Cervantes
12\tThe Lord of the Rings\tJ. R. R. Tolkien
13\tDialogues\tPlato
14\tUlysses\tJames Joyce
15\tNotes from Underground\tFyodor Dostoevsky
16\t1984\tGeorge Orwell
17\tAnna Karenina\tLeo Tolstoy
18\tFaust\tJohann Wolfgang von Goethe
19\tThe Divine Comedy\tDante Alighieri
20\tThe First Folio\tWilliam Shakespeare
21\tWar and Peace\tLeo Tolstoy
22\tIn Search of Lost Time\tMarcel Proust
23\tStoner\tJohn Williams
24\tFicciones\tJorge Luis Borges
25\tGravity's Rainbow\tThomas Pynchon
26\tHeart of Darkness\tJoseph Conrad
27\tInfinite Jest\tDavid Foster Wallace
28\tParadise Lost\tJohn Milton
29\tDubliners\tJames Joyce
30\tConfessions\tAugustine of Hippo
31\tThe Idiot\tFyodor Dostoevsky
32\tThe Stranger\tAlbert Camus
33\tThe Hobbit\tJ. R. R. Tolkien
34\tThe Old Man and the Sea\tErnest Hemingway
35\t2666\tRoberto Bolaño
36\tPale Fire\tVladimir Nabokov
37\tSiddhartha\tHermann Hesse
38\tThe Epic of Gilgamesh\tAnonymous
39\tBrave New World\tAldous Huxley
40\tThe Count of Monte Cristo\tAlexandre Dumas
41\tThe Castle\tFranz Kafka
42\tTragedies\tAeschylus
43\tJourney to the End of the Night\tLouis-Ferdinand Céline
44\tSlaughterhouse-Five\tKurt Vonnegut
45\tBeowulf\tAnonymous
46\tThe Death of Ivan Ilyich\tLeo Tolstoy
47\tThe Catcher in the Rye\tJ. D. Salinger
48\tIndustrial Society and Its Future\tTheodore Kaczynski
49\tTragedies\tSophocles
50\tDemons\tFyodor Dostoevsky
51\tThe Sailor Who Fell from Grace with the Sea\tYukio Mishima
52\tThe Master and Margarita\tMikhail Bulgakov
53\tA Portrait of the Artist as a Young Man\tJames Joyce
54\tThe Sound and the Fury\tWilliam Faulkner
55\tBeyond Good and Evil\tFriedrich Nietzsche
56\tWuthering Heights\tEmily Brontë
57\tMetamorphoses\tOvid
58\tThus Spoke Zarathustra\tFriedrich Nietzsche
59\tFear and Trembling\tSøren Kierkegaard
60\tDo Androids Dream of Electric Sheep?\tPhilip K. Dick
61\tStorm of Steel\tErnst Jünger
62\tThe World as Will and Representation\tArthur Schopenhauer
63\tThe Picture of Dorian Gray\tOscar Wilde
64\tThe Book of Disquiet\tFernando Pessoa
65\tNicomachean Ethics\tAristotle
66\tThe Sorrows of Young Werther\tJohann Wolfgang von Goethe
67\tNo Longer Human\tOsamu Dazai
68\tFinnegans Wake\tJames Joyce
69\tCatch-22\tJoseph Heller
70\tThe Aeneid\tVirgil
71\tConfessions of a Mask\tYukio Mishima
72\tPoems\tT. S. Eliot
73\tEast of Eden\tJohn Steinbeck
74\tThe Crying of Lot 49\tThomas Pynchon
75\tTo the Lighthouse\tVirginia Woolf
76\tA Christmas Carol\tCharles Dickens
77\tThe Prince\tNiccolò Machiavelli
78\tFrankenstein\tMary Shelley
79\tThe Magic Mountain\tThomas Mann
80\tA Confederacy of Dunces\tJohn Kennedy Toole
81\tThe Canterbury Tales\tGeoffrey Chaucer
82\tThe Name of the Rose\tUmberto Eco
83\tHunger\tKnut Hamsun
84\tPride and Prejudice\tJane Austen
85\tPoems\tW. B. Yeats
86\tAnimal Farm\tGeorge Orwell
87\tThe City of God\tAugustine of Hippo
88\tThe Ring of the Nibelung\tRichard Wagner
89\tAlice's Adventures in Wonderland\tLewis Carroll
90\tDracula\tBram Stoker
91\tThe Trilogy\tSamuel Beckett
92\tWaiting for Godot\tSamuel Beckett
93\tDune\tFrank Herbert
94\tMason & Dixon\tThomas Pynchon
95\tCthulhu Mythos\tH. P. Lovecraft
96\tThe Myth of Sisyphus\tAlbert Camus
97\tOne Hundred Years of Solitude\tGabriel García Márquez
98\tOn the Genealogy of Morals / Ecce Homo\tFriedrich Nietzsche
99\tThe Sun Also Rises\tErnest Hemingway
100\tA Clockwork Orange\tAnthony Burgess"""


LIT_DECADE = """1\tMoby-Dick\tHerman Melville
2\tThe Brothers Karamazov\tFyodor Dostoevsky
3\tLolita\tVladimir Nabokov
4\tCrime and Punishment\tFyodor Dostoevsky
5\tUlysses\tJames Joyce
6\tInfinite Jest\tDavid Foster Wallace
7\tDon Quixote\tMiguel de Cervantes
8\tBlood Meridian\tCormac McCarthy
9\tGravity's Rainbow\tThomas Pynchon
10\tThe Holy Bible\tVarious authors
11\tStoner\tJohn Williams
12\tThe Stranger\tAlbert Camus
13\tThe Divine Comedy\tDante Alighieri
14\tAnna Karenina\tLeo Tolstoy
15\tThe Iliad\tHomer
16\tWar and Peace\tLeo Tolstoy
17\tThe Odyssey\tHomer
18\tThe Trial\tFranz Kafka
19\tIn Search of Lost Time\tMarcel Proust
20\tHamlet\tWilliam Shakespeare
21\tOne Hundred Years of Solitude\tGabriel García Márquez
22\t1984\tGeorge Orwell
23\tNotes from Underground\tFyodor Dostoevsky
24\t2666\tRoberto Bolaño
25\tFaust\tJohann Wolfgang von Goethe
26\tThe Book of the New Sun\tGene Wolfe
27\tDubliners\tJames Joyce
28\tCatch-22\tJoseph Heller
29\tJourney to the End of the Night\tLouis-Ferdinand Céline
30\tThe Catcher in the Rye\tJ. D. Salinger
31\tThe Book of Disquiet\tFernando Pessoa
32\tThe Sound and the Fury\tWilliam Faulkner
33\tThe Master and Margarita\tMikhail Bulgakov
34\tThe Lord of the Rings\tJ. R. R. Tolkien
35\tThe Metamorphosis\tFranz Kafka
36\tA Portrait of the Artist as a Young Man\tJames Joyce
37\tThus Spoke Zarathustra\tFriedrich Nietzsche
38\tThe Idiot\tFyodor Dostoevsky
39\tParadise Lost\tJohn Milton
40\tEast of Eden\tJohn Steinbeck
41\tMason & Dixon\tThomas Pynchon
42\tPale Fire\tVladimir Nabokov
43\tThe Count of Monte Cristo\tAlexandre Dumas
44\tThe Picture of Dorian Gray\tOscar Wilde
45\tA Confederacy of Dunces\tJohn Kennedy Toole
46\tSiddhartha\tHermann Hesse
47\tHunger\tKnut Hamsun
48\tThe Magic Mountain\tThomas Mann
49\tHeart of Darkness\tJoseph Conrad
50\tNo Longer Human\tOsamu Dazai
51\tBrave New World\tAldous Huxley
52\tDune\tFrank Herbert
53\tLes Misérables\tVictor Hugo
54\tSteppenwolf\tHermann Hesse
55\tAmerican Psycho\tBret Easton Ellis
56\tTo the Lighthouse\tVirginia Woolf
57\tThe Republic\tPlato
58\tThe Recognitions\tWilliam Gaddis
59\tV.\tThomas Pynchon
60\tSlaughterhouse-Five\tKurt Vonnegut
61\tThe Sailor Who Fell from Grace with the Sea\tYukio Mishima
62\tThe Great Gatsby\tF. Scott Fitzgerald
63\tWuthering Heights\tEmily Brontë
64\tDemons\tFyodor Dostoevsky
65\tMeditations\tMarcus Aurelius
66\tAbsalom, Absalom!\tWilliam Faulkner
67\tThe Man Without Qualities\tRobert Musil
68\tConfessions\tAugustine of Hippo
69\tThe Old Man and the Sea\tErnest Hemingway
70\tThe Savage Detectives\tRoberto Bolaño
71\tThe Hobbit\tJ. R. R. Tolkien
72\tFinnegans Wake\tJames Joyce
73\tThe Crying of Lot 49\tThomas Pynchon
74\tMadame Bovary\tGustave Flaubert
75\tThe Sun Also Rises\tErnest Hemingway
76\tThe Waves\tVirginia Woolf
77\tInvisible Cities\tItalo Calvino
78\tTristram Shandy\tLaurence Sterne
79\tIf on a Winter's Night a Traveler\tItalo Calvino
80\tThe Grapes of Wrath\tJohn Steinbeck
81\tA Hero of Our Time\tMikhail Lermontov
82\tAs I Lay Dying\tWilliam Faulkner
83\tDead Souls\tNikolai Gogol
84\tNaked Lunch\tWilliam S. Burroughs
85\tFrankenstein\tMary Shelley
86\tAlice's Adventures in Wonderland\tLewis Carroll
87\tThe Name of the Rose\tUmberto Eco
88\tDas Kapital\tKarl Marx
89\tWhite Noise\tDon DeLillo
90\tPedro Páramo\tJuan Rulfo
91\tKokoro\tNatsume Sōseki
92\tPhenomenology of Spirit\tG. W. F. Hegel
93\tStorm of Steel\tErnst Jünger
94\tThe Tunnel\tWilliam H. Gass
95\tJR\tWilliam Gaddis
96\tBhagavad Gita\tVarious authors
97\tIndustrial Society and Its Future\tTheodore Kaczynski
98\tCritique of Pure Reason\tImmanuel Kant
99\tAnimal Farm\tGeorge Orwell
100\tThe Elementary Particles\tMichel Houellebecq"""


DEFINITIONS = {
    "reddit-truelit-2023": {
        "title": "r/TrueLit · Top 100 Favorite Books (2023)",
        "url": "https://www.reddit.com/r/TrueLit/comments/197l37n/truelits_2023_top_100_favorite_books/",
        "spreadsheet": "https://docs.google.com/spreadsheets/d/1LixH6kEImDHHeC2s5AbCrX660DO8hd6wTWQQ_MOMGhk/edit",
        "publisher": "r/TrueLit community",
        "method": "The first 100 rows of the poll's Final List sheet, after its published tiebreak procedure and one-book-per-author rule.",
        "limitation": "Community self-selection and one-book-per-author materially shape the result; ranks are not an editorial assessment by Marginalia.",
    },
    "reddit-classicliterature-2025": {
        "title": "r/classicliterature · Top 100 Favourite Books (2025)",
        "url": "https://www.reddit.com/r/classicliterature/comments/1qdutwp/rclassicliteratures_top_100_favourite_books_2025/",
        "publisher": "r/classicliterature community",
        "method": "Manual double-pass transcription of the post's complete ranked result image (100 positions; 163 participants reported).",
        "limitation": "Image transcription and a self-selected subreddit poll; exact display order is retained without treating it as Marginalia's judgment.",
    },
    "reddit-fantasy-top-novels-2023": {
        "title": "r/Fantasy · Top Novels (2023)",
        "url": "https://www.reddit.com/r/Fantasy/comments/11mvwsa/rfantasy_top_novels_2023_results/",
        "spreadsheet": "https://docs.google.com/spreadsheets/d/1rgODLOgPAooPyTXRyhD1_ZkOtqx0HcWiYZnKpbjcv4w/edit",
        "publisher": "r/Fantasy community",
        "method": "All 266 rows in the official Final List sheet meeting the post's five-vote publication threshold; source ranks and ties retained.",
        "limitation": "The poll mixes series, universes and standalone novels. That source-defined unit is retained in notes and is not a book-only merit comparison.",
    },
    "reddit-printsf-top-books-2023": {
        "title": "r/printSF · Top Book Poll (2023)",
        "url": "https://www.reddit.com/r/printSF/comments/10ywsk7/our_very_own_top_book_poll_results/",
        "spreadsheet": "https://docs.google.com/spreadsheets/d/19DgrwPi7A1PVS2wEIGdl903DkKAoBLImx8p8IDMPsYo/edit",
        "publisher": "r/printSF community",
        "method": "All 115 rows from the official tally-vote sheet with three or more votes, matching the complete table published in the result post.",
        "limitation": "The source mixes books and series; its tally order breaks equal-vote rows sequentially rather than assigning tied source ranks.",
    },
    "fourchan-lit-top-100-2025": {
        "title": "4chan /lit/ · Top 100 Books (2025)",
        "url": "https://warosu.org/lit/thread/25004995",
        "publisher": "4chan /lit/ community",
        "method": "Manual double-pass transcription of all 100 numbered positions in the archived 2025 result image.",
        "limitation": "Anonymous-board self-selection; the source includes collections and one composite Nietzsche entry, retained without splitting.",
    },
    "fourchan-lit-decade-aggregate-2014-2024": {
        "title": "4chan /lit/ · Decade Aggregate (2014–2024)",
        "url": "https://www.reddit.com/r/books/comments/1dy8gy8/for_10_years_now_4chan_has_ranked_the_100_best/",
        "publisher": "SharedHoney / 4chan /lit/ annual polls",
        "method": "All 100 numbered positions in the published text transcription of the ten-poll aggregate.",
        "limitation": "The author says the graphic contains 102 books because of ties at positions 15 and 70, but the published text transcription exposes 100 numbered records. The two non-transcribed graphic entries are not guessed.",
    },
}


def norm(value: str) -> str:
    value = value.translate(str.maketrans({"ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "đ": "d", "Đ": "D"}))
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]+", "", value)


TITLE_ALIASES = {
    norm("Brothers Karamazov"): norm("The Brothers Karamazov"),
    norm("Book of Disquiet"): norm("The Book of Disquiet"),
    norm("Holy Bible"): norm("The Holy Bible"),
    norm("Bible"): norm("The Holy Bible"),
    norm("Republic"): norm("The Republic"),
    norm("Alice in Wonderland"): norm("Alice's Adventures in Wonderland"),
    norm("The Life and Opinions of Tristram Shandy"): norm("Tristram Shandy"),
    norm("Unabomber Manifesto"): norm("Industrial Society and Its Future"),
    norm("Thus Spake Zarathustra"): norm("Thus Spoke Zarathustra"),
    norm("Master and Margharita"): norm("The Master and Margarita"),
    norm("Master and Margerita"): norm("The Master and Margarita"),
    norm("The Passion According to G.H."): norm("The Passion According to G.H."),
}

# Reviewed duplicate-catalog choices. These select the older canonical record
# with a verified edition where available; no duplicate is deleted or merged.
WORK_OVERRIDES = {
    (norm("The Divine Comedy"), norm("Alighieri")): 340,
    (norm("The Divine Comedy"), norm("Dante Alighieri")): 340,
    (norm("Adventures of Huckleberry Finn"), norm("Mark Twain")): 263,
    (norm("The Canterbury Tales"), norm("Geoffrey Chaucer")): 344,
    (norm("The City of God"), norm("Augustine of Hippo")): 666,
    (norm("The Republic"), norm("Plato")): 9,
    (norm("Bhagavad Gita"), norm("Various authors")): 1513,
}


def canonical_title(value: str) -> str:
    value = value.strip()
    return value[:-2] if value in {"1984.0", "2666.0"} else value


def parse_tsv(value: str) -> list[dict]:
    rows = []
    for line in value.splitlines():
        rank, title, author = line.split("\t")
        rows.append({"source_rank": int(rank), "title": title, "author": author})
    return rows


def xlsx_rows(path: Path, sheet_number: int) -> list[dict[str, str]]:
    with ZipFile(path) as archive:
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            strings = ["".join(t.text or "" for t in item.findall(".//m:t", XLSX_NS)) for item in root.findall("m:si", XLSX_NS)]
        sheet = ET.fromstring(archive.read(f"xl/worksheets/sheet{sheet_number}.xml"))
        result = []
        for row in sheet.findall(".//m:sheetData/m:row", XLSX_NS):
            values = {}
            for cell in row.findall("m:c", XLSX_NS):
                column = "".join(char for char in cell.attrib.get("r", "") if char.isalpha())
                raw = cell.find("m:v", XLSX_NS)
                if raw is None:
                    value = ""
                else:
                    value = raw.text or ""
                    if cell.attrib.get("t") == "s":
                        value = strings[int(value)]
                values[column] = value
            result.append(values)
        return result


def source_lists() -> dict[str, list[dict]]:
    true_rows = xlsx_rows(Path("/private/tmp/truelit-2023.xlsx"), 8)[:100]
    truelit = [
        {"source_rank": position, "title": canonical_title(row["A"]), "author": row["B"], "votes": int(float(row["C"]))}
        for position, row in enumerate(true_rows, 1)
    ]
    fantasy = []
    for row in xlsx_rows(Path("/private/tmp/rfantasy-2023.xlsx"), 1)[1:]:
        votes = int(float(row.get("C") or 0))
        if votes >= 5:
            fantasy.append({"source_rank": int(float(row["A"])), "title": canonical_title(row["B"]), "author": row["D"].strip(), "votes": votes})
    printsf = []
    for row in xlsx_rows(Path("/private/tmp/printsf-2023.xlsx"), 1):
        votes = int(float(row.get("D") or 0))
        if votes >= 3:
            printsf.append({"source_rank": int(float(row["A"])), "title": canonical_title(row["C"]), "author": row["B"].strip(), "votes": votes})
    lists = {
        "reddit-truelit-2023": truelit,
        "reddit-classicliterature-2025": parse_tsv(CLASSICLITERATURE),
        "reddit-fantasy-top-novels-2023": fantasy,
        "reddit-printsf-top-books-2023": printsf,
        "fourchan-lit-top-100-2025": parse_tsv(LIT_2025),
        "fourchan-lit-decade-aggregate-2014-2024": parse_tsv(LIT_DECADE),
    }
    expected = {"reddit-truelit-2023": 100, "reddit-classicliterature-2025": 100, "reddit-fantasy-top-novels-2023": 266,
                "reddit-printsf-top-books-2023": 115, "fourchan-lit-top-100-2025": 100,
                "fourchan-lit-decade-aggregate-2014-2024": 100}
    actual = {key: len(rows) for key, rows in lists.items()}
    if actual != expected:
        raise RuntimeError(f"Source extraction count mismatch: {actual}")
    return lists


def split_authors(value: str) -> list[str]:
    value = value.strip()
    replacements = {
        "LeGuin": "Ursula K. Le Guin", "Nabakov": "Vladimir Nabokov", "Bolano": "Roberto Bolaño",
        "Marquez": "Gabriel García Márquez", "Shelly": "Mary Shelley", "Falubert": "Gustave Flaubert",
        "Celine": "Louis-Ferdinand Céline", "Soderberg": "Hjalmar Söderberg", "Selimovic": "Meša Selimović",
        "Cartarescu": "Mircea Cărtărescu", "Cortazar": "Julio Cortázar", "O'Conner": "Flannery O'Connor",
    }
    value = replacements.get(value, value)
    if value.casefold() in {"various authors", "anonymous"}:
        return ["Various authors" if value.casefold().startswith("various") else "Anonymous"]
    return [part.strip() for part in re.split(r"\s+(?:and|&)\s+", value) if part.strip()]


COLLECTION_WORDS = re.compile(
    r"\b(series|trilogy|saga|cycle|chronicles|cantos|universe|world|archive|sequence|quartet|quintet|mythos|tragedies|poems|folio)\b",
    re.I,
)


def proposed_form(title: str) -> str:
    return "collection" if COLLECTION_WORDS.search(title) or "/" in title else "book"


def title_keys(title: str) -> set[str]:
    key = norm(title)
    keys = {key, TITLE_ALIASES.get(key, key)}
    if key.startswith("the"):
        keys.add(key[3:])
    else:
        keys.add("the" + key)
    return keys


def resolve_work(row: dict, by_title: dict[str, list[Work]]) -> tuple[Work | None, str]:
    override_id = WORK_OVERRIDES.get((norm(row["title"]), norm(row["author"])))
    if override_id:
        return Work.objects.get(pk=override_id, is_archived=False), "reviewed_duplicate_choice"
    matches = {work.pk: work for key in title_keys(row["title"]) for work in by_title.get(key, [])}
    if matches:
        wanted = {norm(name) for name in split_authors(row["author"])}
        exact = []
        surname = []
        for work in matches.values():
            existing = {norm(person.name) for person in work.authors.all()}
            if existing == wanted:
                exact.append(work)
            elif wanted and any(any(a.endswith(w[-8:]) or w.endswith(a[-8:]) for a in existing) for w in wanted):
                surname.append(work)
        narrowed = exact or surname
        if len(narrowed) == 1:
            return narrowed[0], "title_author"
        if not narrowed:
            return None, "missing"
        return None, f"ambiguous:{','.join(str(pk) for pk in sorted(matches))}"
    return None, "missing"


def add_to_index(work: Work, by_title: dict[str, list[Work]]) -> None:
    by_title.setdefault(norm(work.title), []).append(work)


def prepare(apply: bool) -> dict:
    lists = source_lists()
    active = list(Work.objects.filter(is_archived=False).prefetch_related("authors"))
    by_title: dict[str, list[Work]] = {}
    for work in active:
        add_to_index(work, by_title)
    people_by_name: dict[str, list[Person]] = {}
    for person in Person.objects.filter(is_archived=False):
        people_by_name.setdefault(norm(person.name), []).append(person)
    created_works = []
    created_people = []
    ambiguous = []
    mapped: dict[str, list[dict]] = {}

    with transaction.atomic():
        for slug, rows in lists.items():
            mapped[slug] = []
            for row in rows:
                work, match = resolve_work(row, by_title)
                if work is None and match.startswith("ambiguous"):
                    ambiguous.append({"target": slug, **row, "reason": match})
                    continue
                if work is None:
                    if not apply:
                        mapped[slug].append({**row, "work_id": None, "resolution": "would_create"})
                        continue
                    people = []
                    for name in split_authors(row["author"]):
                        candidates = people_by_name.get(norm(name), [])
                        exact = [person for person in candidates if person.name.casefold() == name.casefold()]
                        person = min(exact or candidates, key=lambda item: item.pk) if candidates else None
                        if person is None:
                            person = Person(name=name, source_url=DEFINITIONS[slug]["url"])
                            person.full_clean()
                            person.save()
                            created_people.append({"id": person.pk, "name": name})
                            people_by_name.setdefault(norm(name), []).append(person)
                        people.append(person)
                    work = Work(
                        title=row["title"], form=proposed_form(row["title"]), field="literature",
                        description=f"Source-defined entry in {DEFINITIONS[slug]['title']}; edition and cover metadata pending.",
                    )
                    work.full_clean()
                    work.save()
                    work.authors.set(people)
                    created_works.append({"id": work.pk, "title": work.title, "authors": [p.name for p in people], "source": slug})
                    add_to_index(work, by_title)
                    match = "created"
                mapped[slug].append({**row, "work_id": work.pk, "resolution": match})
        if ambiguous:
            raise RuntimeError(f"Resolve {len(ambiguous)} ambiguous rows before import; see report output: {ambiguous[:10]}")
        if not apply:
            transaction.set_rollback(True)

    return {"lists": lists, "mapped": mapped, "created_works": created_works, "created_people": created_people,
            "would_create": sum(1 for rows in mapped.values() for row in rows if row["resolution"] == "would_create"),
            "ambiguous": ambiguous}


def source_records(slug: str) -> list[dict]:
    definition = DEFINITIONS[slug]
    records = [{
        "source_id": "COMMUNITY-LIST-01",
        "underlying_source_id": "community-list:" + definition["url"],
        "title": definition["title"] + " — result publication",
        "canonical_url": definition["url"],
        "source_family": "community_poll",
        "publisher": definition["publisher"],
        "target_ids": [slug],
        "relevance_by_target": {slug: definition["method"]},
        "evidence_notes": definition["method"],
        "accessed_at": CHECKED_ON,
        "eligible": True,
        "limitations": definition["limitation"],
    }]
    if definition.get("spreadsheet"):
        records.append({
            "source_id": "COMMUNITY-LIST-02",
            "underlying_source_id": "community-list:" + definition["spreadsheet"],
            "title": definition["title"] + " — official linked result spreadsheet",
            "canonical_url": definition["spreadsheet"],
            "source_family": "community_poll_data",
            "publisher": definition["publisher"],
            "target_ids": [slug],
            "relevance_by_target": {slug: "Official linked row-level tally used to preserve titles, authors, ordering, votes and published cutoff."},
            "evidence_notes": "Official linked row-level tally used to preserve titles, authors, ordering, votes and published cutoff.",
            "accessed_at": CHECKED_ON,
            "eligible": True,
            "limitations": "Spreadsheet is poll evidence, not an independent critical source.",
        })
    return records


def save_artifacts(result: dict) -> None:
    RUN.mkdir(parents=True, exist_ok=True)
    created_works = result["created_works"] or [
        {"id": work.pk, "title": work.title, "authors": list(work.authors.values_list("name", flat=True))}
        for work in Work.objects.filter(description__startswith="Source-defined entry in ").prefetch_related("authors").order_by("pk")
    ]
    source_urls = [definition["url"] for definition in DEFINITIONS.values()]
    created_people = result["created_people"] or [
        {"id": person.pk, "name": person.name}
        for person in Person.objects.filter(source_url__in=source_urls).order_by("pk")
    ]
    snapshots = {}
    for label, path in {
        "truelit_2023_xlsx": Path("/private/tmp/truelit-2023.xlsx"),
        "rfantasy_2023_xlsx": Path("/private/tmp/rfantasy-2023.xlsx"),
        "printsf_2023_xlsx": Path("/private/tmp/printsf-2023.xlsx"),
        "classicliterature_2025_image": Path("/private/tmp/classicliterature-2025.jpg"),
        "fourchan_lit_2025_image": Path("/private/tmp/lit-2025.png"),
    }.items():
        if path.exists():
            snapshots[label] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}
    audit = {"checked_on": CHECKED_ON, "targets": {}, "catalog": {
        "created_works": created_works, "created_people": created_people}, "source_snapshots": snapshots}
    for slug, rows in result["mapped"].items():
        definition = DEFINITIONS[slug]
        directory = ROOT / "research" / slug
        directory.mkdir(parents=True, exist_ok=True)
        reviewed = [{key: row[key] for key in ("source_rank", "title", "author", "votes") if key in row} for row in rows]
        (directory / "source-list-reviewed-20260913.json").write_text(json.dumps(reviewed, ensure_ascii=False, indent=2) + "\n")
        sources = {"target_id": slug, "status": "named_external_list_import", "saved_at": CHECKED_ON,
                   "sources": source_records(slug)}
        (directory / "sources.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2) + "\n")
        input_path = directory / "reviewed-contents-20260913.json"
        ranking = Ranking.objects.get(slug=slug)
        entries = []
        for row in rows:
            note = f"{row['author']} — source-defined list entry"
            if "votes" in row:
                note += f"; {row['votes']} votes"
            entries.append({"work_id": row["work_id"], "source_rank": row["source_rank"], "note": note})
        payload = {
            "target": slug, "presentation": "ranked", "expected_revision": ranking.revision,
            "source_checked_on": CHECKED_ON, "status": "imported", "unresolved_count": 0,
            "method_note": definition["method"], "allow_reviewed_replacement": bool(ranking.entries.filter(is_archived=False).exists()),
            "entries": entries,
        }
        payload_bytes = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        receipt_path = input_path.with_name(input_path.stem + "-import-receipt.json")
        if input_path.exists() and receipt_path.exists():
            receipt = json.loads(receipt_path.read_text())
            if hashlib.sha256(input_path.read_bytes()).hexdigest() != receipt["input_sha256"]:
                # An earlier idempotency check rewrote only the optimistic-lock
                # fields. Reconstruct and verify the immutable first-import bytes.
                restored = {**payload, "expected_revision": receipt["revision"] - 1, "allow_reviewed_replacement": False}
                restored_bytes = (json.dumps(restored, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
                if hashlib.sha256(restored_bytes).hexdigest() != receipt["input_sha256"]:
                    raise RuntimeError(f"Cannot restore immutable import input for {slug}")
                input_path.write_bytes(restored_bytes)
        elif not input_path.exists():
            input_path.write_bytes(payload_bytes)
        active = list(ranking.entries.filter(is_archived=False).order_by("position", "id").values_list("work_id", "source_rank"))
        desired = [(entry["work_id"], entry["source_rank"]) for entry in entries]
        if active != desired:
            call_command("import_external_list", str(input_path))
            ranking.refresh_from_db()
        now = timezone.now()
        ranking.target_size = len(entries)
        ranking.last_researched_at = now
        ranking.last_sources_checked_at = now
        ranking.scope = {**ranking.scope, "entry_semantics": "publisher/community-defined books, series, collections or composite works",
                         "source_entry_count": len(entries), "source_method": definition["method"],
                         "source_limitations": definition["limitation"]}
        ranking.full_clean()
        ranking.save()
        for record in source_records(slug):
            source, created = ResearchSource.objects.get_or_create(
                ranking=ranking, underlying_source_id=record["underlying_source_id"],
                defaults={"source_id": record["source_id"], "title": record["title"], "url": record["canonical_url"],
                          "family": record["source_family"], "publisher": record["publisher"],
                          "evidence": record["evidence_notes"], "limitations": record["limitations"],
                          "consulted_on": date.fromisoformat(CHECKED_ON), "eligible": True, "metadata": record},
            )
            if created:
                source.full_clean()
        research_md = f"""# {definition['title']}\n\nStatus: fully imported named published ranking ({len(entries)} entries), checked {CHECKED_ON}.\n\nSource: {definition['url']}\n\nMethod: {definition['method']}\n\nThe source ordering and any source ranks/ties are stored separately from Marginalia's researched rankings and personal assessments. No criteria, weights or personal scores were assigned. New catalog identities have pending edition and cover enrichment; this does not alter source membership.\n\nLimitations: {definition['limitation']}\n\nArtifacts: `source-list-reviewed-20260913.json`, `reviewed-contents-20260913.json`, its import receipt, and `sources.json`. Historical revisions and private data were preserved.\n"""
        (directory / "RESEARCH.md").write_text(research_md)
        audit["targets"][slug] = {"ranking_id": ranking.pk, "entries": len(entries), "revision": ranking.revision,
                                   "source_count": ranking.sources.filter(is_archived=False).count(),
                                   "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest()}
    (RUN / "publication-audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    result = prepare(args.apply)
    counts = {slug: len(rows) for slug, rows in result["mapped"].items()}
    if not args.apply:
        print(json.dumps({"mode": "read_only", "counts": counts, "would_create": result["would_create"],
                          "ambiguous": result["ambiguous"]}, ensure_ascii=False, indent=2))
        return
    with transaction.atomic():
        save_artifacts(result)
    print(json.dumps({"mode": "applied", "counts": counts, "created_works": len(result["created_works"]),
                      "created_people": len(result["created_people"])}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
