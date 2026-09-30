"""Resumable, credited portraits: exact Wikipedia identity + Wikidata human/P18.

A supplied name alone is insufficient: the article must mention a catalog work,
or identify a ranked philosopher as a philosopher. Historical depictions are
labelled as such; no generated or generic substitute counts as a portrait.
"""
import argparse, html, io, json, os, re, sys, time, unicodedata
from pathlib import Path
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research.enrichment_queue import Queue, exclusive, rotate
from research.operational_state import atomic_state, read_state
RUN=ROOT/'research/_runs/2026-09-28/portraits';LEDGER=RUN/'outcomes.jsonl'
COOLDOWN=RUN/'provider-cooldown.json'
HEADERS={'User-Agent':'Marginalia/1.0 (humanities catalog; credited portrait research)'}
LAST=0.
def norm(value):
    return ''.join(char for char in unicodedata.normalize('NFKD',str(value)).casefold() if char.isalnum())
def get_json(host,params):
    global LAST
    time.sleep(max(0,1-(time.monotonic()-LAST)));LAST=time.monotonic()
    url=host+'?'+urlencode({**params,'format':'json','formatversion':2,'maxlag':5})
    with urlopen(Request(url,headers=HEADERS),timeout=25) as r: data=json.load(r)
    if 'error' in data: raise ValueError(str(data['error']))
    return data

