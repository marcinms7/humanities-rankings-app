import os,sys,json,re,unicodedata
from pathlib import Path
sys.path.insert(0,str(Path.cwd()));os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.config.settings')
import django;django.setup()
from backend.core.models import Work,Person,Ranking
P=Path(__file__).resolve().parent
def norm(s):return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower())
base=json.load(open('research/philosophy-books-all-time/expanded-selection-v3.json'))
records={r['item_id']:r for r in base['entries']}
a=json.load(open('research/books-all-time/expanded-selection-v3.json'))
souls=next(r for r in a['entries'] if r['item_id']==10)
# Shared book is intentionally also philosophy; don't infer membership solely from catalog field.
bs={s.source_id for s in Ranking.objects.get(slug='philosophy-books-all-time').sources.all()}
souls={**souls,'source_ids':[s for s in souls['source_ids'] if s in bs]};records[10]=souls
cat=json.load(open('research/catalog/philosophy-expansion-01.json'))['works'];rc={r['key']:r['work_id'] for r in json.load(open('research/catalog/philosophy-expansion-01-import-receipt.json'))['records']}
for r in cat:
 wid=rc[r['key']]
 records[wid]=dict(key=r['key'],item_id=wid,source_ids=r['evidence_ids'],source_positions=[],standing='Included through '+', '.join(r['evidence_ids'])+'. The position is a qualitative editorial comparison: curriculum inclusion supplies a candidate, not a merit rank; review evidence applies to the named work.',reading='Short dialogues and direct ethical or political arguments are promoted in the reading-value view; systematic and technical texts retain their value but may require preparation. Remaining relative positions follow standing, not a claimed reader poll.',caveat='English edition, pagination and images are pending. Curricula may teach excerpts; this entry denotes the authored work, not a claim that a selected extract is the complete book. Adjacent ranks remain revisable.',metadata_status='edition_and_media_pending')
bytitle={norm(Work.objects.get(pk=i).title):i for i in records}
def order_titles(text,mapping):
 out=[]
 for t in text.strip().split('\n'):
  i=mapping.get(norm(t))
  if not i:raise ValueError(t)
  if i not in out:out.append(i)
 return out
head=order_titles('''
The Republic
Critique of Pure Reason
Nicomachean Ethics
Metaphysics
Analects
Ethics
A Treatise of Human Nature
Philosophical Investigations
Phenomenology of Spirit
Leviathan
The Second Sex
The Social Contract
Zhuangzi
Meditations on First Philosophy
Groundwork of the Metaphysics of Morals
Politics
The Fundamental Wisdom of the Middle Way
The Enneads
Summa Theologiae
The Guide for the Perplexed
Confessions
Discourse on the Method
A Theory of Justice
On Liberty
Daodejing
Beyond Good and Evil
The Prince
Second Treatise of Government
Essays
The Human Condition
The Souls of Black Folk
On the Genealogy of Morality
Capital
Novum Organum
The Wealth of Nations
The Crisis of European Sciences and Transcendental Phenomenology
Fear and Trembling
Annihilation of Caste
Black Skin, White Masks
Mengzi
The Incoherence of the Philosophers
On the Nature of Things
Philosophy and an African Culture
Reasons and Persons
After Virtue
Discipline and Punish
''',bytitle)
standing=list(dict.fromkeys(head+list(records)))
reading=order_titles('''
The Republic
Nicomachean Ethics
On Liberty
An Enquiry concerning Human Understanding
The Second Sex
The Souls of Black Folk
Annihilation of Caste
Zhuangzi
Analects
The Human Condition
Symposium
Apology
Meditations on First Philosophy
Discourse on the Method
Essays
Enchiridion
Discourses
The Prince
The Social Contract
Fear and Trembling
After Virtue
Black Skin, White Masks
Philosophy and an African Culture
Creating Capabilities
Epistemic Injustice
A Theory of Justice
Reasons and Persons
''',bytitle)
reading=list(dict.fromkeys(reading+standing))
def save(target,recs,stand,read,revision,version,method):
 old=Ranking.objects.get(slug=target)
 assert old.revision==revision
 assert set(old.entries.filter(is_archived=False).values_list('work_id',flat=True)).issubset(stand)
 out=dict(target=target,expected_revision=revision,allow_expansion=True,allow_pending_metadata=True,version=version,published_on='2026-09-13',notice=f'{len(stand)}-book comparison with both editorial orders. Newly added books have pending editions, covers and author portraits. Further expansion and comparative refinement continue; no personal scores.',method=method,orders={lens:{'label':label,'description':desc,'keys':[recs[i]['key'] for i in ids]} for lens,label,desc,ids in [('standing','Critical standing / enduring influence','Qualitative editorial comparison, with target-local evidence and source limitations.',stand),('reading','Reading value today','Direct engagement and present usefulness inform selected promotions; remaining relative positions follow standing.',read)]},entries=[recs[i] for i in stand])
 path=Path('research')/target/f'expanded-selection-v{version}.json';path.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(target,len(stand))
