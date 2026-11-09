#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
CHECK_PYTHON=${PYTHON_BIN:-"$ROOT/.venv/bin/python"}
test -x "$CHECK_PYTHON" || {
  echo "Create a Python 3.12+ .venv and install .[dev] first; see README.md." >&2
  exit 1
}
CHECK_STATE=$(mktemp -d "${TMPDIR:-/tmp}/metube-check.XXXXXX")
trap 'rm -rf "$CHECK_STATE"' EXIT
export DATA_DIR="$CHECK_STATE/data"
export DOWNLOADS_DIR="$CHECK_STATE/downloads"
sh shortcuts/build-on-mac.sh
"$CHECK_PYTHON" -m compileall -q app tests shortcuts scripts
"$CHECK_PYTHON" -m pytest -q
"$CHECK_PYTHON" -m unittest discover -s shortcuts/tests -q
docker compose -f docker-compose.example.yml config --quiet
git diff --check
