#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec .venv/bin/python research/catalog_enrichment_supervisor.py --background "$@"