def picture(info):
    time.sleep(2)  # Respect Commons image request limits across this sequential batch.
    url=info.get('thumburl') or info['url']
    with urlopen(Request(url,headers=HEADERS),timeout=25) as r: blob=r.read(10*1024*1024+1)
    if len(blob)>10*1024*1024: raise ValueError('image exceeds 10 MB')
    with Image.open(io.BytesIO(blob)) as image:
        if min(image.size)<80 or max(image.size)/min(image.size)>5: raise ValueError('not a useful portrait image')
        if image.format not in ('JPEG','PNG','WEBP','GIF'): raise ValueError('unsupported raster format')
        ext={'JPEG':'jpg','PNG':'png','WEBP':'webp','GIF':'gif'}[image.format];image.verify()
    return blob,ext

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int,default=100);parser.add_argument('--retry',action='store_true');parser.add_argument('--person-id',type=int)
    args=parser.parse_args()
    if COOLDOWN.exists() and read_state(COOLDOWN, cooldown=True).get('until',0)>time.time():
        print('Portrait provider cooldown is active; no requests sent.',flush=True)
        return
    os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.config.settings')
    import django;django.setup()
    from django.db import transaction
    from django.db.models import Count,Q
    from django.core.files.base import ContentFile
    from backend.core.models import Person
    RUN.mkdir(parents=True,exist_ok=True);queue=Queue('portraits',LEDGER);rotate(LEDGER)
    people=Person.objects.filter(is_archived=False,portrait='').prefetch_related('works').annotate(ranked=Count('rankingentry',filter=Q(rankingentry__is_archived=False,rankingentry__ranking__is_archived=False),distinct=True)).order_by('-ranked','pk')
    if args.person_id: people=people.filter(pk=args.person_id)
    items=[]
    for person in people:
        works=[w.title for w in person.works.all() if not w.is_archived]
        item={'id':person.pk,'title':person.name,'authors':works,'ranked':bool(person.ranked)}
        if queue.due(item,'wikimedia-human-work-confirmed-v2',retry=args.retry):items.append(item)
        if args.limit and len(items)>=args.limit:break
    stats={'queued':len(items),'processed':0,'portraits':0};failures=0
    with LEDGER.open('a') as audit:
        def finish(item,record):
            record.update(work_id=item['id'],person_id=item['id'],name=item['title'])
            queue.finish(item,record,audit);finished_ids.add(item['id']);stats['processed']+=1
            atomic_state(RUN/'latest-stats.json', {**stats,**queue.summary()})
            print(json.dumps({k:v for k,v in record.items() if k in ('person_id','name','status','error')},ensure_ascii=False),flush=True)
        for start in range(0,len(items),20):
            batch=items[start:start+20]
            finished_ids=set()
            try:
                data=get_json('https://en.wikipedia.org/w/api.php',{'action':'query','titles':'|'.join(i['title'] for i in batch),'redirects':1,'prop':'extracts|pageprops|info','explaintext':1,'exintro':1,'exlimit':'max','inprop':'url'})['query']
                redirects={norm(r['from']):norm(r['to']) for r in data.get('redirects',[])+data.get('normalized',[])}
                pages={norm(p['title']):p for p in data.get('pages',[])}
                selected=[]
                for item in batch:
                    name=norm(item['title']);seen=set()
                    while name in redirects and name not in seen:seen.add(name);name=redirects[name]
                    page=pages.get(name,{})
                    props=page.get('pageprops',{})
                    if 'disambiguation' in props or not props.get('wikibase_item'):
                        finish(item,{'status':'no_unique_identity'});continue
                    extract=page.get('extract','');hay=norm(extract)
                    matches=[title for title in item['authors'] if len(norm(title))>=8 and norm(title) in hay]
                    philosopher=item['ranked'] and bool(re.search(r'\bphilosoph(?:er|y)\b',extract[:2500],re.I))
                    if not matches and not philosopher and item['authors']:
                        detail=get_json('https://en.wikipedia.org/w/api.php',{'action':'query','pageids':page['pageid'],'prop':'extracts','explaintext':1})
                        hay=norm(detail['query']['pages'][0].get('extract',''))
                        matches=[title for title in item['authors'] if len(norm(title))>=8 and norm(title) in hay]
                    if not matches and not philosopher:
                        finish(item,{'status':'identity_review','page_url':page.get('fullurl'),'reason':'No catalog work or ranked-philosopher identity corroboration'});continue
                    selected.append((item,page,matches))
                if not selected:continue
                entities={}
                # Cacheable entity documents avoid query-service lag dependencies.
                for qid in dict.fromkeys(p['pageprops']['wikibase_item'] for _,p,_ in selected):
                    with urlopen(Request('https://www.wikidata.org/wiki/Special:EntityData/'+qid+'.json',headers=HEADERS),timeout=25) as response:
                        entities.update(json.load(response)['entities'])
                    time.sleep(0.5)
                images=[]
                for item,page,matches in selected:
                    qid=page['pageprops']['wikibase_item'];claims=entities.get(qid,{}).get('claims',{})
                    human=any(c.get('mainsnak',{}).get('datavalue',{}).get('value',{}).get('id')=='Q5' for c in claims.get('P31',[]))
                    names=[c.get('mainsnak',{}).get('datavalue',{}).get('value') for c in claims.get('P18',[]) if c.get('rank')!='deprecated']
                    names=[n for n in names if isinstance(n,str)]
                    if not human or not names:
                        finish(item,{'status':'no_human_portrait' if human else 'identity_review','wikidata':qid});continue
                    images.append((item,page,matches,qid,names[0]))
                if not images:continue
                info=get_json('https://commons.wikimedia.org/w/api.php',{'action':'query','titles':'|'.join('File:'+n for *_,n in images),'prop':'imageinfo','iiprop':'url|mime|extmetadata','iiurlwidth':500})['query']['pages']
                files={norm(p['title'].removeprefix('File:')):p for p in info}
                for item,page,matches,qid,name in images:
                    metadata=files.get(norm(name),{}).get('imageinfo',[{}])[0]
                    ext=metadata.get('extmetadata',{})
                    record={'wikidata':qid,'page_url':page.get('fullurl'),'matched_works':matches,'file':name,'image_metadata':metadata}
                    if not metadata.get('url') or not ext.get('LicenseShortName',{}).get('value'):
                        finish(item,{**record,'status':'unresolved_image_credit'});continue
                    try:
                        blob,extension=picture(metadata)
                        source=metadata.get('descriptionurl') or 'https://commons.wikimedia.org/wiki/File:'+quote(name.replace(' ','_'))
                        artist=html.unescape(re.sub('<[^>]+>',' ',ext.get('Artist',{}).get('value',''))).strip()
                        license=ext['LicenseShortName']['value']
                        credit=f'Portrait / historical depiction. {artist[:110]} · {license[:65]} · {source}'
                        if len(credit)>500:credit=f'Portrait / historical depiction; full credit and license: {source}'[:500]
                        with transaction.atomic():
                            person=Person.objects.select_for_update().get(pk=item['id'])
                            if person.portrait or person.is_archived or person.name!=item['title']:
                                finish(item,{**record,'status':'preserved_existing'});continue
                            person.portrait.save(f'wikimedia-{qid}.{extension}',ContentFile(blob),save=False)
                            person.image_attribution=credit;person.save(update_fields=['portrait','image_attribution','updated_at'])
                        stats['portraits']+=1;finish(item,{**record,'status':'covered'})
                    except HTTPError as error:
                        finish(item,{**record,'status':'image_error','error':str(error)[:250]})
                        if error.code == 429:
                            # Leave unattempted items pending and stop this run; do not
                            # send the remaining batch into a provider rate limit.
                            stats.update(queue.summary(), stopped='provider_rate_limit', retry_after=error.headers.get('Retry-After', '900'))
                            raw_retry=error.headers.get('Retry-After','900')
                            try: delay=max(900,int(raw_retry))
                            except ValueError:
                                from email.utils import parsedate_to_datetime
                                try: delay=max(900,parsedate_to_datetime(raw_retry).timestamp()-time.time())
                                except (ValueError,TypeError): delay=900
                            atomic_state(COOLDOWN, {'until':time.time()+delay,'reason':'HTTP 429'})
                            atomic_state(RUN/'latest-stats.json', stats)
                            queue.close()
                            print(json.dumps(stats),flush=True)
                            return
                    except Exception as error:finish(item,{**record,'status':'image_error','error':str(error)[:250]})
                failures=0
            except Exception as error:
                failures+=1
                if isinstance(error, HTTPError) and error.code in (429, 503):
                    atomic_state(COOLDOWN, {'until':time.time()+900,'reason':f'HTTP {error.code}'})
                # Due retries retain their retryable state until finish(). Track
                # completed items here so provider failures consume their budget
                # too, while preserving decisions already saved in this batch.
                for item in batch:
                    if item['id'] not in finished_ids:finish(item,{'status':'provider_error','error':str(error)[:250]})
                if failures>=3 or isinstance(error, HTTPError) and error.code in (429,503):break
    stats.update(queue.summary(),provider_errors=queue.batch_errors);queue.close();atomic_state(RUN/'latest-stats.json', stats);print(json.dumps(stats),flush=True)
if __name__=='__main__':
    with exclusive('portraits'):main()
