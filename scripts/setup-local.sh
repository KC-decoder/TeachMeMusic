#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_COMMAND="${PYTHON_COMMAND:-python3}"

cd "$PROJECT_ROOT"

if ! command -v "$PYTHON_COMMAND" >/dev/null 2>&1; then
  echo "TeachMeMusic requires Python 3.12 or 3.13." >&2
  echo "Set PYTHON_COMMAND to the supported Python executable if needed." >&2
  exit 1
fi

PYTHON_MINOR="$($PYTHON_COMMAND -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
case "$PYTHON_MINOR" in
  3.12) PYTHON_LOCK_SUFFIX="py312" ;;
  3.13) PYTHON_LOCK_SUFFIX="py313" ;;
  *)
    echo "Unsupported Python $PYTHON_MINOR; use Python 3.12 or 3.13." >&2
    exit 1
    ;;
esac

SYSTEM_NAME="$(uname -s)"
MACHINE_NAME="$(uname -m)"
case "$SYSTEM_NAME:$MACHINE_NAME" in
  Darwin:arm64) PLATFORM_LOCK_PREFIX="macos-arm64" ;;
  Linux:x86_64) PLATFORM_LOCK_PREFIX="linux-x86_64" ;;
  *)
    echo "No verified dependency lock exists for $SYSTEM_NAME/$MACHINE_NAME." >&2
    echo "Supported environments: macOS ARM64 and Linux x86-64." >&2
    exit 1
    ;;
esac

if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo "TeachMeMusic requires Node.js 20 or newer and npm." >&2
  exit 1
fi

NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
if (( NODE_MAJOR < 20 )); then
  echo "Unsupported Node.js $(node --version); install Node.js 20 or newer." >&2
  exit 1
fi

LOCK_PATH="requirements/pylock.${PLATFORM_LOCK_PREFIX}-${PYTHON_LOCK_SUFFIX}.toml"
if [[ ! -f "$LOCK_PATH" ]]; then
  echo "Required dependency lock is missing: $LOCK_PATH" >&2
  exit 1
fi

echo "Preparing TeachMeMusic with Python $PYTHON_MINOR and Node.js $(node --version)."

if [[ ! -x .venv/bin/python ]]; then
  "$PYTHON_COMMAND" -m venv .venv
fi

.venv/bin/python -m pip install "pip==26.2.1"
.venv/bin/python -m pip install -r "$LOCK_PATH"
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .

(
  cd web
  npm ci
  npm run build
)

echo
echo "TeachMeMusic is ready. Start it with:"
echo "  ./scripts/run-local.sh"
