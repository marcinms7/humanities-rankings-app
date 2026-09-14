"""Import reviewed historical polls and four established published rankings.

Run without ``--apply`` for reconciliation only.  The apply path creates only
missing public catalogue identities, publishes exact source order through the
revision-aware external-list importer, and writes a separate ledger per target.
Private records and existing shared records are never deleted.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date
from html.parser import HTMLParser
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
from research.import_community_published_rankings import (
    TITLE_ALIASES,
    WORK_OVERRIDES,
    canonical_title,
    norm,
    proposed_form,
    split_authors,
    title_keys,
    xlsx_rows,
)

CHECKED_ON = "2026-09-13"
RUN = ROOT / "research" / "_runs" / CHECKED_ON / "historical-published-rankings"


# The official 2017 result page publishes every entry with at least ten votes.
RFANTASY_2017 = """1\tA Song of Ice and Fire\tGeorge R. R. Martin\t251
2\tThe Stormlight Archive\tBrandon Sanderson\t241
3\tMiddle-Earth Universe\tJ. R. R. Tolkien\t226
4\tThe Kingkiller Chronicle\tPatrick Rothfuss\t218
5\tHarry Potter\tJ. K. Rowling\t196
6\tMistborn\tBrandon Sanderson\t175
7\tGentleman Bastard\tScott Lynch\t166
8\tThe Wheel of Time\tRobert Jordan\t165
9\tThe First Law\tJoe Abercrombie\t143
10\tDiscworld\tTerry Pratchett\t139
11\tThe Malazan Book of the Fallen\tSteven Erikson\t133
12\tRealm of the Elderlings\tRobin Hobb\t126
13\tThe Dresden Files\tJim Butcher\t101
14\tWorm\tWildbow\t84
15\tDune\tFrank Herbert\t74
16\tRed Rising\tPierce Brown\t73
17\tRiyria\tMichael J. Sullivan\t71
18\tThe Broken Empire\tMark Lawrence\t66
19\tLightbringer\tBrent Weeks\t56
20\tThe Chronicles of the Black Company\tGlen Cook\t53
20\tThe Dark Tower\tStephen King\t53
21\tEnderverse\tOrson Scott Card\t50
22\tHyperion Cantos\tDan Simmons\t46
23\tThe Hitchhiker's Guide to the Galaxy\tDouglas Adams\t44
24\tHis Dark Materials\tPhilip Pullman\t42
25\tAmerican Gods\tNeil Gaiman\t41
26\tThe Chronicles of Narnia\tC. S. Lewis\t40
27\tThe Broken Earth\tN. K. Jemisin\t39
28\tPowder Mage\tBrian McClellan\t38
28\tTigana\tGuy Gavriel Kay\t38
29\tThe Lions of Al-Rassan\tGuy Gavriel Kay\t37
30\tGood Omens\tNeil Gaiman and Terry Pratchett\t33
30\tThe Witcher\tAndrzej Sapkowski\t33
31\tJonathan Strange & Mr Norrell\tSusanna Clarke\t32
31\tThe Earthsea Cycle\tUrsula K. Le Guin\t32
32\tThe Magicians\tLev Grossman\t31
33\tKushiel's Universe\tJacqueline Carey\t30
33\tThe Books of Babel\tJosiah Bancroft\t30
34\tAbhorsen\tGarth Nix\t27
34\tSandman\tNeil Gaiman\t27
35\tThe Goblin Emperor\tKatherine Addison\t26
36\tThe Book of the New Sun\tGene Wolfe\t25
37\tWorld of the Five Gods\tLois McMaster Bujold\t24
37\tUprooted\tNaomi Novik\t24
38\tNew Crobuzon\tChina Miéville\t23
38\tReady Player One\tErnest Cline\t23
38\tCulture\tIain M. Banks\t23
39\tThe Bartimaeus Sequence\tJonathan Stroud\t22
39\tTortall\tTamora Pierce\t22
40\tRedwall\tBrian Jacques\t20
41\tThe Shadow Campaigns\tDjango Wexler\t19
42\tThe Inheritance Cycle\tChristopher Paolini\t18
42\tThe Expanse\tJames S. A. Corey\t18
42\tThe Second Apocalypse\tR. Scott Bakker\t18
42\tThe Chronicles of Amber\tRoger Zelazny\t18
42\tMemory, Sorrow, and Thorn\tTad Williams\t18
42\tThrawn Trilogy\tTimothy Zahn\t18
43\tThe Belgariad\tDavid Eddings\t17
43\tFoundation Universe\tIsaac Asimov\t17
43\tThe Empire Trilogy\tJanny Wurts and Raymond E. Feist\t17
43\tVorkosigan Saga\tLois McMaster Bujold\t17
43\tThe Riftwar Cycle\tRaymond E. Feist\t17
43\tTwig\tWildbow\t17
44\tNight Angel Trilogy\tBrent Weeks\t16
44\tRaven's Shadow\tAnthony Ryan\t16
44\tThe Acts of Caine\tMatthew Woodring Stover\t16
45\tThe Drenai Saga\tDavid Gemmell\t15
45\tCodex Alera\tJim Butcher\t15
45\tThe Divine Cities\tRobert Jackson Bennett\t15
45\tThe Traitor Baru Cormorant\tSeth Dickinson\t15
45\tThe Princess Bride\tWilliam Goldman\t15
46\tElantris\tBrandon Sanderson\t14
46\tWarbreaker\tBrandon Sanderson\t14
46\tThe Sarantine Mosaic\tGuy Gavriel Kay\t14
46\tThe Demon Cycle\tPeter V. Brett\t14
47\tWatership Down\tRichard Adams\t13
47\tPercy Jackson & the Olympians\tRick Riordan\t13
48\tNeverwhere\tNeil Gaiman\t12
48\tThe Emperor's Soul\tBrandon Sanderson\t12
48\tWars of Light and Shadow\tJanny Wurts\t12
49\tThe Dagger and the Coin\tDaniel Abraham\t11
49\tThe Traitor Son Cycle\tMiles Cameron\t11
49\tInheritance Trilogy\tN. K. Jemisin\t11
49\tThe Last Unicorn\tPeter S. Beagle\t11
49\tThe Stand\tStephen King\t11
49\tPact\tWildbow\t11
50\tThe Chronicles of Thomas Covenant\tStephen R. Donaldson\t10
50\tThe Chronicle of the Unhewn Throne\tBrian Staveley\t10
50\tThe Deed of Paksenarrion\tElizabeth Moon\t10
50\tThe Dandelion Dynasty\tKen Liu\t10
50\tBook of the Ancestor\tMark Lawrence\t10
50\tThe Elric Saga\tMichael Moorcock\t10
50\tGreatcoats\tSebastien de Castell\t10
50\tWayfarers\tBecky Chambers\t10"""


NYT_2024 = """1\tMy Brilliant Friend\tElena Ferrante
2\tThe Warmth of Other Suns\tIsabel Wilkerson
3\tWolf Hall\tHilary Mantel
4\tThe Known World\tEdward P. Jones
5\tThe Corrections\tJonathan Franzen
6\t2666\tRoberto Bolaño
7\tThe Underground Railroad\tColson Whitehead
8\tAusterlitz\tW. G. Sebald
9\tNever Let Me Go\tKazuo Ishiguro
10\tGilead\tMarilynne Robinson
11\tThe Brief Wondrous Life of Oscar Wao\tJunot Díaz
12\tThe Year of Magical Thinking\tJoan Didion
13\tThe Road\tCormac McCarthy
14\tOutline\tRachel Cusk
15\tPachinko\tMin Jin Lee
16\tThe Amazing Adventures of Kavalier & Clay\tMichael Chabon
17\tThe Sellout\tPaul Beatty
18\tLincoln in the Bardo\tGeorge Saunders
19\tSay Nothing\tPatrick Radden Keefe
20\tErasure\tPercival Everett
21\tEvicted\tMatthew Desmond
22\tBehind the Beautiful Forevers\tKatherine Boo
23\tHateship, Friendship, Courtship, Loveship, Marriage\tAlice Munro
24\tThe Overstory\tRichard Powers
25\tRandom Family\tAdrian Nicole LeBlanc
26\tAtonement\tIan McEwan
27\tAmericanah\tChimamanda Ngozi Adichie
28\tCloud Atlas\tDavid Mitchell
29\tThe Last Samurai\tHelen DeWitt
30\tSing, Unburied, Sing\tJesmyn Ward
31\tWhite Teeth\tZadie Smith
32\tThe Line of Beauty\tAlan Hollinghurst
33\tSalvage the Bones\tJesmyn Ward
34\tCitizen\tClaudia Rankine
35\tFun Home\tAlison Bechdel
36\tBetween the World and Me\tTa-Nehisi Coates
37\tThe Years\tAnnie Ernaux
38\tThe Savage Detectives\tRoberto Bolaño
39\tA Visit from the Goon Squad\tJennifer Egan
40\tH Is for Hawk\tHelen Macdonald
41\tSmall Things Like These\tClaire Keegan
42\tA Brief History of Seven Killings\tMarlon James
43\tPostwar\tTony Judt
44\tThe Fifth Season\tN. K. Jemisin
45\tThe Argonauts\tMaggie Nelson
46\tThe Goldfinch\tDonna Tartt
47\tA Mercy\tToni Morrison
48\tPersepolis\tMarjane Satrapi
49\tThe Vegetarian\tHan Kang
50\tTrust\tHernan Diaz
51\tLife After Life\tKate Atkinson
52\tTrain Dreams\tDenis Johnson
53\tRunaway\tAlice Munro
54\tTenth of December\tGeorge Saunders
55\tThe Looming Tower\tLawrence Wright
56\tThe Flamethrowers\tRachel Kushner
57\tNickel and Dimed\tBarbara Ehrenreich
58\tStay True\tHua Hsu
59\tMiddlesex\tJeffrey Eugenides
60\tHeavy\tKiese Laymon
61\tDemon Copperhead\tBarbara Kingsolver
62\t10:04\tBen Lerner
63\tVeronica\tMary Gaitskill
64\tThe Great Believers\tRebecca Makkai
65\tThe Plot Against America\tPhilip Roth
66\tWe the Animals\tJustin Torres
67\tFar from the Tree\tAndrew Solomon
68\tThe Friend\tSigrid Nunez
69\tThe New Jim Crow\tMichelle Alexander
70\tAll Aunt Hagar's Children\tEdward P. Jones
71\tThe Copenhagen Trilogy\tTove Ditlevsen
72\tSecondhand Time\tSvetlana Alexievich
73\tThe Passage of Power\tRobert Caro
74\tOlive Kitteridge\tElizabeth Strout
75\tExit West\tMohsin Hamid
76\tTomorrow, and Tomorrow, and Tomorrow\tGabrielle Zevin
77\tAn American Marriage\tTayari Jones
78\tSeptology\tJon Fosse
79\tA Manual for Cleaning Women\tLucia Berlin
80\tThe Story of the Lost Child\tElena Ferrante
81\tPulphead\tJohn Jeremiah Sullivan
82\tHurricane Season\tFernanda Melchor
83\tWhen We Cease to Understand the World\tBenjamín Labatut
84\tThe Emperor of All Maladies\tSiddhartha Mukherjee
85\tPastoralia\tGeorge Saunders
86\tFrederick Douglass\tDavid W. Blight
87\tDetransition, Baby\tTorrey Peters
88\tThe Collected Stories of Lydia Davis\tLydia Davis
89\tThe Return\tHisham Matar
90\tThe Sympathizer\tViet Thanh Nguyen
91\tThe Human Stain\tPhilip Roth
92\tThe Days of Abandonment\tElena Ferrante
93\tStation Eleven\tEmily St. John Mandel
94\tOn Beauty\tZadie Smith
95\tBring Up the Bodies\tHilary Mantel
96\tWayward Lives, Beautiful Experiments\tSaidiya Hartman
97\tMen We Reaped\tJesmyn Ward
98\tBel Canto\tAnn Patchett
99\tHow to Be Both\tAli Smith
100\tTree of Smoke\tDenis Johnson"""


LIT_2024 = """1\tThe Holy Bible\tVarious authors
2\tMoby-Dick\tHerman Melville
3\tThe Brothers Karamazov\tFyodor Dostoevsky
4\tThe Iliad\tHomer
5\tThe Odyssey\tHomer
6\tCrime and Punishment\tFyodor Dostoevsky
7\tDon Quixote\tMiguel de Cervantes
8\tThe Lord of the Rings\tJ. R. R. Tolkien
9\tThe Divine Comedy\tDante Alighieri
10\tNotes from Underground\tFyodor Dostoevsky
11\tUlysses\tJames Joyce
12\tThe Trial\tFranz Kafka
13\tWar and Peace\tLeo Tolstoy
14\tFaust\tJohann Wolfgang von Goethe
15\tThe Metamorphosis\tFranz Kafka
16\tBlood Meridian\tCormac McCarthy
17\tThe First Folio\tWilliam Shakespeare
18\tDialogues\tPlato
19\tThe Stranger\tAlbert Camus
20\tAnna Karenina\tLeo Tolstoy
21\tLolita\tVladimir Nabokov
22\tIndustrial Society and Its Future\tTheodore Kaczynski
23\tInfinite Jest\tDavid Foster Wallace
24\tThe Idiot\tFyodor Dostoevsky
25\t1984\tGeorge Orwell
26\tParadise Lost\tJohn Milton
27\tDubliners\tJames Joyce
28\tStoner\tJohn Williams
29\tGravity's Rainbow\tThomas Pynchon
30\tThe Hobbit\tJ. R. R. Tolkien
31\tFicciones\tJorge Luis Borges
32\tTao Te Ching\tLaozi
33\tTragedies\tAeschylus
34\tOne Hundred Years of Solitude\tGabriel García Márquez
35\tConfessions\tAugustine of Hippo
36\tA Portrait of the Artist as a Young Man\tJames Joyce
37\tThe Aeneid\tVirgil
38\tBeowulf\tAnonymous
39\tIn Search of Lost Time\tMarcel Proust
40\tThus Spoke Zarathustra\tFriedrich Nietzsche
41\tDemons\tFyodor Dostoevsky
42\tSlaughterhouse-Five\tKurt Vonnegut
43\tHeart of Darkness\tJoseph Conrad
44\tThe Master and Margarita\tMikhail Bulgakov
45\tFrankenstein\tMary Shelley
46\tCatch-22\tJoseph Heller
47\tThe Death of Ivan Ilyich\tLeo Tolstoy
48\tThe Canterbury Tales\tGeoffrey Chaucer
49\tMetamorphoses\tOvid
50\tThe Sound and the Fury\tWilliam Faulkner
51\tThe Epic of Gilgamesh\tAnonymous
52\tThe Old Man and the Sea\tErnest Hemingway
53\tTragedies\tSophocles
54\tThe Count of Monte Cristo\tAlexandre Dumas
55\tThe Sorrows of Young Werther\tJohann Wolfgang von Goethe
56\tThe Catcher in the Rye\tJ. D. Salinger
57\tWuthering Heights\tEmily Brontë
58\tNicomachean Ethics\tAristotle
59\t2666\tRoberto Bolaño
60\tThe Sailor Who Fell from Grace with the Sea\tYukio Mishima
61\tJourney to the End of the Night\tLouis-Ferdinand Céline
62\tBrave New World\tAldous Huxley
63\tCritique of Pure Reason\tImmanuel Kant
64\tDune\tFrank Herbert
65\tThe Castle\tFranz Kafka
66\tThe Prince\tNiccolò Machiavelli
67\tAmerican Psycho\tBret Easton Ellis
68\tStorm of Steel\tErnst Jünger
69\tThe Ring of the Nibelung\tRichard Wagner
70\tSiddhartha\tHermann Hesse
71\tAnimal Farm\tGeorge Orwell
72\tMetaphysics\tAristotle
73\tThe Picture of Dorian Gray\tOscar Wilde
74\tMeditations\tMarcus Aurelius
75\tSpring Snow\tYukio Mishima
76\tEast of Eden\tJohn Steinbeck
77\tThe Magic Mountain\tThomas Mann
78\tThe Histories\tHerodotus
79\tA Confederacy of Dunces\tJohn Kennedy Toole
80\tDo Androids Dream of Electric Sheep?\tPhilip K. Dick
81\tDead Souls\tNikolai Gogol
82\tAnabasis\tXenophon
83\tMadame Bovary\tGustave Flaubert
84\tThe Name of the Rose\tUmberto Eco
85\tThe Great Gatsby\tF. Scott Fitzgerald
86\tHunger\tKnut Hamsun
87\tThe Crying of Lot 49\tThomas Pynchon
88\tSumma Theologica\tThomas Aquinas
89\tRomance of the Three Kingdoms\tLuo Guanzhong
90\tPoems\tW. B. Yeats
91\tThe Aleph\tJorge Luis Borges
92\tThe City of God\tAugustine of Hippo
93\tPolitics\tAristotle
94\tNo Longer Human\tOsamu Dazai
95\tThe Book of the New Sun\tGene Wolfe
96\tFinnegans Wake\tJames Joyce
97\tEssays\tMichel de Montaigne
98\tPhenomenology of Spirit\tG. W. F. Hegel
99\tThe World as Will and Representation\tArthur Schopenhauer
100\tA Clockwork Orange\tAnthony Burgess"""


LIT_2021 = """1\tThe Holy Bible\tAnonymous
2\tMoby-Dick\tHerman Melville
3\tThe Brothers Karamazov\tFyodor Dostoevsky
4\tThe Iliad\tHomer
5\tCrime and Punishment\tFyodor Dostoevsky
6\tInfinite Jest\tDavid Foster Wallace
7\tDon Quixote\tMiguel de Cervantes
8\tLolita\tVladimir Nabokov
9\tBlood Meridian\tCormac McCarthy
10\tAnna Karenina\tLeo Tolstoy
11\tThe Odyssey\tHomer
12\tWar and Peace\tLeo Tolstoy
13\tGravity's Rainbow\tThomas Pynchon
14\tThe Divine Comedy\tDante Alighieri
15\tUlysses\tJames Joyce
16\tFicciones\tJorge Luis Borges
17\tStoner\tJohn Williams
18\tThe Stranger\tAlbert Camus
19\tThe Lord of the Rings\tJ. R. R. Tolkien
20\tMein Kampf\tAdolf Hitler
21\tNotes from Underground\tFyodor Dostoevsky
22\tThe Catcher in the Rye\tJ. D. Salinger
23\tHamlet\tWilliam Shakespeare
24\tIn Search of Lost Time\tMarcel Proust
25\t1984\tGeorge Orwell
26\tFaust\tJohann Wolfgang von Goethe
27\tCatch-22\tJoseph Heller
28\tThe Master and Margarita\tMikhail Bulgakov
29\tEast of Eden\tJohn Steinbeck
30\tOne Hundred Years of Solitude\tGabriel García Márquez
31\tBrave New World\tAldous Huxley
32\tDune\tFrank Herbert
33\tThus Spoke Zarathustra\tFriedrich Nietzsche
34\tDemons\tFyodor Dostoevsky
35\tA Portrait of the Artist as a Young Man\tJames Joyce
36\tThe Idiot\tFyodor Dostoevsky
37\tThe Book of Disquiet\tFernando Pessoa
38\tThe Sound and the Fury\tWilliam Faulkner
39\t2666\tRoberto Bolaño
40\tThe Book of the New Sun\tGene Wolfe
41\tThe Republic\tPlato
42\tThe Sailor Who Fell from Grace with the Sea\tYukio Mishima
43\tThe Great Gatsby\tF. Scott Fitzgerald
44\tThe Count of Monte Cristo\tAlexandre Dumas
45\tMeditations\tMarcus Aurelius
46\tJourney to the End of the Night\tLouis-Ferdinand Céline
47\tAmerican Psycho\tBret Easton Ellis
48\tA Confederacy of Dunces\tJohn Kennedy Toole
49\tWuthering Heights\tEmily Brontë
50\tSlaughterhouse-Five\tKurt Vonnegut
51\tFerdydurke\tWitold Gombrowicz
52\tFear and Loathing in Las Vegas\tHunter S. Thompson
53\tDas Kapital\tKarl Marx
54\tIndustrial Society and Its Future\tTheodore Kaczynski
55\tThe Metamorphosis\tFranz Kafka
56\tDubliners\tJames Joyce
57\tFrankenstein\tMary Shelley
58\tLes Misérables\tVictor Hugo
59\tMason & Dixon\tThomas Pynchon
60\tThe Savage Detectives\tRoberto Bolaño
61\tTo the Lighthouse\tVirginia Woolf
62\tHeart of Darkness\tJoseph Conrad
63\tThe Picture of Dorian Gray\tOscar Wilde
64\tThe Tunnel\tWilliam H. Gass
65\tParadise Lost\tJohn Milton
66\tThe Old Man and the Sea\tErnest Hemingway
67\tThe Histories\tHerodotus
68\tSteppenwolf\tHermann Hesse
69\tBhagavad Gita\tVarious authors
70\tAnimal Farm\tGeorge Orwell
71\tHunger\tKnut Hamsun
72\tCritique of Pure Reason\tImmanuel Kant
73\tMadame Bovary\tGustave Flaubert
74\tThe Elementary Particles\tMichel Houellebecq
75\tNo Longer Human\tOsamu Dazai
76\tThe Grapes of Wrath\tJohn Steinbeck
77\tA Hero of Our Time\tMikhail Lermontov
78\tCandide\tVoltaire
79\tPedro Páramo\tJuan Rulfo
80\tFor Whom the Bell Tolls\tErnest Hemingway
81\tThe Death of Virgil\tHermann Broch
82\tLibra\tDon DeLillo
83\tThe Posthumous Memoirs of Brás Cubas\tMachado de Assis
84\tMacbeth\tWilliam Shakespeare
85\tThe Aeneid\tVirgil
86\tConfessions\tAugustine of Hippo
87\tThe Epic of Gilgamesh\tAnonymous
88\tThe Magic Mountain\tThomas Mann
89\tWalden\tHenry David Thoreau
90\tInvisible Cities\tItalo Calvino
91\tSiddhartha\tHermann Hesse
92\tA Clockwork Orange\tAnthony Burgess
93\tThe Crying of Lot 49\tThomas Pynchon
94\tThe Trilogy\tSamuel Beckett
95\tFinnegans Wake\tJames Joyce
96\tThe Decline of the West\tOswald Spengler
97\tPhenomenology of Spirit\tG. W. F. Hegel
98\tThe Red and the Black\tStendhal
99\tThe Temple of the Golden Pavilion\tYukio Mishima
100\tZeno's Conscience\tItalo Svevo"""


