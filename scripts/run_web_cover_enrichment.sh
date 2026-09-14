#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec .venv/bin/python research/enrich_catalog_covers_web.py --limit 0 --workers 2
