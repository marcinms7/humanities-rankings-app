"""Prepare reviewed named-list imports; resolve identities with author checks."""
import os, sys, json, re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from research.repair_collections import ROOT, RUN, norm, save
os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.config.settings')
import django
django.setup()
from backend.core.models import Work, Ranking

AUTHORS={
 'Saint Augustine':'Augustine of Hippo','Saint Thomas Aquinas':'Thomas Aquinas','Dante':'Dante Alighieri',
 'Chaucer':'Geoffrey Chaucer','Machiavelli':'Niccolò Machiavelli','Descartes':'René Descartes',
 'Shakespeare':'William Shakespeare','Cervantes':'Miguel de Cervantes','Montaigne':'Michel de Montaigne',
 'Michel Eyquem de Montaigne':'Michel de Montaigne','Thomas Hobbe':'Thomas Hobbes','Milton':'John Milton',
 'Moliere':'Molière','Newton':'Isaac Newton','Sir Isaac Newton':'Isaac Newton','Sir Francis Bacon':'Francis Bacon',
 'Rousseau':'Jean-Jacques Rousseau','Jean Jacques Rousseau':'Jean-Jacques Rousseau','Kant':'Immanuel Kant',
 'Mill':'John Stuart Mill','Kierkegaard':'Søren Kierkegaard','Nietzsche':'Friedrich Nietzsche',
 'Goethe':'Johann Wolfgang von Goethe','Balzac':'Honoré de Balzac','Tolstoy':'Leo Tolstoy','Count Leo Tolstoy':'Leo Tolstoy',
 'Dostoyevsky':'Fyodor Dostoevsky','Fyodor Mikhailovich Dostoevsky':'Fyodor Dostoevsky','Ibsen':'Henrik Ibsen',
 'Freud':'Sigmund Freud','Einstein':'Albert Einstein','Sir George Frazer':'James George Frazer','Sir James George Frazer':'James George Frazer',
 'Proust':'Marcel Proust','T.S. Eliot':'T. S. Eliot','Hemingway':'Ernest Hemingway','Faulkner':'William Faulkner',
 'P. Cornelius Tacitus':'Tacitus','Benedict de Spinoza':'Baruch Spinoza','Charles de Secondat, Baron de Montesquieu':'Montesquieu',
 'Antoine Laurent Lavoisier':'Antoine Lavoisier','Jean Baptiste Joseph Fourier':'Joseph Fourier',
 'Nicomachus of Gerasa':'Nicomachus','Erasmus':'Desiderius Erasmus',
}
TITLE_ALIASES={
 ('Aristotle','Ethics'):'Nicomachean Ethics',('Marcus Aurelius','The Meditations'):'Meditations',
 ('Herodotus','The History'):'The Histories',('Horace','Poetics'):'Ars Poetica',
 ('René Descartes','Discourse'):'Discourse on the Method',('William Shakespeare','Everything'):'The Complete Works of Shakespeare',
 ('Molière','Tartuff'):'Tartuffe',('Marcel Proust','In Remembrance of Things Past'):'In Search of Lost Time',
 ('Karl Marx','Manifesto (with Engels)'):'The Communist Manifesto',('Karl Marx','Das Kapital'):'Capital',
 ('Karl Marx and Friedrich Engels','Manifesto of the Communist Party'):'The Communist Manifesto',
 ('Albert Einstein','Relativity'):'Relativity: The Special and the General Theory',
 ('Sophocles','Oedipus the King'):'Oedipus Rex',('Euripides','Bacchae'):'The Bacchae',
 ('Aeschylus','Choephoroe'):'The Libation Bearers',('Aeschylus','Choephoroe (The Libation Bearers)'):'The Libation Bearers',
 ('Sophocles','The Trachiniae'):'Women of Trachis',('Euripides','Bacchantes'):'The Bacchae',
 ('Euripides','Heracles Mad'):'Heracles',('Aristophanes','Ecclesiazousae'):'The Assemblywomen',
 ('Aristophanes','The Poet and the Women'):'Thesmophoriazusae',('Euclid',"Euclid's Elements"):'Elements',
 ('Lucretius','The Way Things Are'):'On the Nature of Things',('Plotinus','The Six Enneads'):'Enneads',
 ('Miguel de Cervantes','The History of Don Quixote de la Mancha'):'Don Quixote',
 ('Herman Melville','Moby Dick; or, The Whale'):'Moby-Dick',
 ('Charles Darwin','The Origin of Species by Means of Natural Selection'):'On the Origin of Species',
 ('Charles Darwin','Origin of Species'):'On the Origin of Species',
 ('Adam Smith','An Inquiry into the Nature and Causes of the Wealth of Nations'):'The Wealth of Nations',
 ('Mark Twain','Huckleberry Finn'):'Adventures of Huckleberry Finn',
 ('Plutarch','The Lives of the Noble Grecians and Romans'):'Parallel Lives',
}