LIT_2023 = """1\tMoby-Dick\tHerman Melville
2\tThe Brothers Karamazov\tFyodor Dostoevsky
3\tThe Holy Bible\tAnonymous
4\tDon Quixote\tMiguel de Cervantes
5\tBlood Meridian\tCormac McCarthy
6\tStoner\tJohn Williams
7\tThe First Folio\tWilliam Shakespeare
8\tLolita\tVladimir Nabokov
9\tThe Iliad\tHomer
10\tUlysses\tJames Joyce
11\tCrime and Punishment\tFyodor Dostoevsky
12\tAnna Karenina\tLeo Tolstoy
13\tFaust\tJohann Wolfgang von Goethe
14\tWar and Peace\tLeo Tolstoy
15\tFicciones\tJorge Luis Borges
16\tThe Divine Comedy\tDante Alighieri
17\tThus Spoke Zarathustra\tFriedrich Nietzsche
18\tParadise Lost\tJohn Milton
19\tThe Lord of the Rings\tJ. R. R. Tolkien
20\tThe Stranger\tAlbert Camus
21\tThe Odyssey\tHomer
22\tInfinite Jest\tDavid Foster Wallace
23\tThe Book of Disquiet\tFernando Pessoa
24\tDemons\tFyodor Dostoevsky
25\tThe Book of the New Sun\tGene Wolfe
26\tIn Search of Lost Time\tMarcel Proust
27\tGravity's Rainbow\tThomas Pynchon
28\tPedro Páramo\tJuan Rulfo
29\tThe Magic Mountain\tThomas Mann
30\tThe Republic\tPlato
31\t2666\tRoberto Bolaño
32\tThe Master and Margarita\tMikhail Bulgakov
33\tMason & Dixon\tThomas Pynchon
34\tA Confederacy of Dunces\tJohn Kennedy Toole
35\tThe Ring of the Nibelung\tRichard Wagner
36\tThe Elementary Particles\tMichel Houellebecq
37\tThe Man Without Qualities\tRobert Musil
38\tHunger\tKnut Hamsun
39\tGrowth of the Soil\tKnut Hamsun
40\tThe Metamorphosis\tFranz Kafka
41\tJourney to the End of the Night\tLouis-Ferdinand Céline
42\tThe Trial\tFranz Kafka
43\tThe Old Man and the Sea\tErnest Hemingway
44\tThe Sailor Who Fell from Grace with the Sea\tYukio Mishima
45\tEast of Eden\tJohn Steinbeck
46\tSpring Snow\tYukio Mishima
47\tNotes from Underground\tFyodor Dostoevsky
48\tPale Horse, Pale Rider\tKatherine Anne Porter
49\tThe Sound and the Fury\tWilliam Faulkner
50\tThe Count of Monte Cristo\tAlexandre Dumas
51\tAbsalom, Absalom!\tWilliam Faulkner
52\tThe Hobbit\tJ. R. R. Tolkien
53\tThe Sorrows of Young Werther\tJohann Wolfgang von Goethe
54\tThe Recognitions\tWilliam Gaddis
55\tThe Idiot\tFyodor Dostoevsky
56\tCritique of Pure Reason\tImmanuel Kant
57\tSuttree\tCormac McCarthy
58\tThe Catcher in the Rye\tJ. D. Salinger
59\tA Portrait of the Artist as a Young Man\tJames Joyce
60\tGormenghast\tMervyn Peake
61\tThe Picture of Dorian Gray\tOscar Wilde
62\tSteppenwolf\tHermann Hesse
63\tSiddhartha\tHermann Hesse
64\tGargantua and Pantagruel\tFrançois Rabelais
65\tNo Longer Human\tOsamu Dazai
66\tIf on a Winter's Night a Traveler\tItalo Calvino
67\tAlice's Adventures in Wonderland\tLewis Carroll
68\tLost Illusions\tHonoré de Balzac
69\t1984\tGeorge Orwell
70\tOne Hundred Years of Solitude\tGabriel García Márquez
71\tBhagavad Gita\tVarious authors
72\tConfessions\tAugustine of Hippo
73\tStorm of Steel\tErnst Jünger
74\tThe Trilogy\tSamuel Beckett
75\tDubliners\tJames Joyce
76\tThe Temple of the Golden Pavilion\tYukio Mishima
77\tCatch-22\tJoseph Heller
78\tWuthering Heights\tEmily Brontë
79\tTropic of Cancer\tHenry Miller
80\tEssays\tMichel de Montaigne
81\tThe Name of the Rose\tUmberto Eco
82\tDead Souls\tNikolai Gogol
83\tThe Faerie Queene\tEdmund Spenser
84\tTo the Lighthouse\tVirginia Woolf
85\tThe Epic of Gilgamesh\tAnonymous
86\tLes Misérables\tVictor Hugo
87\tA Canticle for Leibowitz\tWalter M. Miller Jr.
88\tThe Waves\tVirginia Woolf
89\tAmerican Psycho\tBret Easton Ellis
90\tThe Tartar Steppe\tDino Buzzati
91\tAs I Lay Dying\tWilliam Faulkner
92\tLoser\tJerry Spinelli
93\tFrankenstein\tMary Shelley
94\tThe Cantos\tEzra Pound
95\tThe World as Will and Representation\tArthur Schopenhauer
96\tWalden\tHenry David Thoreau
97\tAnabasis\tXenophon
98\tMadame Bovary\tGustave Flaubert
99\tBrave New World\tAldous Huxley
100\tIndustrial Society and Its Future\tTheodore Kaczynski"""


