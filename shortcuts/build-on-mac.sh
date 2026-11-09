#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"
COMPILER=${CHERRI_BIN:-"$SCRIPT_DIR/.tools/cherri"}
test -x "$COMPILER" || {
  echo "Set CHERRI_BIN to the pinned Cherri 2.3.0 compiler; see README.md." >&2
  exit 1
}
"$COMPILER" main.cherri --skip-sign
python3 finalize.py "MeTube Download_unsigned.shortcut"
python3 -m unittest discover -s tests -p test_shortcut.py -q
python3 -m unittest discover -s tests -p test_runner.py -q