def canonical(row):
    a=re.split(r' \((?:translated|rendered)',row['author'])[0].strip()
    a=AUTHORS.get(a,a)
    t=re.split(r' \((?:translated|edited)',row['title'])[0].strip().strip('"').rstrip(',')
    t=TITLE_ALIASES.get((a,t),t)
    if a=='William Shakespeare':
        t={
          'The First Part of King Henry the Sixth':'Henry VI, Part 1','The Second Part of King Henry the Sixth':'Henry VI, Part 2',
          'The Third Part of King Henry the Sixth':'Henry VI, Part 3','The First Part of King Henry the Fourth':'Henry IV, Part 1',
          'The Second Part of King Henry the Fourth':'Henry IV, Part 2','The Tragedy of Richard the Third':'Richard III',
          'The Tragedy of King Richard the Second':'Richard II','The Life and Death of King John':'King John',
          'The Life of King Henry the Fifth':'Henry V','Twelfth Night; or, What You Will':'Twelfth Night',
          'The Tragedy of Hamlet, Prince of Denmark':'Hamlet','Othello, the Moor of Venice':'Othello',
          'Pericles, Prince of Tyre':'Pericles','The Famous History of the Life of King Henry the Eighth':'Henry VIII',
        }.get(t,t)
    authors=[a] if a else []
    if t=='The Communist Manifesto': authors=['Karl Marx','Friedrich Engels']
    if a=='Alexander Hamilton, James Madison, John Jay': authors=['Alexander Hamilton','James Madison','John Jay']
    if a=='American State Papers': authors=[]
    return t,authors

def titlekey(t):
    return norm(re.sub(r'^(?:the|an|a)\s+','',t,flags=re.I))

def prepare(target, rows, url, method, description=None):
    catalog=list(Work.objects.filter(is_archived=False).prefetch_related('authors'))
    additions={}; mapped=[]
    for i,row in enumerate(rows):
        t,authors=canonical(row)
        matches=[w for w in catalog if titlekey(w.title)==titlekey(t) and
                 {norm(AUTHORS.get(p.name,p.name)) for p in w.authors.all()}=={norm(a) for a in authors}]
        # Prefer the earliest established identity; duplicate catalog rows remain preserved.
        matches.sort(key=lambda w:(not bool(w.default_edition_id),w.pk))
        key=norm(t)+'-'+ '-'.join(norm(a) for a in authors)
        note=row['group']+'. '+row.get('note','')
        if row.get('source_note') and row['source_note']!=row['title']: note+=' Source scope: '+row['source_note']
        if row.get('part_of'): note+=' In '+row['part_of']+'.'
        mapped.append(dict(key=key,work_id=matches[0].pk if matches else None,note=note,source_title=row['title'],authors=authors))
        if not matches:
            additions[key]=dict(key=key,title=t,authors=authors,form=row.get('form','book'),field=row.get('field','literature'),original_year=None,
                original_language='',countries=[],description=row.get('description',''),work_source_url=url,evidence_ids=['COLLECTION-CONTENTS'],
                edition=None,english_availability_note='Title is listed in this English-language collection; specific edition and media remain unverified.')
    save(target+'-mapped.json',mapped)
    save(target+'-catalog.json',dict(schema_version=1,consulted_on='2026-09-13',allow_pending_editions=True,works=list(additions.values())))
    save(target+'-definition.json',dict(target=target,url=url,method=method,description=description))
    print(target,len(rows),'source rows;',len(additions),'catalog additions;',sum(not a['authors'] for a in additions.values()),'anonymous')

if __name__=='__main__':
    rows=json.loads((RUN/'mcevoy-reading-raw.json').read_text())
    for r in rows:
        if r['title'] in ['Treatises','Essays','Enquiry','Critiques','Selected Works','Selected Short Stories']:
            r['note']='Source uses this broad label; no particular edition or complete collected corpus is specified.'
            r['form']='collection'
    prepare('mcevoy-reading-list',rows,'https://benjaminmcevoy.com/reading-list/',
        'All 101 listed assignments, preserving five programme-year groups and source order. Author nesting corrected. Broad selections stay explicitly unspecified.',
        'Benjamin McEvoy’s five-year suggested reading programme. Year labels refer to programme stages, not book-club calendar years. Some assignments name an unspecified selection or collection.')
    fav=[('The Complete Works of Shakespeare','William Shakespeare'),('King Lear','William Shakespeare'),('Hamlet','William Shakespeare'),
         ('Nicomachean Ethics','Aristotle'),('The Bible',''),('Essays','Michel de Montaigne'),('The Short Stories of Chekhov','Anton Chekhov'),
         ('War and Peace','Leo Tolstoy'),('Moby-Dick','Herman Melville'),('Novels','Charles Dickens'),('Short Stories','Guy de Maupassant')]
    rows=[dict(title=t,author=a,group='Additional named favourite within Shakespeare’s works' if i in [1,2] else 'Additional desert-island choice' if i>=9 else 'Main favourites',
               form='collection' if i in [0,4,5,6,9,10] else 'book') for i,(t,a) in enumerate(fav)]
    prepare('mcevoy-favourites',rows,'https://benjaminmcevoy.com/reading-list/',
       'Seven main choices, two specifically highlighted Shakespeare plays, and two author collections from the closing paragraph. Generic poetry/art book wishes remain in the description, not invented book records.',
       'Seven main favourites, with King Lear and Hamlet highlighted within Shakespeare, plus Dickens’s novels and Maupassant’s short stories from the closing paragraph. McEvoy also wishes for an unspecified poetry anthology and art book. Unranked; collections overlap with individual works.')
