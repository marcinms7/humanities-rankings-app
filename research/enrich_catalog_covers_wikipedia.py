"""Conservative Wikipedia book-cover fallback with resumable outcomes."""
from __future__ import annotations

import argparse, html, json, os, re, sys, unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
RUN = ROOT / "research/_runs/2026-09-14/catalog-wikipedia-covers"
LEDGER = RUN / "outcomes.jsonl"
HEADERS = {"User-Agent": "Marginalia catalogue enrichment/1.0 (local humanities catalogue)"}

def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]", "", s)

def tokens(s):
    return re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().casefold())

def api(params, timeout=10):
    params.update(action="query", format="json", formatversion=2)
    req = Request("https://en.wikipedia.org/w/api.php?" + urlencode(params), headers=HEADERS)
    with urlopen(req, timeout=timeout) as response:
        return json.load(response)

def image(url):
    with urlopen(Request(url, headers=HEADERS), timeout=12) as response:
        return response.read()

def title_ok(expected, found):
    a, b = norm(expected), norm(re.sub(r"\s*\([^)]*\)\s*$", "", found))
    return a == b or (len(a) >= 12 and (a in b or b in a))

def author_ok(authors, extract):
    hay = set(tokens(extract))
    return any(any(len(t) >= 4 and t in hay for t in tokens(author)) for author in authors)

def lookup(item):
    query = f'intitle:"{item["title"]}" ' + (item["authors"][0] if item["authors"] else "")
    try:
        data = api({"generator":"search", "gsrsearch":query, "gsrlimit":6,
                    "prop":"extracts|images|info", "exintro":1, "explaintext":1,
                    "imlimit":30, "inprop":"url"})
    except Exception as exc:
        return None, "wikipedia_error: " + str(exc)[:140]
    pages = []
    for page in data.get("query", {}).get("pages", []):
        if title_ok(item["title"], page.get("title", "")) and author_ok(item["authors"], page.get("extract", "")):
            pages.append(page)
    if len(pages) != 1:
        return None, "wikipedia_no_unique_page"
    page = pages[0]
    candidates = []
    title_norm = norm(item["title"])
    for entry in page.get("images", []):
        name = entry.get("title", "")
        low = name.casefold()
        if not low.endswith((".jpg", ".jpeg", ".png", ".webp")):
            continue
        if any(x in low for x in ("commons-logo", "icon", "speaker", "signature", "author")):
            continue
        stem = norm(re.sub(r"^File:|\.[^.]+$", "", name, flags=re.I))
        score = 100 if stem == title_norm else 90 if len(title_norm) >= 8 and title_norm in stem else 0
        if score:
            candidates.append((score, name))
    if not candidates:
        return None, "wikipedia_no_cover_image"
    candidates.sort(reverse=True)
    if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
        return None, "wikipedia_ambiguous_image"
    filename = candidates[0][1]
    try:
        info = api({"titles":filename, "prop":"imageinfo", "iiprop":"url|mime", "iiurlwidth":800})
        image_info = info["query"]["pages"][0]["imageinfo"][0]
        url = image_info.get("thumburl") or image_info["url"]
        blob = image(url)
    except Exception as exc:
        return None, "wikipedia_image_error: " + str(exc)[:140]
    if len(blob) < 1024:
        return None, "wikipedia_image_too_small"
    return {"image":blob, "image_url":url, "page_url":page.get("fullurl"), "filename":filename}, None

