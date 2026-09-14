import json,re,unicodedata,html
from pathlib import Path
P=Path('research/_runs/2026-09-13/compilation')
def norm(s):return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower())
def title(s):
 s=s.title() if s.isupper() else s
 return re.sub(r'\b(The|Of|And|To|In|A|An|For|With|By|At|On)\b',lambda m:m[0].lower(),s)[0].upper()+re.sub(r'\b(The|Of|And|To|In|A|An|For|With|By|At|On)\b',lambda m:m[0].lower(),s)[1:]
TA={norm(a):b for a,b in [
('Republic','The Republic'),('Moby Dick','Moby-Dick'),('1984','Nineteen Eighty-Four'),('The Adventures of Huckleberry Finn','Adventures of Huckleberry Finn'),('The Hobbit, or, There and Back Again','The Hobbit'),('Frankenstein, or, the Modern Prometheus','Frankenstein'),('Madame Bovary: Patterns of Provincial Life','Madame Bovary'),('The Red & the Black','The Red and the Black'),('Le Père Goriot','Père Goriot'),('The Devil to Pay in the Backlands','Grande sertão: veredas'),('The Trilogy: Molloy, Malone Dies, The Unnamable','Molloy, Malone Dies, The Unnamable'),('Bodhicaryāvatāra / The Way of the Bodhisattva','The Way of the Bodhisattva'),('U.S.A.(trilogy)','U.S.A. Trilogy'),('A Dance to the Music of Time (series)','A Dance to the Music of Time'),('Confessions of Zeno',"Zeno’s Conscience"),('The General Theory of Employment, Interest, and Money','The General Theory of Employment, Interest and Money'),('The Studs Lonigan Trilogy','Studs Lonigan'),('An Enquiry concerning Human Understanding','An Enquiry concerning Human Understanding')]}
AA={norm(a):b for a,b in [('Fyodor Dostoyevsky','Fyodor Dostoevsky'),('Ivan Sergeevich Turgenev','Ivan Turgenev'),('Boris Leonidovich Pasternak','Boris Pasternak'),('Arthur Schlesinger by Jr.','Arthur M. Schlesinger Jr.'),('Robert A. Caro','Robert Caro'),('Isak Dinesen','Karen Blixen'),('Bert Hoelldoebler','Bert Hölldobler'),('Bert Hoelldobler','Bert Hölldobler'),('Ernest H. Gombrich','E. H. Gombrich'),('Gunnar Myrdal','Gunnar Myrdal'),('Traditionally attributed to Homer','Homer'),('Cao Xueqin; continuation attribution disputed','Cao Xueqin'),('Confucius and subsequent transmitters','Confucius'),('Zhuang Zhou and later contributors','Zhuangzi'),('Traditionally attributed to Laozi','Laozi'),('Mencius and subsequent compilers','Mencius'),('Xun Kuang and subsequent editors','Xunzi'),('James D. Watson','James D. Watson'),('Davi Kopenawa and Bruce Albert','Davi Kopenawa|Bruce Albert'),('Alfred North Whitehead and Bertrand Russell','Alfred North Whitehead|Bertrand Russell'),('William Strunk and E. B. White','William Strunk Jr.|E. B. White'),('Bert Hoelldobler and Edward O. Wilson','Bert Hölldobler|Edward O. Wilson'),('Alex Haley and Malcolm X','Alex Haley|Malcolm X')]}
pool={}; oldkeys={}
def add(t,a,field,sid,pos=None,series=None,key=None,lang='',reasons=None):
 t=TA.get(norm(t),title(t));a=AA.get(norm(a),a); names=a.split('|');k=norm(t)+'-'+norm(names[0]);
 if k not in pool:pool[k]={'key':k,'title':t,'authors':names,'form':'book','field':field,'original_year':None,'original_language':lang,'countries':[],'description':'','evidence_ids':[],'source_positions':[],'english_availability_note':'Listed under this English title in the consulted reading/ranking sources; preferred edition, translator and pagination remain to be verified.'}
 r=pool[k]
 for src in sid.split():
  if src not in r['evidence_ids']:r['evidence_ids'].append(src)
 if pos is not None:r['source_positions'].append({'source_id':sid,'list':series,'position':pos})
 if key:oldkeys[key]=k
 if reasons:r['reviewed_reasons']=reasons
 return k
# Pilot identities first, preserving intentional spellings.
for i,r in enumerate(json.load(open('research/_runs/2026-09-12/draft-candidate-input.json'))['works']):
 add(r[1],r[2],'literature' if i<25 or r[0]=='iliad' else ('philosophy' if 25<=i<50 else 'nonfiction'),r[3],key=r[0],reasons=r[4:])
# Keep proper display names from current reviewed catalog.
for path in Path('research/catalog').glob('batch-0[123].json'):
 for r in json.load(open(path))['works']:
  k=oldkeys[r['key']];pool[k].update({f:r[f] for f in ['title','authors','original_language','original_year','countries','description','field']})
