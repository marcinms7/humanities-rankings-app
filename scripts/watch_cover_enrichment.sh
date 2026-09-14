#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
while true; do
  clear
  .venv/bin/python research/cover_enrichment_status.py
  printf '\nRefreshing every 10 seconds. Press Ctrl-C to stop watching.\n'
  sleep 10
done
