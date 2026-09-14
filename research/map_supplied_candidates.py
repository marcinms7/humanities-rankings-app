"""Produce reviewable catalog/source matches; no database mutations."""
import os, sys, json, hashlib, re, unicodedata
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent; sys.path.insert(0,str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.config.settings')
import django; django.setup()
from backend.core.models import Work
P=ROOT/'research/_runs/2026-09-13/supplied-corpus'
def norm(s): return re.sub(r'\W+',' ',unicodedata.normalize('NFKD',s).casefold()).strip()
works=list(Work.objects.filter(is_archived=False).prefetch_related('authors'))
index=json.loads((P/'index.json').read_text())
for target, urls in index.items():
    candidates={}; audit=[]
    for url in urls:
        path=P/(hashlib.sha256(url.encode()).hexdigest()+'.json')
        if not path.exists(): continue
        result=json.loads(path.read_text()); content=result.get('text','')
        # Remove recurring navigation and focus Goodreads on the actual list.
        if 'goodreads.com/list/' in url and 'All Votes' in content: content=content.split('All Votes',1)[1].split('Related News',1)[0]
        body=' '+norm(content)+' '
        found=[]
        for w in works:
            title=norm(w.title); authors=[norm(a.name) for a in w.authors.all()]
            if len(title)<5: continue
            pos=body.find(' '+title+' ')
            if pos<0: continue
            nearby=body[max(0,pos-150):pos+len(title)+350]
            # Require author identification nearby for ambiguous short titles.
            if len(title.split())<3 and not any(a in nearby for a in authors): continue
            if not any(a in body for a in authors): continue
            candidates.setdefault(str(w.pk),{'id':w.pk,'title':w.title,'authors':[a.name for a in w.authors.all()],'field':w.field,'sources':[]})['sources'].append(url)
            found.append(w.pk)
        audit.append({'url':url,'matched_catalog_ids':found,'error':result.get('error'),'readable_characters':len(content)})
    rows=sorted(candidates.values(),key=lambda r:(-len(r['sources']),r['title']))
    (P/f'{target}-candidates.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
    (P/f'{target}-audit.json').write_text(json.dumps(audit,indent=2))
    print(target,len(audit),'pages',len(rows),'candidates')
    print([(r['title'],len(r['sources'])) for r in rows[:20]])
