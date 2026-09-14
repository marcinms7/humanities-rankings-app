"""2021 primary dated records, full public 2026 schedule, and lecture catalogue."""
from import_collection_repairs import *

URL='https://www.patreon.com/hardcoreliterature/posts/hardcore-book-48439779'
dated={r['id']:r['text'] for r in json.loads((RUN/'dated-post-checks.json').read_text())}
dated.update({r['id']:r['text'] for r in json.loads((RUN/'dated-post-retries.json').read_text()) if re.search(r'\b2021\b',r['text'])})
items=[(11,'Anna Karenina','Leo Tolstoy'),(278,'Crime and Punishment','Fyodor Dostoevsky'),(578,'A Living Relic','Ivan Turgenev'),
 (308,'Persuasion','Jane Austen'),(580,'The Library of Babel','Jorge Luis Borges'),(471,'The Marriage of Heaven and Hell','William Blake'),
 (387,'Siddhartha','Hermann Hesse'),(393,'Don Quixote','Miguel de Cervantes'),(292,'Les Misérables','Victor Hugo'),
 (560,'Frankenstein','Mary Shelley'),(555,'Self-Reliance','Ralph Waldo Emerson'),(436,'Middlemarch','George Eliot'),
 (403,'Great Expectations','Charles Dickens'),(409,'A Christmas Carol','Charles Dickens')]
rows=[]
for id,title,author in items:
    s=dated[id];date=re.search(r'L\d+: ([A-Z][a-z]{2} \d+, 2021)',s)
    if not date:raise ValueError((id,'no verified 2021 date'))
    url=re.search(r'https://www.patreon.com/[^)\s]+',s)[0]
    note='Public post title and date confirm membership; paid lecture content was not accessed. '+url
    if id==471:note+=' Lecture covers Proverbs of Hell, an excerpt from The Marriage of Heaven and Hell.'
    if id==436:note+=' Serial-reading guide issued in November 2021; lectures continued in 2022.'
    rows.append(dict(title=title,author=author,group=date[1],note=note))
save('mcevoy-schedule-2021-reviewed-rows.json',rows)
prepare('mcevoy-schedule-2021',rows,URL,'Membership verified from fourteen public 2021 dated post headers. Complete rest-of-2021 syllabus is member-only; this is a documented partial reconstruction, not a claim to reproduce every assignment.',
    'Verified 2021 book-club readings and named supplementary works, in dated introduction order. Includes Middlemarch’s November serial-reading guide; the reading continued in 2022. Partial: the complete original syllabus is member-only, and the public sitemap stops in February 2022.')
p=RUN/'mcevoy-schedule-2021-definition.json';d=json.loads(p.read_text());d.update(title='Hardcore Literature · 2021 book-club readings',presentation='reading_sequence',status='partially_imported',unresolved_count=1);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')

schedule='''January–February|Lonesome Dove|Larry McMurtry
January–February|The Oresteia|Aeschylus
January–February|Oedipus Rex|Sophocles
January–February|Medea|Euripides
March–April|The Idiot|Fyodor Dostoevsky
March–April|Poetry|William Blake
March–April|The Art of War|Sun Tzu
May–June|My Brilliant Friend|Elena Ferrante
May–June|The Story of a New Name|Elena Ferrante
May–June|Those Who Leave and Those Who Stay|Elena Ferrante
May–June|The Story of the Lost Child|Elena Ferrante
May–June|The Wind in the Willows|Kenneth Grahame
May–June|Short Stories|Clarice Lispector
May–June|The Bhagavad Gita|
July–August|Swann's Way|Marcel Proust
July–August|Within a Budding Grove|Marcel Proust
July–August|Finnegans Wake|James Joyce
July–August|Confessions|Augustine of Hippo
September–October|The Picture of Dorian Gray|Oscar Wilde
September–October|Beowulf|
September–October|On the Origin of Species|Charles Darwin
November–December|The Left Hand of Darkness|Ursula K. Le Guin
Self-paced continuing project|The Complete Works of Shakespeare|William Shakespeare'''
rows26=[]
for line in schedule.splitlines():
    period,t,a=line.split('|');r=dict(title=t,author=a,group='2026 · '+period,note='Published schedule: https://www.patreon.com/hardcoreliterature/about')
    if a=='Elena Ferrante':r['note']+=' One of the four Neapolitan Quartet novels; the contents page names all four.'
    if t in ['Poetry','Short Stories']:r.update(form='collection',note=r['note']+' Unspecified selection; no particular edition is prescribed here.')
    rows26.append(r)
