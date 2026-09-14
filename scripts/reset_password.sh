#!/usr/bin/env bash
# Uses Django's hidden interactive prompt. No password is written into this file.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/python ]]; then
  echo 'Run ./scripts/setup_local.sh first.' >&2
  exit 1
fi
if [[ $# -gt 1 ]]; then
  echo 'Usage: bash scripts/reset_password.sh [username]' >&2
  exit 1
fi
account_name="${1:-}"
if [[ -z "$account_name" ]]; then
  read -r -p 'Account username: ' account_name
fi
if [[ -z "$account_name" ]]; then
  echo 'A username is required.' >&2
  exit 1
fi
exec .venv/bin/python manage.py changepassword -- "$account_name"
