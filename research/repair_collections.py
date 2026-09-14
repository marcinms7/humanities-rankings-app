"""Reviewed collection repair helpers. No database writes on import."""
import json, re, unicodedata
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / 'research/_runs/2026-09-13/collection-repair'
RUN.mkdir(parents=True, exist_ok=True)

class Node:
    def __init__(self, tag='', attrs=(), parent=None):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs), parent, []
    def text(self, omit=()):
        return re.sub(r'\s+', ' ', ''.join(c if isinstance(c,str) else '' if c.tag in omit else c.text(omit) for c in self.children)).strip()
    def find(self, tag):
        for c in self.children:
            if isinstance(c,Node):
                if c.tag == tag: yield c
                yield from c.find(tag)
    def direct(self, tag):
        return [c for c in self.children if isinstance(c,Node) and c.tag == tag]

class DOM(HTMLParser):
    def __init__(self, source):
        super().__init__(); self.root=Node(); self.cur=self.root; self.feed(source)
    def handle_starttag(self, tag, attrs):
        n=Node(tag,attrs,self.cur); self.cur.children.append(n)
        if tag not in {'br','hr','img','meta','link','input','source','wbr','area','base','embed','param','col'}: self.cur=n
    def handle_endtag(self, tag):
        n=self.cur
        while n.parent and n.tag != tag: n=n.parent
        if n.parent: self.cur=n.parent
    def handle_data(self,data): self.cur.children.append(data)

def save(name,data):
    (RUN/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')

def norm(s):
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower())

def mcevoy():
    source=Path('/tmp/mcevoy.html').read_text()
    rows=[]
    sections=re.split(r'<h2[^>]*>',source)
    for section in sections:
        h=DOM(section.split('</h2>')[0]).root.text()
        if 'Year Reading List:' not in h: continue
        ul=next(DOM(section.split('</h2>',1)[1]).root.find('ul'))
        for li in ul.direct('li'):
            author=li.text(omit=('ul',)).rstrip(':').strip()
            children=li.direct('ul')
            if children:
                for item in children[0].direct('li'):
                    rows.append(dict(title=item.text(),author=author,group=h.rstrip(':')))
            else:
                rows.append(dict(title=author,author='',group=h.rstrip(':')))
    save('mcevoy-reading-raw.json',rows)
    return rows

def greatbooks():
    root=DOM(Path('/tmp/gbww.html').read_text()).root
    out={'1952':{},'1990_changes':{}}
    for s in root.find('section'):
        key=s.attrs.get('aria-labelledby','')
        if not key.startswith('Volume_'): continue
        edition='1990_changes' if s.parent.attrs.get('aria-labelledby')=='Second_edition' else '1952'
        number=int(key.split('_')[1]); rows=[]
        for ul in s.direct('ul'):
            for authorli in ul.direct('li'):
                author=authorli.text(omit=('ul',))
                nested=authorli.direct('ul')
                if not nested:
                    rows.append(dict(title=author,author='',group=f'Volume {number}')); continue
                def leaves(ul, parent=''):
                    for li in ul.direct('li'):
                        italic=li.direct('i')
                        title=italic[0].text() if italic else li.text(omit=('ul',))
                        if li.direct('ul'):
                            yield from leaves(li.direct('ul')[0], title)
                        else:
                            yield dict(title=title,author=author,group=f'Volume {number}',source_note=li.text(),part_of=parent)
                rows.extend(leaves(nested[0]))
        out[edition][number]=rows
    save('greatbooks-raw.json',out)
    print({e:{v:len(r) for v,r in volumes.items()} for e,volumes in out.items()})
    return out

if __name__=='__main__':
    print('McEvoy',len(mcevoy())); greatbooks()
