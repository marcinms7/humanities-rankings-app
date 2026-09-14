#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -r requirements.txt

if [[ -x .node/bin/node ]]; then
  export PATH="$PWD/.node/bin:$PATH"
fi
if ! command -v node >/dev/null || ! command -v npm >/dev/null; then
  echo 'Install Node.js 24 and npm, then rerun ./scripts/setup_local.sh.' >&2
  exit 1
fi
node -e 'if (Number(process.versions.node.split(".")[0]) < 22) { console.error("Node.js 22 or newer is required; this build uses Node 24."); process.exit(1); }'
npm --prefix frontend ci
npm --prefix frontend run build

mkdir -p data media
if [[ -z "${POSTGRES_HOST:-}" && -f "${SQLITE_PATH:-data/db.sqlite3}" ]]; then
  .venv/bin/python manage.py backup_local --daily
fi
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py bootstrap_rankings
.venv/bin/python manage.py import_research research/books-all-time/sources.json --target books-all-time
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py check
echo 'Ready. Run ./scripts/run_local.sh and open http://127.0.0.1:8000/ to create your local account.'
