import os,sys,json,re,unicodedata
from pathlib import Path
sys.path.insert(0,str(Path.cwd()));os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.config.settings')
import django;django.setup()
from backend.core.models import Work,Ranking
T='nonfiction-all-time';old=json.load(open(f'research/{T}/expanded-selection-v4.json'));records={r['item_id']:r for r in old['entries']}
# Include all supported nonfiction candidates, not only those that happened to fit the preceding philosophy-heavy pass.
ledger={s['source_id']:s for s in json.load(open(f'research/{T}/sources.json'))['sources']}
for f in ['nonfiction-expansion-01','nonfiction-rebalance-01']:
 batch=json.load(open(f'research/catalog/{f}.json'));receipt={r['key']:r['work_id'] for r in json.load(open(f'research/catalog/{f}-import-receipt.json'))['records']}
 for r in batch['works']:
  i=receipt[r['key']]
  if i in records:
   records[i]['source_ids']=list(dict.fromkeys(records[i]['source_ids']+r['evidence_ids']));records[i]['source_positions']+=r.get('source_positions',[]);continue
  sid=r['evidence_ids'][0];records[i]=dict(key=r['key'],item_id=i,source_ids=r['evidence_ids'],source_positions=r.get('source_positions',[]),standing=f'Included through {sid}: '+('reader reception across a Chinese-language platform' if sid=='R203' else 'French-language member ratings' if sid=='R205' else 'a reader selection and its critical discussion' if sid=='R204' else 'a broad nonfiction editorial selection')+'. Placement here is an editorial synthesis, not a source rank transferred into the all-time list.',reading='Offers a different nonfiction encounter—history, life-writing, science, culture, society or practical inquiry. Position reflects the broad reading-value comparison; no claim that every factual or practical conclusion is endorsed.',caveat='Source scope, reader self-selection and contested claims remain relevant. Exact English edition, cover and author portrait are pending. A dated work can be important without being current guidance.',metadata_status='edition_and_media_pending')
works={i:Work.objects.get(pk=i) for i in records}
def norm(s):return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower())
# Normalize accidental punctuation variants to one work identity in this ranking.
groups={}
for i,w in works.items(): groups.setdefault((norm(w.title), tuple(sorted(norm(a.name) for a in w.authors.all()))), []).append(i)
for duplicate_ids in groups.values():
 if len(duplicate_ids)>1:
  keep=min(duplicate_ids)
  for duplicate in duplicate_ids:
   if duplicate==keep:continue
   records[keep]['source_ids']=list(dict.fromkeys(records[keep]['source_ids']+records[duplicate]['source_ids']))
   records[keep]['source_positions']+=records[duplicate].get('source_positions',[])
   records.pop(duplicate);works.pop(duplicate)
lookup={norm(w.title):i for i,w in works.items()}
def ids(text):
 out=[]
 for t in text.strip().split('\n'):
  if norm(t) not in lookup:raise ValueError(t)
  if lookup[norm(t)] not in out:out.append(lookup[norm(t)])
 return out
