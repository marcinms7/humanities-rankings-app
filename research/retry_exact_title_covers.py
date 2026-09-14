"""Conservative second pass for exact-title Open Library cover matches."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json, os, sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
ROOT=Path(__file__).resolve().parent.parent; sys.path.insert(0,str(ROOT))
from enrich_catalog_covers import CACHE, best_doc, load_cache, norm

def fetch(row):
    try:
        req=Request('https://openlibrary.org/search.json?'+urlencode({'title':row['title'],'limit':10,'fields':'*'}),headers={'User-Agent':'humanities-rankings-cover-enrichment/1.0'})
        with urlopen(req,timeout=6) as response: docs=json.loads(response.read()).get('docs',[])
        exact=[d for d in docs if norm(d.get('title',''))==norm(row['title']) and d.get('cover_i')]
        if len(exact)!=1: return row,None
        d=exact[0]; cid=d['cover_i']; req=Request(f'https://covers.openlibrary.org/b/id/{cid}-L.jpg?default=false',headers={'User-Agent':'humanities-rankings-cover-enrichment/1.0'})
        with urlopen(req,timeout=6) as response: image=response.read()
        row={**row,'status':'covered','cover_id':cid,'isbn':(d.get('isbn') or [''])[0],'publisher':(d.get('publisher') or [''])[0],'source_key':d.get('key')}; return row,image
    except Exception as error: return {**row,'status':'error','error':str(error)[:300]},None

def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.config.settings'); import django; django.setup()
    from django.core.files.base import ContentFile
    from backend.core.models import Edition,Work
    cache=load_cache(); rows=[r for r in cache.values() if r.get('status')=='no_match']; print('retrying',len(rows))
    with CACHE.open('a') as out, ThreadPoolExecutor(max_workers=12) as pool:
        for future in as_completed([pool.submit(fetch,r) for r in rows]):
            row,image=future.result()
            if image:
                work=Work.objects.get(pk=row['work_id']); edition=work.editions.filter(is_archived=False).first()
                if edition is None:
                    edition=Edition(work=work,language='English',publisher=row.get('publisher',''),isbn=row.get('isbn',''),source_url=f"https://openlibrary.org{row.get('source_key','')}"); edition.full_clean(); edition.save()
                edition.cover.save(f"openlibrary-{row['cover_id']}.jpg",ContentFile(image),save=False); edition.image_attribution=f"Open Library Covers API: https://covers.openlibrary.org/b/id/{row['cover_id']}-L.jpg"; edition.save(update_fields=['cover','image_attribution','updated_at']); row['edition_id']=edition.pk
            out.write(json.dumps(row,ensure_ascii=False)+'\n'); out.flush(); cache[str(row['work_id'])]=row
    print('covered',sum(1 for r in rows if r.get('status')=='covered'))
if __name__=='__main__': main()
