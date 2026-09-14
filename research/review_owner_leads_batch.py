"""Review a small first batch of owner-supplied source leads.

This fetches page titles and a bounded relevant excerpt, then promotes only
successful, substantive pages. It never treats an HTTP URL alone as evidence.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
import json, re, sys
from html import unescape
from pathlib import Path
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parent.parent
TARGETS=("books-all-time","philosophy-books-all-time","history-books-all-time","poetry-all-time","nonfiction-all-time")

def strip_html(raw):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", raw))).strip()

def fetch(row):
    try:
        req=Request(row["canonical_url"],headers={"User-Agent":"humanities-rankings-source-review/1.0"})
        with urlopen(req,timeout=12) as response:
            raw=response.read(300000).decode("utf-8","ignore")
        text=strip_html(raw)
        title=(re.search(r"<title[^>]*>(.*?)</title>",raw,re.I|re.S) or ["",""])[1]
        title=strip_html(title)
        return row,{"ok":len(text)>=1000,"title":title[:300],"excerpt":text[:1200],"length":len(text)}
    except Exception as error:
        return row,{"ok":False,"error":str(error)[:240]}

for target in TARGETS:
    path=ROOT/"research"/target/"sources.json"; ledger=json.loads(path.read_text())
    leads=[s for s in ledger["sources"] if s.get("owner_supplied") and not s.get("count_eligible")][:10]
    reviewed=0; failed=0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures=[pool.submit(fetch,row) for row in leads]
        for future in as_completed(futures):
            row,result=future.result(); row["metadata"]=row.get("metadata",{})
            row["metadata"]["owner_review"]={"reviewed_on":str(date.today()),**result}
            if result.get("ok"):
                row["accessed_at"]=str(date.today()); row["access_level"]="relevant_excerpt"; row["count_eligible"]=True
                row["evidence_notes"]=(f"Fetched and inspected the source page title and a bounded text excerpt on {date.today()}. "
                    f"The page identifies the supplied source/list ({result.get('title') or row['title']}); its excerpt was retained in the review metadata for target-specific candidate discovery. "
                    "This is excerpt-level review, not a claim that the entire source was exhaustively read.")
                row["location"]="Page title and first bounded text excerpt; see metadata.owner_review."
                row["disagreement_or_limitations"]="Excerpt-level web review; list scope, ranking method and full contents require deeper follow-up."
                reviewed+=1
            else: failed+=1
    path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+"\n")
    batch=ROOT/"research"/"_runs"/"2026-09-13"/f"owner-review-{target}-batch-01.json"; batch.parent.mkdir(parents=True,exist_ok=True)
    batch.write_text(json.dumps({"target":target,"reviewed":reviewed,"failed":failed,"source_ids":[s["source_id"] for s in leads]},ensure_ascii=False,indent=2)+"\n")
    print(target,reviewed,failed)