head=ids('''
On the Origin of Species
The Power Broker
The Souls of Black Folk
The History of the Decline and Fall of the Roman Empire
Silent Spring
The Second Sex
The Structure of Scientific Revolutions
If This Is a Man
The Making of the English Working Class
Muqaddimah
The Autobiography of Malcolm X
The General Theory of Employment, Interest and Money
The Republic
The Origins of Totalitarianism
The Education of Henry Adams
The Death and Life of Great American Cities
Hiroshima
Essays
The Wealth of Nations
Orientalism
Democracy in America
The Double Helix
A Room of One's Own
The Emperor of All Maladies
The Guns of August
The Warmth of Other Suns
Imagined Communities
The Story of Art
The Feminine Mystique
Secondhand Time
The Interesting Narrative of the Life of Olaudah Equiano
Maus
The Selfish Gene
The Immortal Life of Henrietta Lacks
The Wretched of the Earth
The Civil War
Black Boy
Notes of a Native Son
Deng Xiaoping and the Transformation of China
From the Soil
The Historian's Craft
The Falling Sky
A Theory of Justice
The Sixth Extinction
The Year of Magical Thinking
A Brief History of Time
Bury My Heart at Wounded Knee
The Rise and Fall of the Third Reich
The Right Stuff
The Omnivore's Dilemma
The Mismeasure of Man
Gödel, Escher, Bach
The Gene
London Labour and the London Poor
Testament of Youth
The Road to Wigan Pier
The Lives of a Cell
Awakenings
The Art of Memory
The Hero with a Thousand Faces
The Uses of Literacy: Aspects of Working-Class Life
Thinking, Fast and Slow
The Demon-Haunted World
The American Cinema
Mystery Train
A Book of Mediterranean Food
The Sweet Science
The Elements of Style
Working
The American Way of Death
The Natural History and Antiquities of Selborne
The Anatomy of Melancholy
The Diary of Samuel Pepys
The Life of Samuel Johnson
The Autobiography of Benjamin Franklin
Personal Memoirs
The Human Race
1587, A Year of No Significance
Stories of the Sahara
River Town
''')
# This is a one-edition breadth correction, not a permanent user weight or scoring criterion.
phil=[i for i in list(dict.fromkeys(head+list(records))) if works[i].field=='philosophy'][:35]
nonphil=[i for i in list(dict.fromkeys(head+list(records))) if works[i].field!='philosophy'][:215]
selected=set(phil+nonphil);standing=[i for i in list(dict.fromkeys(head+list(records))) if i in selected]
assert len(standing)==250,(len(phil),len(nonphil))
reading_head=ids('''
If This Is a Man
The Souls of Black Folk
Silent Spring
The Autobiography of Malcolm X
The Warmth of Other Suns
The Immortal Life of Henrietta Lacks
Hiroshima
The Emperor of All Maladies
The Power Broker
Maus
Secondhand Time
The Year of Magical Thinking
The Story of Art
A Room of One's Own
The Second Sex
The Death and Life of Great American Cities
The Sixth Extinction
The Right Stuff
The Republic
The Demon-Haunted World
From the Soil
Stories of the Sahara
River Town
Deng Xiaoping and the Transformation of China
The Gene
The Omnivore's Dilemma
Testament of Youth
Notes of a Native Son
A Brief History of Time
Bury My Heart at Wounded Knee
''')
reading=list(dict.fromkeys([i for i in reading_head if i in selected]+standing))
for i in selected:
 r=records[i]
 if i in head:r['standing']='Placed in the comparative opening to represent nonfiction across history, life-writing, science, economics, society, arts and philosophy. Evidence: '+', '.join(r['source_ids'])+'. This is an editorial ordering; neither academic attention nor a single list determines its exact position.'
 r['reading']=('Promoted for a sustained encounter with its subject in the broad nonfiction reading group. ' if i in reading_head else 'Retains its relative standing outside the promoted reading group. ')+'Reader recommendations inform this view, alongside clarity, narrative engagement and the value of the questions raised; these are qualitative explanations, not agreed numerical criteria.'
oldids={r['item_id'] for r in old['entries']};removed=oldids-selected
out={**old,'expected_revision':4,'version':5,'notice':'250 nonfiction books across history, memoir, biography, science, society, economics, arts, travel, reference and philosophy. Rebalanced after the earlier philosophy-heavy edition. Covers, portraits and edition details remain pending for new catalog records.','method':'Broad nonfiction synthesis, rebalanced after owner review. Individual philosophical articles no longer dominate membership or the opening order. Consulted editorial lists, Chinese Douban and French SensCritique reader rankings, and a Reddit selection with dissent inform inclusion alongside existing criticism. The current selection contains 35 catalog-classified philosophy works and 215 other nonfiction works; this is an editorial breadth correction, not a permanent quota or a personal scoring weight. Source limitations and different source ordering methods remain explicit. Academic sources support interpretation rather than supplying extra popularity votes.','entries':[records[i] for i in standing],'reviewed_exclusions':[{'item_id':i,'reason':'Removed from this edition of broad nonfiction to correct over-concentration on specialized philosophy; catalog, philosophy ranking membership where present, evidence and earlier nonfiction revisions are preserved.'} for i in sorted(removed)],'orders':{lens:{**old['orders'][lens],'keys':[records[i]['key'] for i in order]} for lens,order in [('standing',standing),('reading',reading)]}}
Path(f'research/{T}/expanded-selection-v5.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
Path('research/_runs/2026-09-13/compilation/nonfiction-rebalance-review.tsv').write_text('standing\treading\ttitle\tfield\n'+'\n'.join(f'{n+1}\t{reading.index(i)+1}\t{works[i].title}\t{works[i].field}' for n,i in enumerate(standing))+'\n')
print('Prepared 250, philosophy',len(phil),'other',len(nonphil),'archived previous entries',len(removed))