def parse_tsv(value: str, votes: bool = False) -> list[dict]:
    result = []
    for line in value.splitlines():
        cells = line.split("\t")
        row = {"source_rank": int(cells[0]), "title": cells[1].strip(), "author": cells[2].strip()}
        if votes:
            row["votes"] = int(cells[3])
        result.append(row)
    return result


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self.table = self.row = self.cell = None
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.depth += 1
            if self.depth == 1:
                self.table = []
        elif self.table is not None:
            if tag == "tr":
                self.row = []
            elif tag in {"td", "th"}:
                self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if self.table is None:
            return
        if tag in {"td", "th"} and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.table.append(self.row)
            self.row = None
        elif tag == "table":
            self.depth -= 1
            if self.depth == 0:
                self.tables.append(self.table)
                self.table = None


class ParagraphParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paragraphs = []
        self.buffer = None

    def handle_starttag(self, tag, attrs):
        if tag == "p":
            self.buffer = []

    def handle_data(self, data):
        if self.buffer is not None:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if tag == "p" and self.buffer is not None:
            self.paragraphs.append(" ".join("".join(self.buffer).split()))
            self.buffer = None


class ListParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ordered_lists = []
        self.depth = 0
        self.current = self.item = None

    def handle_starttag(self, tag, attrs):
        if tag == "ol":
            self.depth += 1
            if self.depth == 1:
                self.current = []
        elif tag == "li" and self.current is not None and self.depth == 1:
            self.item = []

    def handle_data(self, data):
        if self.item is not None:
            self.item.append(data)

    def handle_endtag(self, tag):
        if tag == "li" and self.item is not None:
            self.current.append(" ".join("".join(self.item).split()))
            self.item = None
        elif tag == "ol" and self.current is not None:
            self.depth -= 1
            if self.depth == 0:
                self.ordered_lists.append(self.current)
                self.current = None


