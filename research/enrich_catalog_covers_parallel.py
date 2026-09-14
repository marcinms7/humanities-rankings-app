"""Concurrent network stage for the resumable Open Library cover enrichment."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from enrich_catalog_covers import CACHE, MEDIA, best_doc, load_cache, norm


def fetch(work):
    wid, title, authors = work
    try:
        params = {"title": title, "author": authors[0] if authors else "", "limit": 5, "fields": "*,availability"}
        req = Request("https://openlibrary.org/search.json?" + urlencode(params), headers={"User-Agent": "humanities-rankings-cover-enrichment/1.0"})
        with urlopen(req, timeout=6) as response:
            doc = best_doc(type("W", (), {"title": title, "authors": [type("A", (), {"name": a})() for a in authors]})(), json.loads(response.read()).get("docs", []))
        if not doc:
            return {"work_id": wid, "title": title, "status": "no_match"}, None
        cover_id = doc.get("cover_i")
        image = None
        if cover_id:
            req = Request(f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg?default=false", headers={"User-Agent": "humanities-rankings-cover-enrichment/1.0"})
            with urlopen(req, timeout=6) as response:
                image = response.read()
        return {"work_id": wid, "title": title, "status": "covered" if image else "matched_without_cover", "cover_id": cover_id, "isbn": (doc.get("isbn") or [""])[0], "publisher": (doc.get("publisher") or [""])[0], "pages": doc.get("number_of_pages_median"), "first_publish_year": doc.get("first_publish_year"), "languages": [x.get("key", "").split('/')[-1] for x in doc.get("language", [])], "source_key": doc.get("key")}, image
    except Exception as error:
        return {"work_id": wid, "title": title, "status": "error", "error": str(error)[:300]}, None


def main():
    import os
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.settings")
    import django
    django.setup()
    from django.core.files.base import ContentFile
    from backend.core.models import Edition, Work
    cache = load_cache()
    works = []
    for work in Work.objects.filter(is_archived=False).prefetch_related("authors", "editions"):
        if (str(work.pk) in cache and cache[str(work.pk)].get("status") != "error") or any(e.cover for e in work.editions.filter(is_archived=False)):
            continue
        works.append((work.pk, work.title, [a.name for a in work.authors.all()]))
    CACHE.parent.mkdir(parents=True, exist_ok=True); MEDIA.mkdir(parents=True, exist_ok=True)
    stats = {"queued": len(works), "covered": 0, "no_match": 0, "matched_without_cover": 0, "errors": 0}
    with CACHE.open("a") as out, ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(fetch, work) for work in works]
        for future in as_completed(futures):
            row, image = future.result(); wid = row["work_id"]
            if row["status"] in {"covered", "matched_without_cover"}:
                work = Work.objects.get(pk=wid)
                changed = []
                if not work.original_year and row.get("first_publish_year"):
                    work.original_year = row["first_publish_year"]; changed.append("original_year")
                if not work.original_language and row.get("languages"):
                    work.original_language = row["languages"][0]; changed.append("original_language")
                if changed:
                    changed.append("updated_at"); work.save(update_fields=changed)
                edition = work.editions.filter(is_archived=False).first()
                if edition is None:
                    edition = Edition(work=work, language="English", publisher=row.get("publisher", ""), isbn=row.get("isbn", ""), pages=row.get("pages"), source_url=f"https://openlibrary.org{row.get('source_key', '')}")
                    edition.full_clean(); edition.save()
                else:
                    fields=[]
                    for field in ("publisher", "isbn", "pages"):
                        value=row.get(field)
                        if not getattr(edition, field) and value:
                            setattr(edition, field, value); fields.append(field)
                    if fields:
                        fields.append("updated_at"); edition.save(update_fields=fields)
                if image:
                    edition.cover.save(f"openlibrary-{row['cover_id']}.jpg", ContentFile(image), save=False)
                    edition.image_attribution = f"Open Library Covers API: https://covers.openlibrary.org/b/id/{row['cover_id']}-L.jpg"
                    edition.save(update_fields=["cover", "image_attribution", "updated_at"])
                    row["edition_id"] = edition.pk
            out.write(json.dumps(row, ensure_ascii=False) + "\n"); out.flush(); cache[str(wid)] = row
            stats[row["status"]] = stats.get(row["status"], 0) + 1
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
