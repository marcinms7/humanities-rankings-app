"""Extract explicit Goodreads title/author rows for review, without writes to DB."""
import json,re,hashlib
from pathlib import Path
P=Path(__file__).resolve().parent/'_runs/2026-09-13/supplied-corpus'
index=json.loads((P/'index.json').read_text())
for target,urls in index.items():
    rows=[]
    for url in urls:
        if 'goodreads.com/list/' not in url: continue
        f=P/(hashlib.sha256(url.encode()).hexdigest()+'.json')
        if not f.exists(): continue
        text=json.loads(f.read_text()).get('text','')
        for rank,title,author in re.findall(r'(?m)^(\d+)\n([^\n]+)\nby\n([^\n]+)\n',text):
            author=author.replace(' (Goodreads Author)','').strip()
            rows.append({'title':title,'author':author,'source_rank':int(rank),'url':url})
    (P/f'{target}-explicit-rows.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
    unique=list(dict.fromkeys((r['title'],r['author']) for r in rows))
    print(target,len(rows),len(unique))
    (P/f'{target}-titles.txt').write_text('\n'.join(f'{i+1}. {t} | {a}' for i,(t,a) in enumerate(unique)))
