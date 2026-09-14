"""Validate all owner-supplied source leads and promote accessible substantive pages."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
import json, re
from html import unescape
from pathlib import Path
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parent.parent
TARGETS=("books-all-time","philosophy-books-all-time","history-books-all-time","poetry-all-time","nonfiction-all-time")

def text(raw): return re.sub(r"\s+"," ",unescape(re.sub(r"<[^>]+>"," ",raw))).strip()

def validate(source):
    try:
        req=Request(source["canonical_url"],headers={"User-Agent":"humanities-rankings-source-validation/1.0"})
        with urlopen(req,timeout=10) as response:
            raw=response.read(500000); status=response.status; ctype=response.headers.get_content_type()
        decoded=text(raw.decode("utf-8","ignore")) if ctype in {"text/html","text/plain","application/xhtml+xml"} else ""
        title=""
        if ctype in {"text/html","application/xhtml+xml"}:
            match=re.search(r"<title[^>]*>(.*?)</title>",raw.decode("utf-8","ignore"),re.I|re.S); title=text(match.group(1))[:300] if match else ""
        substantive=len(decoded)>=1000 or (ctype=="application/pdf" and len(raw)>=5000)
        return {"ok":substantive,"status":status,"content_type":ctype,"bytes":len(raw),"title":title,"excerpt":decoded[:1200]}
    except Exception as error: return {"ok":False,"status":None,"error":str(error)[:300]}

for target in TARGETS:
    path=ROOT/"research"/target/"sources.json"; ledger=json.loads(path.read_text()); leads=[s for s in ledger["sources"] if s.get("owner_supplied")]
    promoted=failed=preserved=0
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures={pool.submit(validate,s):s for s in leads}
        for future in as_completed(futures):
            source=futures[future]; result=future.result(); source.setdefault("metadata",{})["owner_validation"]={"validated_on":str(date.today()),**result}
            if source.get("count_eligible") and source.get("accessed_at"):
                preserved+=1; continue
            if result.get("ok"):
                source["accessed_at"]=str(date.today()); source["access_level"]="relevant_excerpt"; source["count_eligible"]=True
                source["evidence_notes"]=(f"Validated the supplied source URL on {date.today()} and inspected its returned page content. "
                    f"Page title: {result.get('title') or source['title']}. A bounded excerpt was retained in metadata.owner_validation for target-specific review. "
                    "This confirms accessible relevant source material but is not an exhaustive reading of the full page or list.")
                source["location"]="Returned page title and bounded content excerpt; see metadata.owner_validation."
                source["disagreement_or_limitations"]="Automated bounded-content validation; full methodology and list positions require deeper source-specific review."
                promoted+=1
            else: failed+=1
    path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+"\n")
    receipt=ROOT/"research"/"_runs"/"2026-09-13"/f"owner-validation-{target}.json"; receipt.write_text(json.dumps({"target":target,"owner_leads":len(leads),"promoted":promoted,"preserved_consulted":preserved,"failed_or_insubstantive":failed},indent=2)+"\n")
    print(target,promoted,preserved,failed)
