import json,re,unicodedata,os,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()));os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.config.settings')
import django;django.setup()
from backend.core.models import Work,Person
P=Path(__file__).resolve().parent
sources={s['source_id']:s for s in json.load(open('research/philosophy-books-all-time/sources.json'))['sources']}
def norm(s):return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower())
# These exact authored works occur in the examined S03 curriculum. Aliases are normalized explicitly.
data='''
Metaphysics|Aristotle
Politics|Aristotle
Physics|Aristotle
Poetics|Aristotle
On the Soul|Aristotle
Categories|Aristotle
On Interpretation|Aristotle
Prior Analytics|Aristotle
On Generation and Corruption|Aristotle
Meno|Plato
Gorgias|Plato
Apology|Plato
Crito|Plato
Phaedo|Plato
Symposium|Plato
Parmenides|Plato
Theaetetus|Plato
Sophist|Plato
Timaeus|Plato
Phaedrus|Plato
On the Nature of Things|Lucretius
Proslogion|Anselm of Canterbury
Summa Theologiae|Thomas Aquinas
Confessions|Augustine of Hippo
Novum Organum|Francis Bacon
Essays|Michel de Montaigne
Discourse on the Method|René Descartes
Rules for the Direction of the Mind|René Descartes
Discourses|Epictetus
Enchiridion|Epictetus
The Prince|Niccolò Machiavelli
Discourses on Livy|Niccolò Machiavelli
The Guide for the Perplexed|Maimonides
The Enneads|Plotinus
Maxims|François de La Rochefoucauld
Leviathan|Thomas Hobbes
Groundwork of the Metaphysics of Morals|Immanuel Kant
Monadology|Gottfried Wilhelm Leibniz
Discourse on Metaphysics|Gottfried Wilhelm Leibniz
Second Treatise of Government|John Locke
Pensées|Blaise Pascal
The Social Contract|Jean-Jacques Rousseau
Discourse on the Origin of Inequality|Jean-Jacques Rousseau
The Wealth of Nations|Adam Smith
Democracy in America|Alexis de Tocqueville
Beyond the Pleasure Principle|Sigmund Freud
Phenomenology of Spirit|G. W. F. Hegel
Introduction to Metaphysics|Martin Heidegger
The Crisis of European Sciences and Transcendental Phenomenology|Edmund Husserl
Philosophical Fragments|Søren Kierkegaard
Fear and Trembling|Søren Kierkegaard
Capital|Karl Marx
Economic and Philosophic Manuscripts of 1844|Karl Marx
Beyond Good and Evil|Friedrich Nietzsche
The German Ideology|Karl Marx;Friedrich Engels
The Correspondence Between Princess Elisabeth of Bohemia and René Descartes|Elisabeth of Bohemia;René Descartes
'''
rows=[(line.split('|')[0],line.split('|')[1].split(';'),'S03') for line in data.strip().splitlines()]
# Existing saved critical reviews name these works, not new source discoveries.
for line in '''
On What Matters|Derek Parfit|R033
Reasons and Persons|Derek Parfit|R033
Death and the Afterlife|Samuel Scheffler|R035
Creating Capabilities|Martha Nussbaum|R036
Women and Human Development|Martha Nussbaum|R036
Frontiers of Justice|Martha Nussbaum|R036
Justice for Hedgehogs|Ronald Dworkin|R037
Democracy After Virtue|Sungmoon Kim|R038
Ethics in the Conflicts of Modernity|Alasdair MacIntyre|R039
After Virtue|Alasdair MacIntyre|R039
Ethics and the Limits of Philosophy|Bernard Williams|R039
Socrates and Orunmila|Sophie Bósèdé Olúwọlé|R040
Out of the Dark Night|Achille Mbembe|R045
Philosophy and an African Culture|Kwasi Wiredu|R072
Cultural Universals and Particulars|Kwasi Wiredu|R072
Hayy ibn Yaqzan|Ibn Tufayl|R078
Freedom: An Impossible Reality|Raymond Tallis|R147
Being Human|Rowan Williams|R149
Philosophers of Nothingness|James W. Heisig|R152
Discipline and Punish|Michel Foucault|R197
'''.strip().splitlines():
 t,a,s=line.split('|');rows.append((t,[a],s))
canon={norm(p.name):p.name for p in Person.objects.filter(is_archived=False)}
works=[]
for t,authors,s in rows:
 authors=[canon.get(norm(a),a) for a in authors];key=norm(t)+'-'+norm(authors[0])
 works.append(dict(key=key,title=t,authors=authors,form='book',field='philosophy',original_year=None,original_language='',countries=[],description='',work_source_url=sources[s]['canonical_url'],evidence_ids=[s],edition=None,english_availability_note='Named in the English-language curriculum or the saved review of an English-available work; preferred complete edition, translator, pages and media remain pending. Short independently published treatises/dialogues are distinguished from anthology excerpts.'))
Path('research/catalog/philosophy-expansion-01.json').write_text(json.dumps({'schema_version':1,'consulted_on':'2026-09-13','allow_pending_editions':True,'works':works},ensure_ascii=False,indent=2)+'\n')
print(len(works),'philosophy work records prepared')
