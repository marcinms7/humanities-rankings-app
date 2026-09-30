#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# The maintained monitor reads the durable queue index after audit-log rotation.
exec ./scripts/watch_catalog_enrichment.sh "$@"
