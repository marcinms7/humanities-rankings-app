import os,sys,json,re,unicodedata
from pathlib import Path
sys.path.insert(0,str(Path.cwd()));os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.config.settings')
import django;django.setup()
from backend.core.models import Person,Work
P=Path(__file__).resolve().parent
def norm(s):return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower())
canon={norm(p.name):p.name for p in Person.objects.all()}
AA={'Dr Benjamin Spock':'Benjamin Spock','Dr Peter Mark Roget':'Peter Mark Roget','RW Emerson':'Ralph Waldo Emerson','Tom Paine':'Thomas Paine','Ulysses S Grant':'Ulysses S. Grant','John Aubrey, edited by Andrew Clark':'John Aubrey','‘Publius’':'Alexander Hamilton;James Madison;John Jay','Sir Thomas Browne':'Thomas Browne','William Strunk and EB White':'William Strunk Jr.;E. B. White'}
TA={'Against Interpretation':'Against Interpretation and Other Essays','Black Boy: A Record of Childhood and Youth':'Black Boy','The Life of Samuel Johnson LLD':'The Life of Samuel Johnson','The Wonderful Adventures of Mrs Seacole in Many Lands':'Wonderful Adventures of Mrs Seacole in Many Lands'}
exclude={4,11,17,29,46,58,69,73,88,91,97} # verse, drama, satire, ambiguous collection/liturgy identity
rows=[]
for r in json.load(open(P/'R202-guardian.json'))['entries']:
 if r['number'] not in exclude:rows.append((TA.get(r['title'],r['title']),AA.get(r['author'],r['author']).split(';'),'R202',None))
for line in '''
Deng Xiaoping and the Transformation of China|Ezra F. Vogel|R203|13
Stories of the Sahara|Sanmao|R203|18
From the Soil|Fei Xiaotong|R203|34
Sapiens|Yuval Noah Harari|R203|36
River Town|Peter Hessler|R203|44
1587, A Year of No Significance|Ray Huang|R203|47
Secondhand Time|Svetlana Alexievich|R205|7
The Human Race|Robert Antelme|R205|15
Thinking, Fast and Slow|Daniel Kahneman|R204|
Influence|Robert B. Cialdini|R204|
The Righteous Mind|Jonathan Haidt|R204|
Flow|Mihaly Csikszentmihalyi|R204|
The Gene|Siddhartha Mukherjee|R204|
Chaos|James Gleick|R204|
The Demon-Haunted World|Carl Sagan|R204|
The Warmth of Other Suns|Isabel Wilkerson|R204|
The Immortal Life of Henrietta Lacks|Rebecca Skloot|R204|
Why Nations Fail|Daron Acemoglu;James A. Robinson|R204|
Liar's Poker|Michael Lewis|R204|
The Innovator's Dilemma|Clayton M. Christensen|R204|
'''.strip().splitlines():
 t,a,s,pos=line.split('|');rows.append((t,a.split(';'),s,int(pos) if pos else None))
sources={s['source_id']:s for s in json.load(open('research/nonfiction-all-time/sources.json'))['sources']}
works=[]
for t,a,s,pos in rows:
 a=[canon.get(norm(x),x) for x in a];k=norm(t)+'-'+norm(a[0]);works.append(dict(key=k,title=t,authors=a,form='book',field='nonfiction',original_year=None,original_language='',countries=[],description='',evidence_ids=[s],work_source_url=sources[s]['canonical_url'],source_positions=[{'source_id':s,'position':pos,'list':'reader_ratings'}] if pos else [],edition=None,english_availability_note='English work title or established English translation identified in consulted list/bibliographic lookup. Exact edition, translation choice, pagination and images pending.'))
Path('research/catalog/nonfiction-rebalance-01.json').write_text(json.dumps({'schema_version':1,'consulted_on':'2026-09-13','allow_pending_editions':True,'works':works},ensure_ascii=False,indent=2)+'\n')
print(len(works))
