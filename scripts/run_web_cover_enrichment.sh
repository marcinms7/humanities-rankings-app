#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
cat >&2 <<'EOF'
This legacy web-cover runner is retired: it bypasses current identity,
provenance and concurrent-write safeguards.
Run a bounded batch with the maintained coordinator instead:
  ./scripts/run_catalog_enrichment.sh covers --max-batches 2 --batch-size 25
EOF
exit 2
