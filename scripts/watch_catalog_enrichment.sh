#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
while true; do
  clear
  .venv/bin/python research/catalog_enrichment_status.py
  printf '\nRefreshing every 15 seconds. Press Ctrl-C to stop watching.\n'
  sleep 15
done