def lookup_html(item):
    slug = quote(item["title"].replace(" ", "_"), safe="_()")
    page_url = "https://en.wikipedia.org/wiki/" + slug
    try:
        req = Request(page_url, headers=HEADERS)
        with urlopen(req, timeout=12) as response:
            final_url = response.geturl(); body = response.read().decode("utf-8", "ignore")
    except Exception as exc:
        return None, "wikipedia_html_error: " + str(exc)[:140]
    visible = re.sub(r"<[^>]+>", " ", html.unescape(body))
    if not author_ok(item["authors"], visible[:80000]):
        return None, "wikipedia_html_author_mismatch"
    found = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', body, re.I)
    if not found:
        return None, "wikipedia_html_no_image"
    url = html.unescape(found.group(1)).split("?", 1)[0]
    filename = url.split("/", 8)[-1].split("?", 1)[0]
    stem = norm(re.sub(r"\.[^.]+$", "", filename))
    expected = norm(item["title"])
    audited_filename_variants = {785, 1017, 1367, 1375, 1388, 4805, 4808, 4816, 4832, 4855,
                                 1369, 1371, 1503, 1553, 1768, 1960, 1975, 4083, 4277, 4675,
                                 4803, 4831, 4882,
                                 4906, 4911, 4917, 4920, 4960,
                                 4968, 4978, 4981, 5005, 5050, 5061, 5063, 5418, 5504, 5506,
                                 4672, 5372, 5517, 5523, 5525, 5544, 5551, 5592, 5613, 5857,
                                 6242, 6291, 7170, 8117}
    if not (stem == expected or (len(expected) >= 8 and expected in stem) or item["id"] in audited_filename_variants):
        return None, "wikipedia_html_image_mismatch"
    try: blob = image(url)
    except Exception as exc: return None, "wikipedia_html_image_error: " + str(exc)[:140]
    if len(blob) < 1024: return None, "wikipedia_html_image_too_small"
    return {"image":blob,"image_url":url,"page_url":final_url,"filename":filename},None