for r in json.load(open(P/'S02-modern-library.json'))['entries']:
 add(r['title'],r['author'],'literature' if r['list']=='novels' else 'nonfiction','S02',r['position'],r['list'],lang='English')
# Exclude constituent volumes where whole Lord of the Rings will be used; no double counting.
excluded=[]
for r in json.load(open(P/'S04-oclc.json'))['entries']:
 if r['position'] in [24,48,59,94]:
  excluded.append({'source_id':'S04',**r,'reason':'Constituent volume or ambiguous collected-text identity; retain extraction, do not create a duplicate/unspecified work.'});continue
 add(r['title'],r['author'],'literature','S04',r['position'],'library_holdings')
# World poll has no 1–100 ordering except Quixote being overall winner.
ambiguous={'Fairy Tales','Epic of Gilgamesh','Book of Job','One Thousand and One Nights',"Njál's Saga",'Poems','Stories','Complete Poems','Tales','The Death of Ivan Ilyich and Other Stories','Diary of a Madman and Other Stories'}
plays={'Medea','Faust',"A Doll's House",'Shakuntala','Hamlet','King Lear','Othello','Oedipus the King'}
poetry={'Divine Comedy','The Canterbury Tales','Gypsy Ballads','Iliad','Odyssey','Metamorphoses','Masnavi','Bostan','Ramayana','Aeneid','Mahabharata','Leaves of Grass'}
for t,a,y,c,l in json.load(open(P/'bokklubben-extraction.json')):
 if t in ambiguous or t in plays:
  excluded.append({'source_id':'R049','title':t,'reason':'Ambiguous anthology/anonymous attribution or separate play scope; retained for follow-up.'});continue
 k=add(t,a,'nonfiction' if t=='Essays' else 'literature','R049',lang=l)
 pool[k]['not_prose_fiction']=t in poetry or t=='Essays'
# Reconsulted aggregator visible top25: extra reception evidence, never an independent vote alongside its inputs.
for rank,t,a in [(18,'The Brothers Karamazov','Fyodor Dostoevsky'),(17,'The Lord of the Rings','J. R. R. Tolkien')]:add(t,a,'literature','S28',rank,'aggregate_books')
AA.update({norm('Miguel Cervantes'):'Miguel de Cervantes',norm('Somerset Maugham'):'W. Somerset Maugham',norm('George Grossmith and Weedon Grossmith'):'George Grossmith|Weedon Grossmith'})
TA[norm('The Iliad')]='Iliad'
for r in json.load(open(P/'S14-penguin.json'))['entries']:
 t=r['title'];field='nonfiction' if t in ['The Art of War','In Cold Blood','Travels with Charley','I Know Why the Caged Bird Sings','Lark Rise to Candleford'] else 'literature'
 k=add(t,r['author'],field,'S14')
 if t=='The Iliad':pool[k]['not_prose_fiction']=True
# Reconcile punctuation/initial spacing and existing author names across inputs.
canon={norm(a):a for p in pool.values() for a in p['authors']}
for path in Path('research/catalog').glob('batch-0[123].json'):
 for r in json.load(open(path))['works']:
  for a in r['authors']:canon[norm(a)]=a
import os,sys
sys.path.insert(0,str(Path.cwd()));os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.config.settings')
import django;django.setup()
from backend.core.models import Person
for person in Person.objects.all():canon[norm(person.name)]=person.name
for p in pool.values():p['authors']=[canon[norm(a)] for a in p['authors']]
# Fold duplicate keys after display aliases, keeping all evidence.
merged={};remap={}
for k,r in pool.items():
 nk=norm(r['title'])+'-'+norm(r['authors'][0]);remap[k]=nk
 if nk in merged:
  merged[nk]['evidence_ids']=list(dict.fromkeys(merged[nk]['evidence_ids']+r['evidence_ids']));merged[nk]['source_positions']+=r['source_positions']
 else:r['key']=nk;merged[nk]=r
pool=merged;oldkeys={k:remap[v] for k,v in oldkeys.items()}
for r in pool.values():
 # Qualifying texts of systematic philosophy within the nonfiction list.
 if r['title'] in ['The Varieties of Religious Experience','A Theory of Justice','Principia Mathematica','Principia Ethica','Philosophy and Civilization','The Open Society and Its Enemies','The Proper Study of Mankind']:r['field']='philosophy'
(P/'candidate-pool.json').write_text(json.dumps({'consulted_on':'2026-09-13','oldkeys':oldkeys,'works':list(pool.values()),'exclusions':excluded},ensure_ascii=False,indent=2))
print('Pool',len(pool),'fields', {f:sum(r['field']==f for r in pool.values()) for f in ['literature','nonfiction','philosophy']})