TRUELIT_COMPOSITES = {
    "Marcel Proust": "In Search of Lost Time",
    "J. R .R. Tolkien": "The Lord of the Rings",
    "Dante Alighieri": "The Divine Comedy",
    "Samuel Beckett": "The Trilogy",
    "Elena Ferrante": "The Neapolitan Novels",
    "Johann Wolfgang von Goethe": "Faust",
    "Karl Ove Knausgård": "My Struggle",
    "Jon Fosse": "Septology",
    "Yukio Mishima": "The Sea of Fertility",
    "George R. R. Martin": "A Song of Ice and Fire",
    "Gene  Wolfe": "The Book of the New Sun",
    "Mervyn Peake": "Gormenghast",
    "Peter  Weiss": "The Aesthetics of Resistance",
    "Naguib Mahfouz": "The Cairo Trilogy",
    "Cormac McCarthy": "The Border Trilogy",
    "William Shakespeare": "The First Folio",
    "Aeschylus": "The Oresteia",
}


def truelit_rows() -> dict[str, list[dict]]:
    rows = xlsx_rows(Path("/private/tmp/truelit-2019-2025.xlsx"), 1)[1:]
    result = {}
    for year, column in [(2019, "Q"), (2020, "P"), (2021, "O"), (2022, "N"), (2024, "L"), (2025, "K")]:
        grouped = defaultdict(list)
        for row in rows:
            try:
                rank = int(float(row.get(column, "")))
            except (TypeError, ValueError):
                continue
            grouped[rank].append(row)
        prepared = []
        for rank in sorted(grouped):
            members = grouped[rank]
            author = " ".join((members[0].get("D", "") + " " + members[0].get("E", "")).split())
            if len(members) > 1:
                composite_by_author = {norm(name): title for name, title in TRUELIT_COMPOSITES.items()}
                title = composite_by_author[norm(author)]
            else:
                title = members[0]["F"].strip()
            prepared.append({"source_rank": rank, "title": title, "author": author})
        result[f"reddit-truelit-{year}"] = prepared
    return result