def main():
    p=argparse.ArgumentParser(); p.add_argument("--limit",type=int,default=100); p.add_argument("--workers",type=int,default=4)
    p.add_argument("--min-work-id",type=int,default=0); p.add_argument("--max-work-id",type=int); p.add_argument("--retry",action="store_true")
    p.add_argument("--html-only",action="store_true")
    p.add_argument("--work-ids",default="",help="Comma-separated work IDs")
    args=p.parse_args(); os.environ.setdefault("DJANGO_SETTINGS_MODULE","backend.config.settings")
    import django; django.setup()
    from django.core.files.base import ContentFile
    from django.db import transaction
    from backend.core.models import Edition, Person, Work
    RUN.mkdir(parents=True,exist_ok=True)
    done=set()
    if LEDGER.exists() and not args.retry:
        for line in LEDGER.read_text().splitlines():
            try: done.add(int(json.loads(line)["work_id"]))
            except Exception: pass
    person_names={norm(x) for x in Person.objects.values_list("name",flat=True)}
    catalogue_titles={norm(x) for x in Work.objects.filter(is_archived=False).values_list("title",flat=True)}
    qs=Work.objects.filter(is_archived=False,pk__gte=args.min_work_id).select_related("default_edition").prefetch_related("authors").order_by("pk")
    if args.work_ids: qs=qs.filter(pk__in=[int(x) for x in args.work_ids.split(",") if x.strip()])
    if args.max_work_id: qs=qs.filter(pk__lte=args.max_work_id)
    items=[]
    for w in qs:
        if w.pk in done or (w.default_edition_id and w.default_edition.cover): continue
        authors=[a.name for a in w.authors.all()]
        if not authors or (not args.work_ids and (norm(w.title) in person_names or any(norm(a) in catalogue_titles for a in authors))): continue
        aliases={
            692:"Goethe's Faust", 377:"Aeneid", 676:"Paradise Lost", 785:"No Longer Human",
            784:"Snow Country", 1017:"Drive Your Plow Over the Bones of the Dead",
            1077:"Life: A User's Manual", 1367:"The Posthumous Memoirs of Bras Cubas",
            1375:"The Passion According to G.H.", 1388:"The Savage Detectives",
            4802:"The Trilogy (novels)", 4805:"My Struggle (Knausgard novels)", 4806:"Nightwood",
            4808:"Nineteen Eighty-Four", 4816:"The Book of the New Sun",
            4819:"The Goldfinch", 4831:"Assassin's Apprentice", 4832:"Discworld", 4836:"Harry Potter",
            4840:"Unsouled", 4841:"All Systems Red", 4843:"Earthsea", 4850:"Senlin Ascends",
            4853:"Red Sister", 4855:"Children of Time (novel)", 4857:"The Goblin Emperor",
            4858:"Kings of the Wyld", 4859:"Rocannon's World", 4862:"Promise of Blood",
            4865:"The Curse of Chalion", 4872:"The Black Prism", 4873:"The Black Company",
            4875:"The Traitor Baru Cormorant", 4876:"One Piece", 4877:"The Chronicles of Narnia",
            4882:"Kushiel's Dart", 4883:"The Darkness That Comes Before",
            4892:"The Bear and the Nightingale", 4898:"The Song of Achilles",
            4905:"Shards of Honor", 4906:"A Natural History of Dragons", 4907:"City of Stairs",
            4911:"Magician (Feist novel)", 4919:"Too Like the Lightning", 4920:"Consider Phlebas",
            4944:"Dragonflight", 4955:"Sufficiently Advanced Magic", 4956:"The Way of Shadows",
            4960:"The Warded Man", 4967:"Black Sun Rising", 4968:"The Thief (Turner novel)",
            4975:"Blood Song (novel)", 4978:"The Raven Boys", 4981:"Traitor's Blade",
            4995:"Three Parts Dead", 4998:"The Emperor's Blades", 5000:"The Dragon's Path",
            5005:"The Book of Three", 5022:"Ready Player One", 5025:"Magic Bites",
            5027:"Furies of Calderon", 5032:"Heroes Die", 5034:"The Hundred Thousand Kingdoms",
            5043:"Ninefox Gambit", 5050:"Legend (Gemmell novel)", 5061:"Elric of Melnibone",
            5064:"Moon Called", 5694:"Perdido Street Station", 5711:"The Red Knight",
            5148:"Bible", 5153:"The Death of Ivan Ilyich", 5161:"American Psycho",
            5413:"Cairo Trilogy", 5517:"The Gulag Archipelago", 5613:"2666",
            5506:"We (novel)", 5615:"Journey to the End of the Night", 5857:"The Red and the Black",
            6280:"Gone Girl", 7851:"Your Name",
        }
        title=aliases.get(w.pk) or re.split(r"\s*[/:]\s*|\s*\(",w.title,1,flags=re.I)[0].strip()
        items.append({"id":w.pk,"title":title,"display_title":w.title,"authors":authors})
        if args.limit and len(items)>=args.limit: break
    stats={"queued":len(items),"covered":0}
    with LEDGER.open("a") as out, ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(lookup_html if args.html_only else lookup,x):x for x in items}
        for future in as_completed(futures):
            item=futures[future]; match,reason=future.result(); row={"work_id":item["id"],"title":item["display_title"]}
            if reason:
                row["status"]=reason; stats[reason.split(":",1)[0]]=stats.get(reason.split(":",1)[0],0)+1
            else:
                with transaction.atomic():
                    work=Work.objects.select_for_update().get(pk=item["id"]); edition=work.default_edition
                    if edition is None:
                        edition=Edition.objects.create(work=work,language="English"); work.default_edition=edition; work.save(update_fields=["default_edition","updated_at"])
                    suffix=".png" if match["image_url"].lower().split("?",1)[0].endswith(".png") else ".jpg"
                    edition.cover.save(f"wikipedia-{item['id']}{suffix}",ContentFile(match["image"]),save=False)
                    edition.source_url=match["page_url"] or "https://en.wikipedia.org/"
                    representative = (f'Representative series image using {item["title"]}. ' if norm(item["title"]) != norm(item["display_title"]) else "")
                    edition.image_attribution=representative + f'Wikipedia image {match["filename"]}: {match["image_url"]}'
                    edition.save(update_fields=["cover","source_url","image_attribution","updated_at"])
                row.update(status="covered",provider="wikipedia",edition_id=edition.pk,source_url=match["page_url"],image_url=match["image_url"]); stats["covered"]+=1
            out.write(json.dumps(row,ensure_ascii=False)+"\n"); out.flush(); print(f"[{item['id']}] {row['status']} — {item['display_title']}",flush=True)
    print(json.dumps(stats,indent=2))

if __name__=="__main__": main()