save('mcevoy-schedule-2026-reviewed-rows.json',rows26)
prepare('mcevoy-schedule-2026',rows26,'https://www.patreon.com/hardcoreliterature/about',
    'Full named public 2026 schedule, including all four Neapolitan novels and two specified Proust volumes. Secret Dickens Novel remains unresolved, not guessed. Shakespeare is a separate self-paced continuing assignment.',
    'The published January–December 2026 programme, including supporting plays, poetry and philosophy. The Neapolitan Quartet is expanded into its four named novels. The November–December “Secret Dickens Novel” has not been named publicly here and is not fabricated. Shakespeare is a continuing self-paced project.')
p=RUN/'mcevoy-schedule-2026-definition.json';d=json.loads(p.read_text());d.update(status='partially_imported',unresolved_count=1);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')

# All dated memberships plus the complete public contents page's additional named works.
allrows=json.loads((RUN/'annual-reviewed-rows.json').read_text())+rows
for r in allrows:r['group']='Dated public lecture archive · '+r['group']
extra='''The Two Gentlemen of Verona|William Shakespeare
The Rape of Lucrece|William Shakespeare
Venus and Adonis|William Shakespeare
King Lear|William Shakespeare
The Two Noble Kinsmen|William Shakespeare
Neapolitan Quartet|Elena Ferrante
My Brilliant Friend|Elena Ferrante
The Story of a New Name|Elena Ferrante
Those Who Leave and Those Who Stay|Elena Ferrante
The Story of the Lost Child|Elena Ferrante
The Idiot|Fyodor Dostoevsky
Lonesome Dove|Larry McMurtry
The Oresteia|Aeschylus
Oedipus Rex|Sophocles
Medea|Euripides
Poetry|William Blake
Short Stories|Clarice Lispector
Short Stories|Franz Kafka
The Wind in the Willows|Kenneth Grahame
The Art of War|Sun Tzu
The Bhagavad Gita|
The Turn of the Screw|Henry James
In Search of Lost Time|Marcel Proust
The Lady with the Dog|Anton Chekhov
Childe Roland to the Dark Tower Came|Robert Browning
Ode to the West Wind|Percy Bysshe Shelley
The Necessity of Atheism|Percy Bysshe Shelley
Poetry|Emily Dickinson
Poetry|John Keats
Civilization and Its Discontents|Sigmund Freud
History|Ralph Waldo Emerson
How to Read a Book|Mortimer J. Adler
The Bible|'''
for line in extra.splitlines():
    t,a=line.split('|');allrows.append(dict(title=t,author=a,group='Public lecture contents',note=URL,
      form='collection' if t in ['Poetry','Short Stories','The Bible','Neapolitan Quartet'] else 'book'))
# Collapse repeat appearances, retaining all source notes; do not turn every lecture into a different book.
unique={}
for r in allrows:
    title,authors=canonical(r);key=(titlekey(title),tuple(authors))
    if key in unique:unique[key]['note']+=' '+r['group']+'. '+r.get('note','')
    else:unique[key]=dict(r)
save('mcevoy-lectures-reviewed-rows.json',list(unique.values()))
prepare('mcevoy-lectures',list(unique.values()),URL,
    'Named works from the full public contents index plus dated annual archive. Repeated lectures collapse to one work. Generic poetry and story headings remain unspecified selections; no inferred merit positions or invented programme dates.',
    'Named novels, plays, poems, short stories and other readings in Hardcore Literature’s public lecture index and annual archive. Multiple lectures on a work count once. Author-level poetry and short-story selections have no prescribed edition. Paid lecture contents and unnamed reading assignments are not reproduced.')
