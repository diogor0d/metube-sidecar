#!/bin/sh
set -eu

test "$(uname -s)" = "Darwin" || {
  echo "Apple shortcuts CLI signing requires macOS" >&2
  exit 1
}
command -v shortcuts >/dev/null 2>&1 || {
  echo "shortcuts CLI not found" >&2
  exit 1
}

shortcuts sign --mode anyone \
  --input "MeTube Download_unsigned.shortcut" \
  --output "MeTube Download.shortcut"