def ranked_by_votes(rows: list[dict], title_col: str, author_col: str, votes_col: str, threshold: int) -> list[dict]:
    prepared = []
    for row in rows:
        try:
            votes = int(float(row.get(votes_col) or 0))
        except ValueError:
            continue
        if votes >= threshold:
            prepared.append({"title": canonical_title(row[title_col].strip(" *")), "author": row[author_col].strip(), "votes": votes})
    last_votes = None
    source_rank = 0
    for position, row in enumerate(prepared, 1):
        if row["votes"] != last_votes:
            source_rank = position
            last_votes = row["votes"]
        row["source_rank"] = source_rank
    return prepared


def fantasy_rows() -> dict[str, list[dict]]:
    rows_2014 = ListParser()
    rows_2014.feed(Path("/private/tmp/rfantasy-2014.html").read_text() if Path("/private/tmp/rfantasy-2014.html").stat().st_size > 10000 else Path("/private/tmp/rfantasy-2014-mirror.html").read_text())
    candidates = max(rows_2014.ordered_lists, key=len)
    parsed_2014 = []
    for position, text in enumerate(candidates[:105], 1):
        title, author = re.split(r"\s+by\s+", text, maxsplit=1, flags=re.I)
        parsed_2014.append({"source_rank": position, "title": title.strip(), "author": re.sub(r"\s*\(.*", "", author).strip()})
    rows_2021 = ranked_by_votes(xlsx_rows(Path("/private/tmp/rfantasy-2021.xlsx"), 3)[1:], "B", "D", "C", 5)
    seen_2021 = set()
    rows_2021 = [row for row in rows_2021 if not ((key := (norm(row["title"]), norm(row["author"]))) in seen_2021 or seen_2021.add(key))]
    return {
        "reddit-fantasy-top-novels-2014": parsed_2014,
        "reddit-fantasy-top-novels-2015": ranked_by_votes(xlsx_rows(Path("/private/tmp/rfantasy-2015.xlsx"), 1), "A", "B", "C", 3),
        "reddit-fantasy-top-novels-2017": parse_tsv(RFANTASY_2017, votes=True),
        "reddit-fantasy-top-novels-2019": ranked_by_votes(xlsx_rows(Path("/private/tmp/rfantasy-2019.xlsx"), 1), "A", "B", "C", 5),
        "reddit-fantasy-top-novels-2021": rows_2021,
        "reddit-fantasy-top-novels-2025": ranked_by_votes(xlsx_rows(Path("/private/tmp/rfantasy-2025.xlsx"), 1)[1:], "B", "E", "D", 5),
    }


SURNAME_EXPANSIONS = {
    "": "Various authors", "Orwell": "George Orwell", "Bolaño": "Roberto Bolaño", "Barthelme": "Donald Barthelme",
    "Miller Jr.": "Walter M. Miller Jr.", "Burgess": "Anthony Burgess", "Toole": "John Kennedy Toole",
    "Hemingway": "Ernest Hemingway", "Lermontov": "Mikhail Lermontov", "Joyce": "James Joyce",
    "Twain": "Mark Twain", "Virgil": "Virgil", "Huysmans": "Joris-Karl Huysmans", "Carroll": "Lewis Carroll",
    "Ellis": "Bret Easton Ellis", "Tolstoy": "Leo Tolstoy", "Taleb": "Nassim Nicholas Taleb",
    "Benjamin": "Walter Benjamin", "Faulkner": "William Faulkner", "Heidegger": "Martin Heidegger",
    "Nietzsche": "Friedrich Nietzsche", "McCarthy": "Cormac McCarthy", "Schmidt": "Arno Schmidt",
    "Huxley": "Aldous Huxley", "Bronze Age Pervert": "Bronze Age Pervert", "Mann": "Thomas Mann",
    "Voltaire": "Voltaire", "Steinbeck": "John Steinbeck", "Marx": "Karl Marx", "Heller": "Joseph Heller",
    "Augustine": "Augustine of Hippo", "Mishima": "Yukio Mishima", "Bernhard": "Thomas Bernhard",
    "Dostoevsky": "Fyodor Dostoevsky", "Kant": "Immanuel Kant", "Stephenson": "Neal Stephenson",
    "Bradbury": "Ray Bradbury", "Gogol": "Nikolai Gogol", "Dick": "Philip K. Dick", "Cervantes": "Miguel de Cervantes",
    "Herbert": "Frank Herbert", "Montaigne": "Michel de Montaigne", "Spinoza": "Baruch Spinoza",
    "Land": "Nick Land", "Goethe": "Johann Wolfgang von Goethe", "Thompson": "Hunter S. Thompson",
    "Kierkegaard": "Søren Kierkegaard", "Borges": "Jorge Luis Borges", "Palahniuk": "Chuck Palahniuk",
    "Pynchon": "Thomas Pynchon", "Hamsun": "Knut Hamsun", "Shakespeare": "William Shakespeare",
    "Conrad": "Joseph Conrad", "Cortázar": "Julio Cortázar", "Danielewski": "Mark Z. Danielewski",
    "Sōseki": "Natsume Sōseki", "Calvino": "Italo Calvino", "Wilson; Shea": "Robert Shea and Robert Anton Wilson",
    "Kaczynski": "Theodore Kaczynski", "Proust": "Marcel Proust", "Wallace": "David Foster Wallace",
    "Gaddis": "William Gaddis", "Moore": "Alan Moore", "Céline": "Louis-Ferdinand Céline", "Murakami": "Haruki Murakami",
    "Whitman": "Walt Whitman", "Hugo": "Victor Hugo", "Grossman": "Vasily Grossman", "Nabokov": "Vladimir Nabokov",
    "Descartes": "René Descartes", "Burroughs": "William S. Burroughs", "Aurelius": "Marcus Aurelius",
    "Sartre": "Jean-Paul Sartre", "Gibson": "William Gibson", "Dazai": "Osamu Dazai", "Goncharov": "Ivan Goncharov",
    "Cioran": "Emil Cioran", "Kerouac": "Jack Kerouac", "Márquez": "Gabriel García Márquez", "Rulfo": "Juan Rulfo",
    "Aquinas": "Thomas Aquinas", "Browne": "Thomas Browne", "Pessoa": "Fernando Pessoa", "Wolfe": "Gene Wolfe",
    "Chaucer": "Geoffrey Chaucer", "Kafka": "Franz Kafka", "Salinger": "J. D. Salinger", "Merrill": "James Merrill",
    "Dumas": "Alexandre Dumas", "Spengler": "Oswald Spengler", "Alighieri": "Dante Alighieri",
    "Houellebecq": "Michel Houellebecq", "Spenser": "Edmund Spenser", "Camus": "Albert Camus",
    "Baudelaire": "Charles Baudelaire", "Rand": "Ayn Rand", "James": "Henry James", "Buck": "Pearl S. Buck",
    "Solzhenitsyn": "Aleksandr Solzhenitsyn", "Adams": "Douglas Adams", "Tolkien": "J. R. R. Tolkien",
    "Lampedusa": "Giuseppe Tomasi di Lampedusa", "Burton": "Robert Burton", "Lovecraft": "H. P. Lovecraft",
    "Whitehead": "Alfred North Whitehead", "Strugatzky, A. & B.": "Arkady Strugatsky and Boris Strugatsky",
    "Debord": "Guy Debord", "Lem": "Stanisław Lem", "Kesey": "Ken Kesey", "Hesse": "Hermann Hesse",
    "Vonnegut": "Kurt Vonnegut", "Melville": "Herman Melville", "Bataille": "Georges Bataille",
    "Laozi": "Laozi", "Vyasa": "Vyasa", "Buzzati": "Dino Buzzati", "Wilde": "Oscar Wilde",
    "Ishiguro": "Kazuo Ishiguro", "Lispector": "Clarice Lispector", "Assis": "Machado de Assis",
    "Machiavelli": "Niccolò Machiavelli", "Guénon": "René Guénon", "Stendhal": "Stendhal",
    "Sebald": "W. G. Sebald", "Tartt": "Donna Tartt", "Yeats": "W. B. Yeats", "Plato": "Plato",
    "Woolf": "Virginia Woolf", "Sterne": "Laurence Sterne", "Lowry": "Malcolm Lowry", "White": "Patrick White",
    "DiAngelo": "Robin DiAngelo", "Brontë": "Emily Brontë", "Zhuangzi": "Zhuangzi",
}


