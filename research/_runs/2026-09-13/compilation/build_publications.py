"""Reproducible qualitative first-pass editorial order; no personal merit scores."""
import json,re,unicodedata
from pathlib import Path
P=Path(__file__).resolve().parent
D=json.loads((P/'candidate-pool.json').read_text());pool={r['key']:r for r in D['works']}
def norm(s):return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower())
bytitle={norm(r['title']):r['key'] for r in pool.values()}
def resolve(lines):
 out=[]
 for t in lines.strip().split('\n'):
  if not t.strip():continue
  k=bytitle.get(norm(t.strip()))
  if not k:raise ValueError(t)
  if k not in out:out.append(k)
 return out
standing_head=resolve('''
Don Quixote
Ulysses
War and Peace
In Search of Lost Time
The Brothers Karamazov
Iliad
The Republic
On the Origin of Species
The Tale of Genji
Middlemarch
One Hundred Years of Solitude
Critique of Pure Reason
Moby-Dick
Anna Karenina
Analects
Divine Comedy
The Odyssey
Nicomachean Ethics
Madame Bovary
Dream of the Red Chamber
The Second Sex
Essays
Pride and Prejudice
The Sound and the Fury
Beloved
A Treatise of Human Nature
Ethics
Philosophical Investigations
The Great Gatsby
Lolita
Crime and Punishment
The Souls of Black Folk
The Structure of Scientific Revolutions
Zhuangzi
The Trial
To the Lighthouse
The Magic Mountain
The Origins of Totalitarianism
Silent Spring
The Decameron
The Adventures of Huckleberry Finn
Things Fall Apart
The Muqaddimah
Daodejing
A Theory of Justice
The Human Condition
The Wretched of the Earth
Nineteen Eighty-Four
The Man Without Qualities
The General Theory of Employment, Interest and Money
The Fundamental Wisdom of the Middle Way
The Varieties of Religious Experience
Pedro Páramo
The Red and the Black
Wuthering Heights
Jane Eyre
Ficciones
Mrs Dalloway
The Master and Margarita
Invisible Man
If This Is a Man
The Education of Henry Adams
On Liberty
The Catcher in the Rye
Catch-22
Brave New World
Pale Fire
The Golden Notebook
Tristram Shandy
Dead Souls
Absalom, Absalom!
The Grapes of Wrath
The Tin Drum
Season of Migration to the North
Grande sertão: veredas
The Open Society and Its Enemies
A Passage to India
As I Lay Dying
Nostromo
The Doll
Black Skin, White Masks
Cairo Trilogy
Annihilation of Caste
The Making of the English Working Class
The Autobiography of Malcolm X
A Room of One's Own
The Power Broker
The Lord of the Rings
Gulliver's Travels
Great Expectations
Lolita
A Portrait of the Artist as a Young Man
The Stranger
Midnight's Children
Heart of Darkness
The Idiot
Demons
An Enquiry concerning Human Understanding
Meditations on First Philosophy
On the Genealogy of Morality
Mengzi
Xunzi
The Incoherence of the Philosophers
Theological-Political Treatise
The Way of the Bodhisattva
The Falling Sky
The Historian's Craft
Silencing the Past
'''.replace('The Odyssey','Odyssey').replace('The Adventures of Huckleberry Finn','Adventures of Huckleberry Finn').replace('The Muqaddimah','Muqaddimah'))
reading_head=resolve('''
The Brothers Karamazov
Middlemarch
War and Peace
Pride and Prejudice
One Hundred Years of Solitude
Beloved
Crime and Punishment
Anna Karenina
Things Fall Apart
Don Quixote
The Republic
Nineteen Eighty-Four
The Souls of Black Folk
Silent Spring
If This Is a Man
The Second Sex
Jane Eyre
The Great Gatsby
Pedro Páramo
The Stranger
On Liberty
The Autobiography of Malcolm X
A Room of One's Own
Season of Migration to the North
The Lord of the Rings
The Master and Margarita
The Trial
The Doll
Kokoro
Ficciones
The Human Condition
Annihilation of Caste
Essays
Zhuangzi
Analects
The Wretched of the Earth
Black Skin, White Masks
The Origins of Totalitarianism
The Tale of Genji
The Magic Mountain
Moby-Dick
Ulysses
In Search of Lost Time
The Count of Monte Cristo
The Grapes of Wrath
To the Lighthouse
Frankenstein
The Structure of Scientific Revolutions
The Power Broker
I Know Why the Caged Bird Sings
Notes of a Native Son
A Theory of Justice
On the Origin of Species
An Enquiry concerning Human Understanding
The Way of the Bodhisattva
Daodejing
Nicomachean Ethics
The Varieties of Religious Experience
The Fundamental Wisdom of the Middle Way
Epistemic Injustice
''')
# Reviewed extra priorities: global prose, nonfiction beyond the initial hundred and original 14.
extra=resolve('''
This Earth of Mankind
God’s Bits of Wood
History
Complete Stories
Kokoro
Jude the Obscure
Solaris
Worldmaking After Empire
Seven Interpretive Essays on Peruvian Reality
Why Read the Classics?
Narrative of the Life of Frederick Douglass, an American Slave
Epistemic Injustice
Sentimental Education
Buddenbrooks
The Sound of the Mountain
Children of Gebelawi
Independent People
Hunger
Blindness
The Book of Disquiet
Memoirs of Hadrian
Journey to the End of the Night
Berlin Alexanderplatz
Molloy, Malone Dies, The Unnamable
Love in the Time of Cholera
Zeno’s Conscience
Gargantua and Pantagruel
The Handmaid's Tale
Giovanni's Room
The Sea, The Sea
Rebecca
North and South
The Mill on the Floss
Persuasion
Bleak House
David Copperfield
East of Eden
Wide Sargasso Sea
The Portrait of a Lady
'''.replace('The Portrait of a Lady\n',''))
def unique(xs):return list(dict.fromkeys(xs))
# Lower section uses published board order as a transparent tie-break, not invented precision.
def source_sort(k):
 r=pool[k];ml=[p['position'] for p in r['source_positions'] if p['source_id']=='S02'];oc=[p['position'] for p in r['source_positions'] if p['source_id']=='S04']
 return (0,min(ml),r['title']) if ml else (1,min(oc),r['title']) if oc else (2,0,r['title'])
