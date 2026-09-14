"""Index owner-supplied source-universe text without claiming every lead was consulted."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = [
    ('books-all-time', '2026-09-13-owner-paste', 200),
    ('philosophy-books-all-time', '2026-09-13-owner-paste', 159),
    ('history-books-all-time', '2026-09-13-owner-paste', 200),
    ('poetry-all-time', '2026-09-13-owner-paste', 200),
    ('nonfiction-all-time', '2026-09-13-owner-paste', 200),
]

for target, run, claimed in RUNS:
    directory = ROOT / 'research' / 'incoming' / target / run
    raw = (directory / 'original.txt').read_bytes()
    content = raw.decode()
    urls = re.findall(r'https?://[^\s\]|>]+', content)
    urls = [url.rstrip('.,;') for url in urls]
    unique_urls = list(dict.fromkeys(urls))
    receipt = {
        'received_on': '2026-09-13', 'supplied_by': 'owner via chat attachment',
        'requested_target': target, 'sha256': hashlib.sha256(raw).hexdigest(),
        'reported_source_count': claimed, 'extracted_url_count': len(urls),
        'unique_url_count': len(unique_urls), 'status': 'received_and_indexed',
        'counting_note': 'These are source leads supplied with descriptions. They enter the eligible consulted-source ledger only after access/review and target-specific reconciliation.',
    }
    (directory / 'RECEIPT.json').write_text(json.dumps(receipt, indent=2) + '\n')
    (directory / 'source-leads.json').write_text(json.dumps({'target': target, 'urls': unique_urls}, ensure_ascii=False, indent=2) + '\n')
    (directory / 'INTAKE.md').write_text(
        f"# Intake: {target}\n\nPreserved owner-supplied source universe with SHA-256 `{receipt['sha256']}`. "
        f"The document reports {claimed} sources; URL extraction found {len(unique_urls)} unique URLs. "
        "Records are useful discovery leads with supplied descriptions, not automatically certified consultations. "
        "Existing stable source IDs take precedence during reconciliation. Central rankings and representative multilingual/community sources should be opened first.\n"
    )
    print(target, len(unique_urls))
