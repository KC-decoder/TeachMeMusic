#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

if [[ ! -x .venv/bin/python ]]; then
  echo "Local environment missing. Run ./scripts/setup-local.sh first." >&2
  exit 1
fi

if [[ ! -f web/dist/index.html ]]; then
  echo "Browser build missing. Run ./scripts/setup-local.sh first." >&2
  exit 1
fi

exec .venv/bin/python -m teachmemusic.app.mobile_server "$@"
