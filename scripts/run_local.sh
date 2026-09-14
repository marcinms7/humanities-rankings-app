#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/python || ! -f backend/static/app/index.html ]]; then
  echo 'Run ./scripts/setup_local.sh first.' >&2
  exit 1
fi
mkdir -p data media
export DJANGO_DEBUG="${DJANGO_DEBUG:-1}"
if [[ -z "${POSTGRES_HOST:-}" ]]; then
  .venv/bin/python manage.py backup_local --daily
fi
.venv/bin/python manage.py migrate --noinput
exec .venv/bin/python manage.py runserver "127.0.0.1:${PORT:-8000}"
