"""1990 contents reconciled against the source's 60-volume table."""
from import_collection_repairs import *
raw=json.loads((RUN/'greatbooks-raw.json').read_text())
old={int(k):v for k,v in raw['1952'].items()}; changes={int(k):v for k,v in raw['1990_changes'].items()}
# Volume correspondence verified against the complete 1990 contents table.
mapping={1:[2],2:[3],3:[4],4:[5],5:[6],6:[7],7:[8],8:[9],9:[10],10:[11],11:[12,17],12:[13],13:[14],14:[15],15:[16],
16:[18],17:[19],18:[20],19:[21,22],20:[],21:[23],22:[24],23:[25],24:[26],25:[27],26:[28],27:[29],28:[30,31],
29:[32],30:[33],31:[],32:[34],33:[35],34:[36],35:[38],36:[39],37:[40],38:[41],39:[42],40:[43],41:[44],42:[45],
43:[46],44:[],45:[47],46:[],47:[],48:[48],49:[49],50:[50],51:[51],52:[52],53:[53],54:[54],55:[],56:[],57:[],58:[],59:[],60:[]}
replace={3,4,11,12,16,19,20,23,27,31,44,45,46,47,55,56,57,58,59,60}
rows=[]
for volume in range(1,61):
    base=[dict(r) for v in mapping[volume] for r in old[v]]
    if volume in replace: base=[dict(r) for r in changes[volume]]
    elif volume in changes: base += [dict(r) for r in changes[volume]]
    for r in base:
        if r['title'] in ['On Conic Sections','The Life and Opinions of Tristram Shandy, Gentleman','Analytical Theory of Heat']: continue
        r['group']=f'1990 second edition · Volume {volume}'
        if volume in [1,2]:
            r.update(title=f'The Syntopicon: An Index to the Great Ideas, Volume {volume}',author='Mortimer J. Adler',form='collection',field='nonfiction',
                     note='Reference/index volume edited by Mortimer J. Adler; not a separate literary merit selection.')
        if volume==15 and r['author'].startswith('Johannes Kepler'):
            r['note']='Included excerpt: Books IV–V.' if r['title'].startswith('Epitome') else 'Included excerpt: Book V.'
        if volume==50 and r['title']=='Capital':r['note']='Volume I only.'
        if volume==59 and r['author']=='Marcel Proust':
            r.update(title='Swann in Love',note='Only Swann in Love from Swann’s Way is included, not all of In Search of Lost Time.',source_note='Swann in Love (from Remembrance of Things Past)')
        if volume==58:r['note']='Selections only.' if r['author']!='Johan Huizinga' else ''
        if volume==56 and r['title']=='Atomic Theory and the Description of Nature':r['note']='Selections only.'
        # Avoid turning contextual labels for Milton's poem into nameless works.
        if r['title']=='Another on the same':r['title']='Another on the Same (On the University Carrier)'
        if r['author']=='John Milton' and r.get('part_of')=='English Minor Poems':r['form']='poem'
        a=re.split(r' \(',r['author'])[0]
        if a in ['Aeschylus','Sophocles','Euripides','Aristophanes','William Shakespeare','Molière','Jean Racine','Henrik Ibsen']:r['form']='play'
        if a in ['Plato','Aristotle','Epictetus','Marcus Aurelius','Plotinus','Thomas Aquinas','Immanuel Kant','René Descartes','Benedict de Spinoza']:r['field']='philosophy'
        rows.append(r)
save('greatbooks-1990-reviewed-rows.json',rows)
prepare('great-books-western-world',rows,'https://en.wikipedia.org/wiki/Great_Books_of_the_Western_World',
    '1990 second edition, all 60 volumes. Wikipedia nested work contents reconciled with https://www.bopsecrets.org/gateway/book-lists/greatbooks.htm. Removed first-edition-only works; retained volume membership and excerpt limitations. Repeated works spanning volumes share one entry with both notes. Volume order is not merit order.',
    'Contents of the 1990 second edition (60 volumes), including the two Syntopicon reference volumes. Works follow volume order, with individual plays, dialogues and named essays shown separately. Multi-volume works share one entry; selected excerpts are identified in the notes. This is an unranked collection.')
p=RUN/'great-books-western-world-definition.json';d=json.loads(p.read_text());d['title']='Great Books of the Western World · 1990 edition';p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