def lit_archive_rows() -> dict[str, list[dict]]:
    parser = TableParser()
    parser.feed(Path("/private/tmp/lit-top100-wiki.html").read_text())
    table = parser.tables[0]
    result = {}
    for offset, year in enumerate(range(2020, 2013, -1), 2):
        rows = []
        for cells in table[1:]:
            if len(cells) > offset and cells[offset].isdigit():
                author = SURNAME_EXPANSIONS.get(cells[1], cells[1])
                if cells[0] == "Watership Down":
                    author = "Richard Adams"
                rows.append({"source_rank": int(cells[offset]), "title": cells[0], "author": author})
        if year == 2014:
            # The archived comparison table accidentally omits this chart row;
            # it was checked directly against the original 2014 image.
            rows.append({"source_rank": 54, "title": "Harry Potter", "author": "J. K. Rowling"})
        result[f"fourchan-lit-top-100-{year}"] = sorted(rows, key=lambda row: row["source_rank"])
    result["fourchan-lit-top-100-2021"] = parse_tsv(LIT_2021)
    result["fourchan-lit-top-100-2023"] = parse_tsv(LIT_2023)
    result["fourchan-lit-top-100-2024"] = parse_tsv(LIT_2024)
    return result


def established_rows() -> dict[str, list[dict]]:
    modern = ParagraphParser()
    modern.feed(Path("/private/tmp/modern-official.html").read_text())
    modern_rows = []
    for paragraph in modern.paragraphs:
        match = re.match(r"^(\d+)\.\s+(.+?)\s+by\s+(.+)$", paragraph, re.I)
        if match and len(modern_rows) < 100:
            modern_rows.append({"source_rank": int(match.group(1)), "title": match.group(2).title(), "author": match.group(3)})

    bbc = ListParser()
    bbc.feed(Path("/private/tmp/bbc.html").read_text())
    bbc_list = next(rows for rows in bbc.ordered_lists if len(rows) == 200)
    bbc_rows = []
    for position, text in enumerate(bbc_list, 1):
        title, author = re.split(r"\s+by\s+", text, maxsplit=1, flags=re.I)
        bbc_rows.append({"source_rank": position, "title": title, "author": author})

    lemonde = TableParser()
    lemonde.feed(Path("/private/tmp/lemonde.html").read_text())
    # The accessible table concatenates occasional English alternate titles;
    # strip only the four known concatenations retained in its plain text.
    alternate = {
        "The StrangerThe Outsider": "The Stranger",
        "In Search of Lost TimeRemembrance of Things Past": "In Search of Lost Time",
        "Journey to the End of the NightJourney to the End of Night": "Journey to the End of the Night",
        "The Little PrinceLe Petit Prince": "The Little Prince",
    }
    lemonde_rows = [
        {"source_rank": int(row[0]), "title": alternate.get(row[1], row[1]), "author": row[2]}
        for row in lemonde.tables[0][1:] if row and row[0].isdigit()
    ]
    return {
        "modern-library-board-100-novels-1998": modern_rows,
        "new-york-times-best-books-21st-century-2024": parse_tsv(NYT_2024),
        "bbc-big-read-2003": bbc_rows,
        "le-monde-fnac-100-books-century-1999": lemonde_rows,
    }


def definitions() -> dict[str, dict]:
    rows = {}
    for year in [2019, 2020, 2021, 2022, 2024, 2025]:
        rows[f"reddit-truelit-{year}"] = {
            "title": f"r/TrueLit · Favorite Books ({year})", "publisher": "r/TrueLit community",
            "url": "https://docs.google.com/spreadsheets/d/1SDFJoL_Yepj4FvFsfYTYcL1jzMxsr_KIJZnBHeR9POU/edit",
            "family": "community_poll", "method": "Published annual result order, transcribed from the cross-year consolidation; source ties and composite works retained.",
            "limitation": "The consolidation is community-maintained. Series expanded into volume rows there were restored to the single composite entry used by the original poll.",
        }
    true_urls = {
        2022: "https://www.reddit.com/r/TrueLit/comments/106kmlm/truelits_2022_top_100_favorite_books/",
        2024: "https://www.reddit.com/r/TrueLit/comments/1i5re2u/truelits_2024_top_100_favorite_books/",
        2025: "https://www.reddit.com/r/TrueLit/comments/1qj7qm0/truelits_2025_hall_of_fame_and_top_100_favorite/",
    }
    for year, url in true_urls.items():
        rows[f"reddit-truelit-{year}"]["url"] = url
        rows[f"reddit-truelit-{year}"]["mirror"] = "https://docs.google.com/spreadsheets/d/1SDFJoL_Yepj4FvFsfYTYcL1jzMxsr_KIJZnBHeR9POU/edit"
    rows["reddit-truelit-2025"]["limitation"] += " The separately presented Hall of Fame is not part of this Top 100 import."

    fantasy_urls = {
        2014: "https://www.reddit.com/r/Fantasy/comments/1ynqcm/the_top_rfantasy_novels_of_all_time_results_thread/",
        2015: "https://www.reddit.com/r/Fantasy/comments/30h21n/the_2015_top_rfantasy_novels_of_all_time_poll/",
        2017: "https://www.reddit.com/r/Fantasy/comments/6wddcu/the_rfantasy_top_novels_poll_2017_now_with_star/",
        2019: "https://www.reddit.com/r/Fantasy/comments/c7d7z8/the_rfantasy_2019_top_novels_poll_results/",
        2021: "https://www.reddit.com/r/Fantasy/comments/p1mwnx/the_rfantasy_2021_top_novels_poll_results/",
        2025: "https://www.reddit.com/r/Fantasy/comments/1jjif55/rfantasy_top_novels_2025_results/",
    }
    for year, url in fantasy_urls.items():
        rows[f"reddit-fantasy-top-novels-{year}"] = {
            "title": f"r/Fantasy · Top Novels ({year})", "publisher": "r/Fantasy community", "url": url,
            "family": "community_poll", "method": "Complete result at the edition's published cutoff, preserving source ranks, ties, votes and series-level entries.",
            "limitation": "Community self-selection; the source deliberately mixes standalone books, series and fictional universes.",
        }
    rows["reddit-fantasy-top-novels-2014"]["mirror"] = "https://riyria.blogspot.com/2015/03/in-2014-rfantasy-had-more-than-50000.html"
    rows["reddit-fantasy-top-novels-2021"]["limitation"] += " One acknowledged lower duplicate in the official spreadsheet was excluded; the remaining source ranks were not renumbered."

    for year in list(range(2014, 2022)) + [2023, 2024]:
        rows[f"fourchan-lit-top-100-{year}"] = {
            "title": f"4chan /lit/ · Top 100 Books ({year})", "publisher": "4chan /lit/ community",
            "url": "https://web.archive.org/web/20240807003520id_/https://4chanlit.fandom.com/wiki//lit/_Top_100_Lists" if year <= 2020 else "https://www.listchallenges.com/lits-top-100-books-2021" if year == 2021 else "https://www.listchallenges.com/4chan-lits-top-100-2023" if year == 2023 else "https://warosu.org/lit/thread/24093695",
            "family": "community_poll", "method": "All 100 positions from the archived annual comparison table or result chart; source order retained.",
            "limitation": "Anonymous-board, self-selected poll. The archive reports that later editions were not always run with the same formal poll procedure.",
        }
    rows["fourchan-lit-top-100-2023"]["url"] = "https://www.reddit.com/r/4chan/comments/190jl6c/lits_top_100_books_of_all_time_for_2023/"
    rows["fourchan-lit-top-100-2023"]["mirror"] = "https://www.listchallenges.com/4chan-lits-top-100-2023"
    rows["fourchan-lit-top-100-2021"]["limitation"] += " The original chart survives through a complete third-party transcription."

    rows.update({
        "modern-library-board-100-novels-1998": {
            "title": "Modern Library · Board's 100 Best Novels (1998)", "publisher": "Modern Library",
            "url": "https://sites.prh.com/modern-library-top-100/", "family": "publisher_list",
            "method": "All 100 novels in the Modern Library board's published order.",
            "limitation": "Restricted to English-language novels of the twentieth century and shaped by the publisher-appointed board.",
        },
        "new-york-times-best-books-21st-century-2024": {
            "title": "The New York Times · 100 Best Books of the 21st Century (2024)", "publisher": "The New York Times Book Review",
            "url": "https://www.nytimes.com/interactive/2024/books/best-books-21st-century.html", "family": "media_expert_poll",
            "method": "All 100 positions from the Book Review's 2024 survey of 503 writers, critics and other literary participants.",
            "limitation": "A survey of invited participants, published only a quarter of the way through the century; source order is not Marginalia's assessment.",
            "mirror": "https://english.northwestern.edu/documents/undergraduate/literature/nyt-best-100-books-21c-two-pager.pdf",
        },
        "bbc-big-read-2003": {
            "title": "BBC · The Big Read (2003)", "publisher": "BBC",
            "url": "https://www.bbc.co.uk/arts/bigread/", "family": "public_poll",
            "method": "All 200 novels in the final public-vote order.",
            "limitation": "UK public popularity poll; multiple books by an author could appear below the top 21, while the final top-21 vote imposed one book per author.",
            "mirror": "https://en.wikipedia.org/wiki/The_Big_Read",
        },
        "le-monde-fnac-100-books-century-1999": {
            "title": "Le Monde/Fnac · 100 Books of the Century (1999)", "publisher": "Le Monde and Fnac",
            "url": "https://www.lemonde.fr/archives/article/1999/10/15/cent-disques-cent-films-et-cent-livres-pour-un-siecle_3570803_1819218.html",
            "family": "public_poll", "method": "All 100 positions from the 1999 poll of 17,000 French respondents, from a 200-title shortlist.",
            "limitation": "French public-memory poll from a publisher/journalist shortlist; the list includes several multi-volume or non-novel works.",
            "mirror": "https://en.wikipedia.org/wiki/Le_Monde%27s_100_Books_of_the_Century",
        },
    })
    return rows


