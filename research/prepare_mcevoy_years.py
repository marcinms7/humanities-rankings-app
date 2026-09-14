"""Reviewed annual memberships from dated public lecture titles, not merit ranks."""
from import_collection_repairs import *
from research.repair_collections import DOM
archive=json.loads((RUN/'mcevoy-archive.json').read_text())
# A public archive entry's date belongs to the lecture, not necessarily the planned reading start.
root=DOM(Path('/tmp/mcevoy-sitemap.html').read_text()).root
for section in root.find('section'):
    year=section.attrs.get('id','').removeprefix('year-')
    if year not in archive:continue
    archive[year]=[]
    for li in section.find('li'):
        for a in li.direct('a'):
            date=li.text().removesuffix(a.text())
            archive[year].append(dict(date=date,title=a.text(),url=a.attrs['href']))
save('mcevoy-archive.json',archive)

DATA={
2022:'''Wuthering Heights|Emily Brontë
Moby-Dick|Herman Melville|Moby Dick
Middlemarch|George Eliot
Blood Meridian|Cormac McCarthy
Clarissa|Samuel Richardson
Ulysses|James Joyce
Dracula|Bram Stoker
The Lost Stradivarius|John Meade Falkner
The Mystery of Edwin Drood|Charles Dickens
A Christmas Carol|Charles Dickens
The Republic|Plato|Plato's Republic
Swann's Way|Marcel Proust|Close Reading of Proust
The Road|Cormac McCarthy
The Anxiety of Influence|Harold Bloom
Book of Job||Book of Job
Book of Jonah||Book of Jonah
Sonnets|William Shakespeare|Sonnet
Hamlet|William Shakespeare
Macbeth|William Shakespeare
Romeo and Juliet|William Shakespeare
Othello|William Shakespeare
Antony and Cleopatra|William Shakespeare
A Midsummer Night's Dream|William Shakespeare
As You Like It|William Shakespeare
Much Ado About Nothing|William Shakespeare
Twelfth Night|William Shakespeare
The Winter's Tale|William Shakespeare
The Tempest|William Shakespeare''',
2023:'''War and Peace|Leo Tolstoy|War & Peace
The Brothers Karamazov|Fyodor Dostoevsky
Orlando|Virginia Woolf
The Lord of the Rings|J. R. R. Tolkien
The Count of Monte Cristo|Alexandre Dumas
Invisible Man|Ralph Ellison
Jane Eyre|Charlotte Brontë
Gravity's Rainbow|Thomas Pynchon
A Tale of Two Cities|Charles Dickens
Paradise Lost|John Milton
Prometheus Bound|Aeschylus
Hedda Gabler|Henrik Ibsen
The Importance of Being Earnest|Oscar Wilde
Faust|Johann Wolfgang von Goethe
How Much Land Does a Man Need?|Leo Tolstoy
The Moons of Jupiter|Alice Munro
Runaway|Alice Munro
The Bear Came Over the Mountain|Alice Munro
To Autumn|John Keats
If—|Rudyard Kipling|‘If’
Henry VI, Part 1|William Shakespeare|Henry VI: Parts One, Two & Three
Henry VI, Part 2|William Shakespeare|Henry VI: Parts One, Two & Three
Henry VI, Part 3|William Shakespeare|Henry VI: Parts One, Two & Three''',
2024:'''East of Eden|John Steinbeck
The Master and Margarita|Mikhail Bulgakov
Pride and Prejudice|Jane Austen
The Tale of Genji|Murasaki Shikibu
Infinite Jest|David Foster Wallace
Song of Solomon|Toni Morrison
Far from the Madding Crowd|Thomas Hardy
David Copperfield|Charles Dickens
Inferno|Dante Alighieri
Song of Myself|Walt Whitman
The Misanthrope|Molière
Tartuffe|Molière
The School for Wives|Molière
The Learned Ladies|Molière
The Metamorphosis|Franz Kafka
A Hunger Artist|Franz Kafka
In the Penal Colony|Franz Kafka
The Prince|Niccolò Machiavelli
Essays|Michel de Montaigne|Essays of Montaigne
Thus Spoke Zarathustra|Friedrich Nietzsche
The Interpretation of Dreams|Sigmund Freud''',
2025:'''One Hundred Years of Solitude|Gabriel García Márquez
Metamorphoses|Ovid
Madame Bovary|Gustave Flaubert
The Sound and the Fury|William Faulkner
The Canterbury Tales|Geoffrey Chaucer
Brave New World|Aldous Huxley
Nineteen Eighty-Four|George Orwell
Iliad|Homer
Odyssey|Homer
The Three Musketeers|Alexandre Dumas
Rebecca|Daphne du Maurier
Emma|Jane Austen
Strange Case of Dr Jekyll and Mr Hyde|Robert Louis Stevenson
Bleak House|Charles Dickens
A Christmas Carol|Charles Dickens''',
}

def matches(title,post):
    return norm(title) in norm(post)

allrows=[]
for year,tsv in DATA.items():
    posts=list(reversed(archive[str(year)]));rows=[]
    for line in tsv.splitlines():
        bits=line.split('|');title,author=bits[:2];needle=bits[2] if len(bits)>2 else title
        found=[(i,p) for i,p in enumerate(posts) if matches(needle,p['title'])]
        if not found:raise ValueError((year,line,'no public membership evidence'))
        i,p=found[0]
        rows.append(dict(title=title,author=author,group=f'{year} · {p["date"]} public archive',sort=i,
                         note=f'Dated lecture/reading evidence: {p["title"]}. {p["url"]}'))
    if year>=2023:
        for i,p in enumerate(posts):
            if 'Shakespeare Project' not in p['title'] or not ('Lecture' in p['title'] or 'Timon' in p['title']):continue
            title=re.split(r' \(',p['title'])[0]
            if any(t in title for t in ['How to','Reflections','Henry VI:']):continue
            title=title.removeprefix('The Tragedy of ').replace("Shakespeare's Sonnets",'Sonnets')
            title={'Lucrece':'The Rape of Lucrece','Henry IV, Part One':'Henry IV, Part 1','Henry IV, Part Two':'Henry IV, Part 2','Pericles, Prince of Tyre':'Pericles'}.get(title,title)
            rows.append(dict(title=title,author='William Shakespeare',group=f'{year} · {p["date"]} · Shakespeare project',sort=i,
                form='poem' if title in ['Sonnets','The Rape of Lucrece','Venus and Adonis'] else 'play',note=p['url']))
    rows.sort(key=lambda r:r['sort']);allrows.extend(rows)
    target=f'mcevoy-schedule-{year}'
    save(target+'-reviewed-rows.json',rows)
    prepare(target,rows,'https://www.patreon.com/hardcoreliterature/sitemap',
        f'Faithful {year} public archive membership, ordered by first visible dated occurrence. Includes big reads and named supporting plays, poems and stories. Dates are lecture dates, not reconstructed monthly assignments. Public sitemap starts February 2022; member-only syllabus contents were not read.',
        f'Books, plays and named shorter works covered in {year}, checked against Benjamin McEvoy’s dated public lecture archive. Includes supporting readings and the Shakespeare project. Order follows first visible archive mention, not literary merit. The archive does not disclose every member-only assignment.' + (' January archive coverage is incomplete.' if year==2022 else ''))
    p=RUN/(target+'-definition.json');d=json.loads(p.read_text());d.update(title=f'Hardcore Literature · {year} book-club readings',presentation='reading_sequence',status='public_archive_imported');p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
save('annual-reviewed-rows.json',allrows)
