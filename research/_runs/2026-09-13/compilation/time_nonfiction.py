"""Factual TIME selection metadata from the consulted S22 reprint; unranked."""
import json,re,unicodedata,os,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()));os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.config.settings')
import django;django.setup()
from backend.core.models import Person
rows='''
Dreams from My Father|Barack Obama
A Heartbreaking Work of Staggering Genius|Dave Eggers
I Know Why the Caged Bird Sings|Maya Angelou
Manchild in the Promised Land|Claude Brown
Maus|Art Spiegelman
A Moveable Feast|Ernest Hemingway
On Writing|Stephen King
A Walk in the Woods|Bill Bryson
Capitalism and Freedom|Milton Friedman
Fast Food Nation|Eric Schlosser
How to Win Friends and Influence People|Dale Carnegie
No Logo|Naomi Klein
Unsafe at Any Speed|Ralph Nader
What Color Is Your Parachute?|Richard Nelson Bolles
The American Cinema|Andrew Sarris
A Child of the Century|Ben Hecht
Within the Context of No Context|George W. S. Trow
Mystery Train|Greil Marcus
The Story of Art|E. H. Gombrich
Against Interpretation and Other Essays|Susan Sontag
Slouching Towards Bethlehem|Joan Didion
A Supposedly Fun Thing I'll Never Do Again|David Foster Wallace
How to Cook a Wolf|M. F. K. Fisher
The Omnivore's Dilemma|Michael Pollan
And the Band Played On|Randy Shilts
The Common Sense Book of Baby and Child Care|Benjamin Spock
The Joy of Sex|Alex Comfort
The Best and the Brightest|David Halberstam
Bury My Heart at Wounded Knee|Dee Brown
Carry Me Home|Diane McWhorter
The Fatal Shore|Robert Hughes
A People's History of the United States|Howard Zinn
The Rise and Fall of the Third Reich|William L. Shirer
The Closing of the American Mind|Allan Bloom
The End of History and the Last Man|Francis Fukuyama
Gödel, Escher, Bach|Douglas Hofstadter
The Hero with a Thousand Faces|Joseph Campbell
Imagined Communities|Benedict Anderson
Orientalism|Edward Said
Syntactic Structures|Noam Chomsky
Understanding Media|Marshall McLuhan
Zen and the Art of Motorcycle Maintenance|Robert M. Pirsig
The Electric Kool-Aid Acid Test|Tom Wolfe
The Executioner's Song|Norman Mailer
All the President's Men|Bob Woodward;Carl Bernstein
The Clash of Civilizations and the Remaking of World Order|Samuel P. Huntington
The Conscience of a Conservative|Barry Goldwater
God and Man at Yale|William F. Buckley Jr.
What It Takes|Richard Ben Cramer
A Brief History of Time|Stephen Hawking
Coming of Age in Samoa|Margaret Mead
The Emperor of All Maladies|Siddhartha Mukherjee
The Naked Ape|Desmond Morris
On Human Nature|Edward O. Wilson
The Selfish Gene|Richard Dawkins
The American Way of Death|Jessica Mitford
Animal Liberation|Peter Singer
The Beauty Myth|Naomi Wolf
The Death and Life of Great American Cities|Jane Jacobs
The Feminine Mystique|Betty Friedan
Guns, Germs, and Steel|Jared Diamond
Nickel and Dimed|Barbara Ehrenreich
The Other America|Michael Harrington
Ball Four|Jim Bouton
Dispatches|Michael Herr
Hiroshima|John Hersey
The Looming Tower|Lawrence Wright
'''
def norm(s):return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower())
canon={norm(p.name):p.name for p in Person.objects.all()};works=[]
url='https://s-usih.org/2011/08/all-time-100-best-non-fiction-books/'
for line in rows.strip().splitlines():
 t,a=line.split('|');authors=[canon.get(norm(x),x) for x in a.split(';')];works.append(dict(key=norm(t)+'-'+norm(authors[0]),title=t,authors=authors,form='book',field='nonfiction',original_year=None,original_language='English',countries=[],description='',evidence_ids=['S22'],work_source_url=url,edition=None,english_availability_note='English-language TIME nonfiction selection since 1923, examined in the S22 reprint. Work identity only: edition, pagination and images pending.'))
Path('research/catalog/nonfiction-expansion-01.json').write_text(json.dumps({'schema_version':1,'consulted_on':'2026-09-13','allow_pending_editions':True,'works':works},ensure_ascii=False,indent=2)+'\n')
Path('research/_runs/2026-09-13/compilation/S22-time.json').write_text(json.dumps({'source_id':'S22','url':url,'consulted_on':'2026-09-13','method':'Unranked TIME 100 nonfiction selection, English since 1923; 67 explicit candidate rows transcribed for expansion. Other entries already extracted through Modern Library or held for ambiguous collective/series identities. Reprint is the same TIME selection, not an independent vote. Ignore injected advertising text.','entries':[{'title':w['title'],'authors':w['authors'],'position':None} for w in works]},ensure_ascii=False,indent=2)+'\n')
print(len(works))
