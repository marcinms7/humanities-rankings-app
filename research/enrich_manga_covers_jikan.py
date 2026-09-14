"""Attach verified manga covers from MyAnimeList through the public Jikan API."""
from __future__ import annotations

import argparse, hashlib, json, os, re, sys, time, unicodedata
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
RUN = ROOT / "research/_runs/2026-09-14/catalog-manga-jikan"
CACHE = RUN / "outcomes.jsonl"
HEADERS = {"User-Agent": "Marginalia catalogue enrichment/1.0 (cover lookup)"}

def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]", "", s)

def tokens(s):
    return set(re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().casefold()))

def title_ok(expected, candidate):
    a, b = norm(expected), norm(candidate)
    if a == b: return True
    if min(len(a), len(b)) >= 10 and (a in b or b in a): return True
    x, y = tokens(expected), tokens(candidate)
    return bool(x and y and len(x & y) / len(x | y) >= .8)

def author_ok(expected, found):
    for left in expected:
        lt = tokens(left)
        for right in found:
            rt = tokens(right)
            if norm(left) == norm(right) or (len(lt) >= 2 and lt == rt): return True
    return False

def get_json(url, attempts=4):
    error = None
    for delay in (0, 2, 5, 10)[:attempts]:
        if delay: time.sleep(delay)
        try:
            with urlopen(Request(url, headers=HEADERS), timeout=25) as r: return json.load(r)
        except Exception as exc: error = exc
    raise error

def get_bytes(url):
    with urlopen(Request(url, headers=HEADERS), timeout=25) as r: return r.read()

def lookup(item):
    url = "https://api.jikan.moe/v4/manga?" + urlencode({"q": item["title"], "limit": 15, "sfw": "true"})
    data = get_json(url)
    matches = []
    for row in data.get("data", []):
        titles = [row.get("title"), row.get("title_english"), row.get("title_japanese")]
        titles += [x.get("title") for x in row.get("titles", [])]
        found_authors = [x.get("name", "") for x in row.get("authors", [])]
        if any(title_ok(item["title"], t) for t in titles if t) and author_ok(item["authors"], found_authors):
            image_url = (row.get("images", {}).get("jpg", {}).get("large_image_url") or
                         row.get("images", {}).get("jpg", {}).get("image_url"))
            if image_url: matches.append(row)
    if not matches: return None, "no_verified_match"
    exact = [r for r in matches if any(norm(item["title"]) == norm(t.get("title", "")) for t in r.get("titles", []))]
    chosen = (exact or matches)[0]
    image_url = chosen["images"]["jpg"].get("large_image_url") or chosen["images"]["jpg"]["image_url"]
    image = get_bytes(image_url)
    if len(image) < 1024: return None, "cover_too_small"
    return {"mal_id": chosen["mal_id"], "source_url": chosen["url"], "image_url": image_url, "image": image}, None

def completed():
    out = set()
    if CACHE.exists():
        for line in CACHE.read_text().splitlines():
            try: out.add(int(json.loads(line)["work_id"]))
            except Exception: pass
    return out

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--delay", type=float, default=.45)
    p.add_argument("--work-id", type=int)
    args = p.parse_args()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.settings")
    import django; django.setup()
    from django.core.files.base import ContentFile
    from django.db import transaction
    from backend.core.models import Edition, Work
    RUN.mkdir(parents=True, exist_ok=True)
    done = completed(); qs = Work.objects.filter(is_archived=False, field="manga").select_related("default_edition").prefetch_related("authors").order_by("pk")
    if args.work_id: qs = qs.filter(pk=args.work_id)
    items = []
    for w in qs:
        if w.pk in done or (w.default_edition_id and w.default_edition.cover): continue
        items.append({"id": w.pk, "title": w.title, "authors": [a.name for a in w.authors.all()]})
        if args.limit and len(items) >= args.limit: break
    stats = {"queued": len(items), "covered": 0, "no_verified_match": 0, "error": 0}
    with CACHE.open("a") as log:
        for i, item in enumerate(items, 1):
            row = {"work_id": item["id"], "title": item["title"], "authors": item["authors"]}
            if not item["authors"]: match, reason = None, "no_credited_author"
            else:
                try: match, reason = lookup(item)
                except Exception as exc: match, reason = None, "error: " + str(exc)[:180]
            if match:
                with transaction.atomic():
                    work = Work.objects.select_for_update().get(pk=item["id"], is_archived=False)
                    edition = work.default_edition
                    if not edition:
                        edition = Edition.objects.create(work=work, language="English")
                        work.default_edition = edition; work.save(update_fields=["default_edition", "updated_at"])
                    digest = hashlib.sha256(match["image"]).hexdigest()[:16]
                    edition.cover.save(f"mal-{match['mal_id']}-{digest}.jpg", ContentFile(match["image"]), save=False)
                    edition.source_url = match["source_url"]
                    edition.image_attribution = f"MyAnimeList record {match['source_url']}; cover retrieved through Jikan API ({match['image_url']})"
                    edition.save(update_fields=["cover", "source_url", "image_attribution", "updated_at"])
                row.update(status="covered", mal_id=match["mal_id"], source_url=match["source_url"], image_url=match["image_url"], edition_id=edition.pk)
                stats["covered"] += 1
            else:
                row["status"] = reason
                stats[reason.split(":",1)[0]] = stats.get(reason.split(":",1)[0], 0) + 1
            log.write(json.dumps(row, ensure_ascii=False) + "\n"); log.flush()
            print(f"[{i}/{len(items)}] [{item['id']}] {row['status']} — {item['title']}", flush=True)
            time.sleep(args.delay)
    (RUN / "latest-stats.json").write_text(json.dumps(stats, indent=2) + "\n")
    print(json.dumps(stats, indent=2))

if __name__ == "__main__": main()