EXTRA_TITLE_ALIASES = {
    "Nineteen Eighty-Four": "1984", "Moby Dick": "Moby-Dick", "Moby-Dick or, The Whale": "Moby-Dick",
    "Fictions": "Ficciones", "Capital": "Das Kapital", "Catch 22": "Catch-22", "The Naked Lunch": "Naked Lunch",
    "Finnegan's Wake": "Finnegans Wake", "The Illiad": "The Iliad", "Metamorphosis": "The Metamorphosis",
    "Atomised": "The Elementary Particles", "Elementary Particles": "The Elementary Particles",
    "The Death of Ivan Ilych": "The Death of Ivan Ilyich", "Portrait of the Artist as a Young Man": "A Portrait of the Artist as a Young Man",
    "The Book of Disquiet: The Complete Edition": "The Book of Disquiet", "Lord of the Rings": "The Lord of the Rings",
    "The Simarillion": "The Silmarillion", "Vorkosiga Saga": "Vorkosigan Saga",
}
for source, target in EXTRA_TITLE_ALIASES.items():
    TITLE_ALIASES[norm(source)] = norm(target)

REVIEWED_WORK_CHOICES = {
    (norm("The Oresteia"), norm("Aeschylus")): 3094,
    (norm("The Adventures of Huckleberry Finn"), norm("Mark Twain")): 263,
    (norm("Capital"), norm("Karl Marx")): 474,
    (norm("Das Kapital"), norm("Karl Marx")): 474,
    (norm("Roadside Picnic"), norm("Arkady Strugatsky")): 5110,
    (norm("Roadside Picnic"), norm("Arkady Strugatsky and Boris Strugatsky")): 5110,
    (norm("The Bhagavad Gita"), norm("Vyasa")): 1513,
    (norm("The Histories"), norm("Herodotus")): 2590,
    (norm("A House for Mr Biswas"), norm("V.S. Naipaul")): 136,
    (norm("The Diary of a Nobody"), norm("George and Weedon Grossmith")): 399,
    (norm("A Room of One's Own"), norm("Virginia Woolf")): 168,
}


def make_index():
    by_title = defaultdict(list)
    for work in Work.objects.filter(is_archived=False).prefetch_related("authors"):
        for key in title_keys(work.title):
            by_title[key].append(work)
    return by_title


def resolve_work(row, by_title):
    override_id = REVIEWED_WORK_CHOICES.get((norm(row["title"]), norm(row["author"]))) or WORK_OVERRIDES.get((norm(row["title"]), norm(row["author"])))
    if override_id:
        return Work.objects.get(pk=override_id, is_archived=False), "reviewed_duplicate_choice"
    matches = {work.pk: work for key in title_keys(row["title"]) for work in by_title.get(key, [])}
    if not matches:
        return None, "missing"
    wanted = {norm(name) for name in split_authors(row["author"])}
    exact, surname = [], []
    for work in matches.values():
        existing = {norm(person.name) for person in work.authors.all()}
        if wanted and existing == wanted:
            exact.append(work)
        elif wanted and all(any(a.endswith(w) or w.endswith(a) for a in existing) for w in wanted):
            surname.append(work)
    narrowed = exact or surname
    if len(narrowed) == 1:
        return narrowed[0], "title_author"
    homonymous_titles = {norm(value) for value in ("Meditations", "Confessions", "Histories", "The Histories", "Poems", "Tragedies", "Essays")}
    if len(matches) == 1 and norm(row["title"]) not in homonymous_titles:
        only = next(iter(matches.values()))
        return only, "unique_title"
    if len(matches) == 1:
        return None, "missing"
    return None, "ambiguous:" + ",".join(str(pk) for pk in sorted(matches))


def source_lists():
    rows = {}
    rows.update(truelit_rows())
    rows.update(fantasy_rows())
    rows.update(lit_archive_rows())
    rows.update(established_rows())
    expected = {slug: 100 for slug in rows if slug.startswith("fourchan-lit-")}
    expected.update({
        "reddit-truelit-2019": 50, "reddit-truelit-2020": 100, "reddit-truelit-2021": 100,
        "reddit-truelit-2022": 98, "reddit-truelit-2024": 100, "reddit-truelit-2025": 100,
        "reddit-fantasy-top-novels-2014": 105, "reddit-fantasy-top-novels-2015": 85,
        "reddit-fantasy-top-novels-2017": 94, "reddit-fantasy-top-novels-2019": 147,
        "reddit-fantasy-top-novels-2021": 233, "reddit-fantasy-top-novels-2025": 293,
        "modern-library-board-100-novels-1998": 100, "new-york-times-best-books-21st-century-2024": 100,
        "bbc-big-read-2003": 200, "le-monde-fnac-100-books-century-1999": 100,
    })
    actual = {slug: len(values) for slug, values in rows.items()}
    if actual != expected:
        raise RuntimeError(f"Extraction count mismatch: expected {expected}, got {actual}")
    return rows


