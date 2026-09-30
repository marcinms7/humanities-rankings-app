"""Apply reviewed report credits without collapsing series or ranked positions."""
import json, os, re, sys, hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.config.settings')
import django;django.setup()
from django.db import transaction
from django.utils import timezone
from backend.core.models import Work,Person,Ranking,RankingEntry,Edition
from backend.core.views import ensure_revision,save_revision
RUN=ROOT/'research/_runs/2026-09-28/completion'
CREDITS={1806:['Ian Shaw'],1807:[],1814:['Sarah B. Pomeroy'],1821:['Michael Loewe','Edward L. Shaughnessy'],1832:['Peregrine Horden','Nicholas Purcell'],1869:['John Baines','Jaromír Málek'],1870:['B. G. Trigger'],1879:['Bridget Allchin','Raymond Allchin'],1883:['Li Liu','Xingcan Chen'],1886:['Denis Twitchett','Michael Loewe'],1891:['Simon Price','Peter Thonemann'],1900:['John N. Miksic','Goh Geok Yian'],1901:['Robert J. Sharer','Loa P. Traxler'],2150:['Mary Beard','John North','Simon Price'],2161:['Peter Garnsey','Richard Saller'],2492:['James Campbell','Eric John','Patrick Wormald'],2522:['Nicholas J. Higham','Martin J. Ryan'],2543:['Eric Hobsbawm','George Rudé']}
EDITORS={1806,1821,1886}
plan=json.loads((RUN/'column-reversal-plan.json').read_text())['skipped']
apply='--apply' in sys.argv
count=0
for row in plan:
 wid=row['work_id']
 if wid not in CREDITS:continue
 line=row['line'];left,title=re.split(r'\s+[—–]\s+',re.sub(r'^\s*\d+[.)]\s+','',line),maxsplit=1)
 title=re.sub(r'\s*\(\d{4}\)\s*$','',title)
 if wid==1807:title='The Cambridge Ancient History'
 w=Work.objects.get(pk=wid)
 if w.title==title and (sorted(w.authors.values_list('name',flat=True))==sorted(CREDITS[wid]) or (wid!=1807 and set(CREDITS[wid]).issubset(set(w.authors.values_list('name',flat=True))))):continue
 if w.title!=left:raise RuntimeError(f'Identity changed since reviewed report: {wid}')
 paths=list((ROOT/'research/incoming').glob('*/2026-09-13-owner-paste/report.txt'))
 source=next(p for p in paths if line in p.read_text())
 note=('Edited by ' if wid in EDITORS else 'Contributors: ')+', '.join(CREDITS[wid])+'.'
 if wid in {1814,1870}:note+=' The supplied report abbreviates the remaining author credits as et al.; edition-specific full credits still require verification.'
 if wid==1807:note='Multivolume edited series with different contributors for each volume. Select a specific volume/edition before recording a page total.'
 receipt={'work_id':wid,'title':title,'contributors':CREDITS[wid],'roles':'editors' if wid in EDITORS else 'authors','before_title':w.title,'before_authors':list(w.authors.values_list('name',flat=True)),'before_description':w.description,'source':str(source.relative_to(ROOT)),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'raw_line':line,'note':note}
 if apply:
  with transaction.atomic():
   w=Work.objects.select_for_update().get(pk=wid)
   assert w.title==receipt['before_title']
   rankings=list(Ranking.objects.select_for_update().filter(entries__work=w).exclude(origin='personal').distinct())
   for r in rankings:ensure_revision(r)
   people=[]
   for name in CREDITS[wid]:
    found=list(Person.objects.filter(name=name,is_archived=False))
    if len(found)>1:raise RuntimeError(f'Ambiguous existing person: {name}')
    people.append(found[0] if found else Person.objects.create(name=name))
   old=list(w.authors.all());w.authors.set(people)
   w.title=title;w.description=f'Included in the owner-supplied synthesis. Credits corrected from its preserved report on 28 September 2026. {note}'
   w.save(update_fields=['title','description','updated_at'])
   for p in old:
    if not p.works.exists() and not RankingEntry.objects.filter(person=p).exists():p.is_archived=True;p.save(update_fields=['is_archived','updated_at'])
   for r in rankings:
    r.scope.setdefault('identity_repairs',[]).append({'work_id':wid,'source':receipt['source'],'sha256':receipt['sha256'],'contributors':CREDITS[wid],'note':note})
    save_revision(r,f'Corrected report contributor fields for work {wid}; positions retained')
   # Add an exact bibliographic option; preserve any existing default/reading choices.
   if wid in {1806,1879}:
    isbn='9780198150343' if wid==1806 else '052128550X'
    url='https://academic.oup.com/book/47196' if wid==1806 else 'https://doi.org/10.1017/S0003581500066695'
    edition,created=Edition.objects.get_or_create(work=w,isbn=isbn,defaults={'language':'English','publisher':'Oxford University Press' if wid==1806 else 'Cambridge University Press','source_url':url,'pages':None if wid==1806 else 379,'pages_basis':'unknown' if wid==1806 else 'isbn_matched','pages_source_url':'' if wid==1806 else url,'translation_notes':('2000 print edition; edited by Ian Shaw. Page count not independently rechecked.' if wid==1806 else '1982 paperback. Bibliographic review header records xiv preliminary pages plus 379 numbered pages; reading count uses numbered pages.')})
    if not w.default_edition_id:w.default_edition=edition;w.save(update_fields=['default_edition','updated_at'])
    receipt['edition_id']=edition.pk
   receipt['saved_at']=timezone.now().isoformat()
  with (RUN/'contributor-repair-receipts.jsonl').open('a') as f:f.write(json.dumps(receipt,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
 count+=1
 print(json.dumps({'id':wid,'title':title,'contributors':CREDITS[wid],'applied':apply},ensure_ascii=False),flush=True)
print(json.dumps({'reviewed':count,'applied':apply}))
