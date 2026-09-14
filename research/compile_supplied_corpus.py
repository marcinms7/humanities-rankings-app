"""Fetch the owner corpus resumably; retain readable text for selection review."""
import concurrent.futures, hashlib, json, re, time
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'research/_runs/2026-09-13/supplied-corpus'
TARGETS = ['books-all-time', 'philosophy-books-all-time', 'history-books-all-time', 'poetry-all-time', 'nonfiction-all-time']

class Text(HTMLParser):
    def __init__(self):
        super().__init__(); self.skip=0; self.parts=[]
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style','noscript','svg'): self.skip+=1
        if tag in ('p','li','h1','h2','h3','tr','article','div'): self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script','style','noscript','svg'): self.skip=max(0,self.skip-1)
    def handle_data(self, value):
        if not self.skip: self.parts.append(value+' ')

def fetch(url):
    path=OUT/(hashlib.sha256(url.encode()).hexdigest()+'.json')
    if path.exists(): return json.loads(path.read_text())
    result={'url':url}
    try:
        with urlopen(Request(url,headers={'User-Agent':'Marginalia research source extraction/1.0'}),timeout=15) as response:
            raw=response.read(2500000); result['resolved_url']=response.url
            parser=Text(); parser.feed(raw.decode('utf-8','replace'))
            result['text']='\n'.join(re.sub(r'\s+',' ',line).strip() for line in ''.join(parser.parts).splitlines() if line.strip())
            result['bytes']=len(raw)
    except Exception as error: result['error']=str(error)
    path.write_text(json.dumps(result,ensure_ascii=False))
    return result

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    index={t:json.loads((ROOT/f'research/incoming/{t}/2026-09-13-owner-paste/source-leads.json').read_text())['urls'] for t in TARGETS}
    (OUT/'index.json').write_text(json.dumps(index,indent=2))
    urls=list(dict.fromkeys(url for values in index.values() for url in values))
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for i,result in enumerate(pool.map(fetch,urls),1):
            if i%25==0: print(f'{i}/{len(urls)} saved',flush=True)