def ensure_definitions(defs):
    for slug, definition in defs.items():
        ranking, created = Ranking.objects.get_or_create(slug=slug, defaults={
            "title": definition["title"], "origin": "external", "presentation": "ranked", "domain": "collections",
            "item_type": "work", "is_public": True, "source_url": definition["url"], "publisher": definition["publisher"],
            "status": "pending_import", "description": definition["limitation"], "scope": {"external_metadata": definition},
        })
        if created:
            ranking.full_clean()


def prepare(apply: bool):
    lists = source_lists()
    defs = definitions()
    by_title = make_index()
    people_by_name = defaultdict(list)
    for person in Person.objects.filter(is_archived=False):
        people_by_name[norm(person.name)].append(person)
    mapped, created_works, created_people, ambiguous = {}, [], [], []
    with transaction.atomic():
        if apply:
            ensure_definitions(defs)
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
                    for name in split_authors(row["author"] or "Various authors"):
                        candidates = people_by_name[norm(name)]
                        person = min(candidates, key=lambda item: item.pk) if candidates else None
                        if person is None:
                            person = Person(name=name, source_url=defs[slug]["url"])
                            person.full_clean(); person.save()
                            people_by_name[norm(name)].append(person)
                            created_people.append({"id": person.pk, "name": name})
                        people.append(person)
                    work = Work(title=row["title"], form=proposed_form(row["title"]), field="literature",
                                description=f"Source-defined entry in {defs[slug]['title']}; edition and cover metadata pending.")
                    work.full_clean(); work.save(); work.authors.set(people)
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
            raise RuntimeError(f"Resolve {len(ambiguous)} rows before import: {ambiguous[:20]}")
        if not apply:
            transaction.set_rollback(True)
    return {"lists": lists, "mapped": mapped, "created_works": created_works, "created_people": created_people,
            "would_create": sum(row["resolution"] == "would_create" for values in mapped.values() for row in values)}


def source_records(slug, definition):
    records = [{
        "source_id": "PUBLISHED-LIST-01", "underlying_source_id": "published-list:" + definition["url"],
        "title": definition["title"] + " — result publication", "canonical_url": definition["url"],
        "source_family": definition["family"], "publisher": definition["publisher"], "target_ids": [slug],
        "relevance_by_target": {slug: definition["method"]}, "evidence_notes": definition["method"],
        "accessed_at": CHECKED_ON, "eligible": True, "limitations": definition["limitation"],
    }]
    if definition.get("mirror"):
        records.append({
            "source_id": "PUBLISHED-LIST-02", "underlying_source_id": "published-list:" + definition["mirror"],
            "title": definition["title"] + " — transcription/data mirror", "canonical_url": definition["mirror"],
            "source_family": "list_transcription", "publisher": definition["publisher"], "target_ids": [slug],
            "relevance_by_target": {slug: "Row-level transcription used to preserve and cross-check the complete order."},
            "evidence_notes": "Row-level transcription used to preserve and cross-check the complete order.",
            "accessed_at": CHECKED_ON, "eligible": True, "limitations": "Mirror of the same list; not counted as independent opinion evidence.",
        })
    return records


def save_artifacts(result):
    defs = definitions()
    RUN.mkdir(parents=True, exist_ok=True)
    source_paths = [
        Path("/private/tmp/truelit-2019-2025.xlsx"),
        Path("/private/tmp/rfantasy-2014-mirror.html"),
        Path("/private/tmp/rfantasy-2015.xlsx"),
        Path("/private/tmp/rfantasy-2019.xlsx"),
        Path("/private/tmp/rfantasy-2021.xlsx"),
        Path("/private/tmp/rfantasy-2025.xlsx"),
        Path("/private/tmp/lit-top100-wiki.html"),
        Path("/private/tmp/lit-2014c.jpg"),
        Path("/private/tmp/lit24-0"),
        Path("/private/tmp/modern-official.html"),
        Path("/private/tmp/nyt-100.pdf"),
        Path("/private/tmp/bbc.html"),
        Path("/private/tmp/lemonde.html"),
    ]
    audit = {
        "checked_on": CHECKED_ON,
        "targets": {},
        "catalog": {"created_works": result["created_works"], "created_people": result["created_people"]},
        "source_snapshots": {
            path.name: {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in source_paths if path.is_file()
        },
    }
    for slug, rows in result["mapped"].items():
        definition = defs[slug]
        directory = ROOT / "research" / slug
        directory.mkdir(parents=True, exist_ok=True)
        reviewed = [{key: row[key] for key in ("source_rank", "title", "author", "votes") if key in row} for row in rows]
        reviewed_path = directory / "source-list-reviewed-20260913.json"
        reviewed_path.write_text(json.dumps(reviewed, ensure_ascii=False, indent=2) + "\n")
        ledger = {"target_id": slug, "status": "named_external_list_import", "saved_at": CHECKED_ON,
                  "sources": source_records(slug, definition)}
        (directory / "sources.json").write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n")
        ranking = Ranking.objects.get(slug=slug)
        entries = []
        for row in rows:
            note = f"{row['author']} — source-defined list entry"
            if "votes" in row:
                note += f"; {row['votes']} votes"
            entries.append({"work_id": row["work_id"], "source_rank": row["source_rank"], "note": note})
        payload = {"target": slug, "presentation": "ranked", "expected_revision": ranking.revision,
                   "source_checked_on": CHECKED_ON, "status": "imported", "unresolved_count": 0,
                   "method_note": definition["method"], "allow_reviewed_replacement": bool(ranking.entries.filter(is_archived=False).exists()),
                   "entries": entries}
        input_path = directory / "reviewed-contents-20260913.json"
        input_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        call_command("import_external_list", str(input_path))
        ranking.refresh_from_db()
        now = timezone.now()
        ranking.target_size = len(entries); ranking.last_researched_at = now; ranking.last_sources_checked_at = now
        ranking.scope = {**ranking.scope, "entry_semantics": "publisher/community-defined books, series, collections or composite works",
                         "source_entry_count": len(entries), "source_method": definition["method"], "source_limitations": definition["limitation"]}
        ranking.full_clean(); ranking.save()
        for record in source_records(slug, definition):
            source, created = ResearchSource.objects.get_or_create(
                ranking=ranking, underlying_source_id=record["underlying_source_id"],
                defaults={"source_id": record["source_id"], "title": record["title"], "url": record["canonical_url"],
                          "family": record["source_family"], "publisher": record["publisher"], "evidence": record["evidence_notes"],
                          "limitations": record["limitations"], "consulted_on": date.fromisoformat(CHECKED_ON), "eligible": True, "metadata": record})
            if created:
                source.full_clean()
        (directory / "RESEARCH.md").write_text(
            f"# {definition['title']}\n\nStatus: fully imported named published ranking ({len(entries)} entries), checked {CHECKED_ON}.\n\n"
            f"Source: {definition['url']}\n\nMethod: {definition['method']}\n\n"
            "The source ordering, ranks and ties are stored separately from Marginalia's researched rankings and personal assessments. "
            "No criteria, weights or private scores were assigned. Missing edition/cover enrichment does not alter membership.\n\n"
            f"Limitations: {definition['limitation']}\n\nArtifacts: `{reviewed_path.name}`, `{input_path.name}`, its import receipt, and `sources.json`.\n")
        audit["targets"][slug] = {"ranking_id": ranking.pk, "entries": len(entries), "revision": ranking.revision,
                                   "source_count": ranking.sources.filter(is_archived=False).count(),
                                   "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest()}
    (RUN / "publication-audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        result = prepare(False)
        summary = {"counts": {slug: len(rows) for slug, rows in result["mapped"].items()}, "would_create": result["would_create"]}
        print(json.dumps({"mode": "read_only", **summary}, ensure_ascii=False, indent=2)); return
    with transaction.atomic():
        result = prepare(True)
        summary = {"counts": {slug: len(rows) for slug, rows in result["mapped"].items()}, "would_create": result["would_create"]}
        save_artifacts(result)
    print(json.dumps({"mode": "applied", **summary, "created_works": len(result["created_works"]),
                      "created_people": len(result["created_people"])}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
