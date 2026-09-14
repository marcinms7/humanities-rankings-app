"""Build reviewable catalog/publication inputs from the supplied corpus.

Explicit row ranges were reviewed for scope; no catalog writes occur here.
"""
import os,sys,json,re,hashlib,unicodedata
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.config.settings')
import django;django.setup()
from backend.core.models import Work,Ranking
P=ROOT/'research/_runs/2026-09-13/supplied-corpus'
def norm(s):return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().casefold())
def base(s):return norm(re.split(r':|\s+\(',s)[0]).removeprefix('the')
def canon(url):return url.rstrip('/').replace('http://','https://')
history_exclude={11,14,31,47,52,65,66,69,71,100,103,104,105,108,112,116,122,127,128,141,142,145,155,159,160,162,171,175,176,181,193,202,205,212,216,217,218,219,222,223,224,233,236,240,256,259,260,269,273,283,285}
poetry_exclude={27,37,44,45,48,51,55,60,61,76,84,93,94,96,103,107,108,112,116,118,125,126,128,130,135,139,147,148,150,158,160,162,164,166,168,169,173,175,179,185}
philosophy_indices={2,6,10,18,21,25,29,31,32,33,35,37,38,39,41,44,48,49,56,59,61,63,64,68,69,70,74,75,76,77,81,85,90,98,99,102,104,108,110,111,114,115,118,121,122,125,131,132,133,134,135,138,139,140,143,145,147,148,153,154,155,156,157,158,159,160,161,163,164,165,167,168,169,170,171,172,173,174,175,176,177,178,183,189,191,196,198,200,202,203,205,206,208,212,213,214,216,217,218,220,226,228,229,231,233,235,236,238,239,242,244,245,247,249,250,251,252,259,269,276,279,280,281,283,287,293,298,305,307,308,312,313,314,316,320,322,324,329,332,333,335,340,352,355,359,360,362,364,370,377,380,381,383,384,389,390,391,392,394,397,400,402,403,405,406,408,410,412,414,417,423,424,426,438,440,445,448,452,455,459,466,475,490}
indices={'history-books-all-time':set(range(1,285))-history_exclude,'poetry-all-time':(set(range(1,189))-poetry_exclude)|{191,195,196,203,206,209,211,212,215,216,218,232,235,244},'philosophy-books-all-time':philosophy_indices}
indices['philosophy-books-all-time'] -= {154,157,160,163,164,168,170,173,174}
works=list(Work.objects.filter(is_archived=False).prefetch_related('authors'))
catalog=[]; selections={}
def resolve(title,author):
    au=norm(author)
    candidates=[w for w in works if base(w.title)==base(title) and any(norm(a.name)==au or (norm(a.name).endswith(au) or au.endswith(norm(a.name))) for a in w.authors.all())]
    return min(candidates,key=lambda w:w.pk) if candidates else None

for target,chosen in indices.items():
    rows=json.loads((P/f'{target}-explicit-rows.json').read_text()); unique={}
    for row in rows:unique.setdefault((row['title'],row['author']),row)
    selected=[]
    for i,row in enumerate(unique.values(),1):
        if i not in chosen:continue
        author=re.sub(r'\s*\((?:Editor|editor|Translator|Original Author).*?\)','',row['author']).strip()
        if author in {'Unknown','Anonymous'}:continue
        title=re.sub(r'\s*\([^)]*#\d[^)]*\)','',row['title']).strip()
        w=resolve(title,author); key=hashlib.sha256((base(title)+'|'+norm(author)).encode()).hexdigest()[:20]
        selected.append({**row,'title':title,'author':author,'key':key,'item_id':w.pk if w else None})
        if not w and key not in {r['key'] for r in catalog}:
            catalog.append({'key':key,'title':title[:300],'authors':[author],'form':'collection' if target=='poetry-all-time' else 'book','field':'literature' if target=='poetry-all-time' else 'philosophy' if target=='philosophy-books-all-time' else 'nonfiction','original_year':None,'original_language':'','countries':[],'description':'','work_source_url':row['url'],'evidence_ids':['OWNER-LIST-EXTRACTION'],'edition':None,'english_availability_note':'English-language book record in the extracted reader list; specific edition and completeness remain pending.'})
    selections[target]=selected
(P/'reviewed-catalog.json').write_text(json.dumps({'schema_version':1,'allow_pending_editions':True,'works':catalog},ensure_ascii=False,indent=2))
(P/'reviewed-additions.json').write_text(json.dumps(selections,ensure_ascii=False,indent=2))
print('New catalog records',len(catalog));print({k:len(v) for k,v in selections.items()})