method='Expanded philosophy compilation from saved specialist articles, critical reviews, a Great Books curriculum and the philosophical works on the Modern Library nonfiction list. The explicit comparative head places foundational arguments alongside non-Western traditions and modern revisions; later positions are less closely compared. Curriculum inclusion is not a source merit ranking, nor is board nonfiction position a specialist philosophy rank. The reading order promotes direct encounters with arguments and preserves other relative positions. Both are editorial judgments, not numeric personal scores. This remains short of the requested approximately 250 books; notably more Indian, Islamic, African, Chinese, analytic and continental works remain to add.'
save('philosophy-books-all-time',records,standing,reading,2,3,method)
# Nonfiction: keep the published 133 identities, add the philosophical corpus and TIME candidates.
old=json.load(open('research/nonfiction-all-time/expanded-selection-v3.json'));nr={r['item_id']:r for r in old['entries']};ns={s.source_id for s in Ranking.objects.get(slug='nonfiction-all-time').sources.all()}
for i,r in records.items():
 ids=[s for s in r['source_ids'] if s in ns]
 if ids:nr[i]={**r,'source_ids':ids}
for r in a['entries']:
 obj=Work.objects.get(pk=r['item_id']);ids=[s for s in r['source_ids'] if s in ns]
 if obj.field!='literature' and ids:nr.setdefault(obj.pk,{**r,'source_ids':ids,'supplementary_sources':[]})
time=json.load(open('research/catalog/nonfiction-expansion-01.json'))['works'];tr={r['key']:r['work_id'] for r in json.load(open('research/catalog/nonfiction-expansion-01-import-receipt.json'))['records']}
for r in time:
 i=tr[r['key']];nr.setdefault(i,dict(key=r['key'],item_id=i,source_ids=['S22'],source_positions=[],standing='Selected in the consulted TIME nonfiction list (S22), which supplies reception evidence within English-language books since 1923. Its position here is editorial, not a rank assigned by TIME.',reading='Included as a substantive reading option in its subject; this first pass retains its relative standing outside the explicitly promoted reading group. Historical claims and practical guidance should be read in their period context.',caveat='TIME is a scoped editorial selection, not global consensus. Inclusion does not endorse every factual, political or practical claim. Preferred edition and images are pending.',metadata_status='edition_and_media_pending'))
nt={norm(Work.objects.get(pk=i).title):i for i in nr}
nh=order_titles('''
On the Origin of Species
The Republic
Critique of Pure Reason
Nicomachean Ethics
The Second Sex
The Souls of Black Folk
Essays
Metaphysics
Analects
Leviathan
The Wealth of Nations
The General Theory of Employment, Interest and Money
The Structure of Scientific Revolutions
The Origins of Totalitarianism
Silent Spring
The Social Contract
A Treatise of Human Nature
Ethics
Philosophical Investigations
Phenomenology of Spirit
The Human Condition
The Wretched of the Earth
A Theory of Justice
The Education of Henry Adams
If This Is a Man
Muqaddimah
The Autobiography of Malcolm X
Democracy in America
Capital
The Varieties of Religious Experience
The Making of the English Working Class
The Power Broker
Orientalism
Imagined Communities
A Room of One's Own
The Death and Life of Great American Cities
The Feminine Mystique
Gödel, Escher, Bach
On Liberty
Confessions
The Guide for the Perplexed
Summa Theologiae
The Open Society and Its Enemies
Discipline and Punish
The Falling Sky
Annihilation of Caste
Black Skin, White Masks
Maus
Hiroshima
The Emperor of All Maladies
''',nt)
# Published identities always survive; remaining space uses reviewed new candidates.
mandatory=[r['item_id'] for r in old['entries']]
selected=list(dict.fromkeys(nh+mandatory))
for i in list(nr):
 if len(selected)>=250:break
 if i not in selected:selected.append(i)
assert len(selected)==250
nread=[i for i in reading if i in selected];nread=list(dict.fromkeys([nt[norm(t)] for t in ['If This Is a Man','The Souls of Black Folk','Silent Spring','The Second Sex','The Republic','The Autobiography of Malcolm X','Maus','Hiroshima','The Emperor of All Maladies','A Room of One\'s Own']]+nread+selected))
save('nonfiction-all-time',nr,selected,nread,3,4,'Qualitative synthesis of saved cross-subject research, the complete Modern Library nonfiction board list, philosophical works in the consulted curriculum and TIME nonfiction selections. Source orders remain separate and TIME/curriculum membership has no invented merit position. A comparative head precedes a less closely compared lower section; existing identities remain in the expanded selection. Coverage is still weighted toward Western philosophy and English-language twentieth-century nonfiction. Both orders are editorial and revisable; no numerical personal scores.')