fiction=sorted([k for k,r in pool.items() if r['field']=='literature'],key=source_sort)
nonfiction=sorted([k for k,r in pool.items() if r['field']!='literature'],key=source_sort)
# Interleave the remaining pools for an all-subject selection, after the explicit comparative head.
tail=[]
for i in range(max(len(fiction),len(nonfiction))):
 if i<len(fiction):tail.append(fiction[i])
 if i<len(nonfiction):tail.append(nonfiction[i])
a=unique(standing_head+extra+tail)[:250]
# Literary fiction excludes verse, drama, nonfiction, and this pass's children's-only/primarily formula genre selections.
exclude=set(resolve('''
The Da Vinci Code
Atlas Shrugged
Harry Potter and the Sorcerer's Stone
Harry Potter and the Chamber of Secrets
Heidi
The Wizard of Oz
The Swiss Family Robinson
The Lion, the Witch, and the Wardrobe
The Wind in the Willows
Charlotte's Web
Pippi Longstocking
Pinocchio
Black Beauty
The Secret Garden
The Hobbit
The Godfather
'''))
l=[k for k in unique(standing_head+extra+fiction) if pool[k]['field']=='literature' and not pool[k].get('not_prose_fiction') and k not in exclude][:250]
n=[k for k in unique(standing_head+extra+nonfiction) if pool[k]['field']!='literature']
b=[k for k in n if pool[k]['field']=='philosophy']
receipts={r['key']:r['work_id'] for f in Path('research/catalog').glob('expansion-??-import-receipt.json') for r in json.load(open(f))['records']}
# Specific comparative judgments, explicitly editorial rather than attributed poll findings.
reading_notes={
 'Ulysses':'Retains a high place for its formal and linguistic rewards; its allusive density moves it below more immediately sustained narratives in this general-reader order.',
 'In Search of Lost Time':'Exceptional sustained introspection remains valuable; the length and recursive structure make it a larger commitment than the novels promoted here.',
 'The Brothers Karamazov':'Promoted for the combination of dramatic momentum, moral conflict and philosophical conversation; breadth of reward matters more here than formal priority.',
 'The Doll':'Promoted within this lens for its sustained social world and character experience. This does not restore its former unsupported Top-14 standing.',
 'Critique of Pure Reason':'Foundational standing exceeds its position as a general-reader recommendation: technical vocabulary and dependence on philosophical context make guidance especially valuable.',
 'Principia Mathematica':'Historical importance does not make the complete technical work a strong first choice for most readers today.',
 'Silent Spring':'Promoted for the continuing conjunction of scientific communication, environmental responsibility and public argument.',
 'Things Fall Apart':'Promoted for concentrated narrative force and the encounter between a particular social world and colonial disruption.',
 'On Liberty':'Promoted as a compact, still-contested argument about personal freedom and social power.',
 'Epistemic Injustice':'Promoted for the practical reach of its questions about testimony, credibility and unequal access to understanding.',
}
method='Qualitative editorial compilation from a 423-book comparison pool: the saved cross-tradition research, both Modern Library board lists, the Norwegian Book Clubs selection, OCLC holdings and Penguin reader suggestions. An explicit comparative head precedes a lower-confidence section, where published board ordering is a tie-break and other supported candidates follow. All-books interleaves fiction and nonfiction after the comparative head; this is an editorial breadth choice, not user weights or a numerical merit formula. Library holdings indicate circulation/reception, not excellence. The Norwegian table is unranked except its reported winner. Penguin display numbers are not vote ranks. Aggregators and their source lists are not independent votes. Adjacent positions remain revisable; no personal scores are assigned.'
for target,keys in [('books-all-time',a),('literature-all-time',l),('nonfiction-all-time',n),('philosophy-books-all-time',b)]:
 sources={r['source_id']:r for r in json.load(open('research/'+target+'/sources.json'))['sources']}
 missing=[pool[k]['title'] for k in keys if not set(pool[k]['evidence_ids'])&sources.keys()]
 if missing:print(target,'unsupported held',missing)
 keys=[k for k in keys if set(pool[k]['evidence_ids'])&sources.keys()]
 read=unique([k for k in reading_head if k in keys]+keys)
 records=[]
 for k in keys:
  r=pool[k];ids=[s for s in r['evidence_ids'] if s in sources]
  supports=[]
  for s in ids:
   positions=[p for p in r['source_positions'] if p['source_id']==s]
   if positions:supports += [f"{s} {p['list']} #{p['position']}" for p in positions]
   else:supports.append(s)
  prior=r.get('reviewed_reasons')
  standing=(prior[0]+' ' if prior else '')+'Inclusion evidence: '+', '.join(supports)+'. Placement is an editorial comparison within this expanded pool; list appearances alone do not establish an exact global rank.'
  reading=reading_notes.get(r['title']) or ((prior[1]+' ' if prior else '')+'This first pass retains its standing order relative to other books outside the explicitly promoted reading group; no independent reader-vote ranking is claimed.')
  caveat=(prior[2]+' ' if prior else '')+'Source scope and overlapping selections limit precision. Preferred English edition and media are pending where the catalog has no verified record.'
  record=dict(key=k,item_id=receipts[k],source_ids=ids,source_positions=[p for p in r['source_positions'] if p['source_id'] in ids],standing=standing,reading=reading,caveat=caveat,metadata_status='See catalog: verified existing media retained; missing edition/cover/portraits pending')
  if 'R049' in ids:record['supplementary_sources']=[{'source_id':'R049','title':'Norwegian Book Clubs poll — full factual table (same underlying source)','url':'https://en.wikipedia.org/wiki/Bokklubben_World_Library'}]
  records.append(record)
 out=dict(target=target,expected_revision=2,allow_expansion=True,allow_pending_metadata=True,version=3,published_on='2026-09-13',notice=f'{len(keys)}-book first-pass comparison. Two qualitative orders; no personal scores. Edition details, covers and author portraits are still being completed for newly added books. Lower placements are less closely compared and will be refined.',method=method,orders={lens:{'label':label,'description':desc,'keys':order} for lens,label,desc,order in [('standing','Critical standing / enduring influence','Comparative editorial standing across the saved pool; source scope and dependence are recorded.',keys),('reading','Reading value today','Selected promotions for present engagement, with explanations; other relative positions retain the standing order.',read)]},entries=records)
 p=Path('research')/target/'expanded-selection-v3.json';p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
 (P/(target+'-review.tsv')).write_text('standing\treading\ttitle\tauthors\n'+'\n'.join(f"{i+1}\t{read.index(k)+1}\t{pool[k]['title']}\t{'; '.join(pool[k]['authors'])}" for i,k in enumerate(keys))+'\n')
 print(target,len(keys))
