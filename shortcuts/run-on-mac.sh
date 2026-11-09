#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

KEYCHAIN_ID_SERVICE="org.metube-sidecar.shortcut.cloudflare-client-id"
KEYCHAIN_SECRET_SERVICE="org.metube-sidecar.shortcut.cloudflare-client-secret"
KEYCHAIN_ACCOUNT=$(id -un)
LOCAL_DIR="$HOME/Library/Application Support/MeTube Sidecar"
HEALTH_USER_AGENT="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
RUNNER_BUILD="2026.10.06.5"

test "$(uname -s)" = "Darwin" || {
  echo "This script must run on macOS" >&2
  exit 1
}
case "${1:-}" in
  "") ;;
  --forget-credentials)
    security delete-generic-password -a "$KEYCHAIN_ACCOUNT" -s "$KEYCHAIN_ID_SERVICE" >/dev/null 2>&1 || true
    security delete-generic-password -a "$KEYCHAIN_ACCOUNT" -s "$KEYCHAIN_SECRET_SERVICE" >/dev/null 2>&1 || true
    echo "Removed MeTube Cloudflare credentials from this Mac's Keychain"
    exit 0
    ;;
  *)
    echo "usage: sh ./run-on-mac.sh [--forget-credentials]" >&2
    exit 2
    ;;
esac

echo "MeTube runner build $RUNNER_BUILD"

command -v python3 >/dev/null 2>&1 || {
  echo "python3 is required" >&2
  exit 1
}
command -v shortcuts >/dev/null 2>&1 || {
  echo "Apple shortcuts CLI is required" >&2
  exit 1
}
command -v security >/dev/null 2>&1 || {
  echo "macOS security CLI is required" >&2
  exit 1
}
command -v curl >/dev/null 2>&1 || {
  echo "curl is required" >&2
  exit 1
}
test -f "MeTube Download_unsigned.shortcut" || {
  echo "MeTube Download_unsigned.shortcut is missing" >&2
  exit 1
}
test -f "private/config.json" || {
  echo "private/config.json is missing" >&2
  exit 1
}

keychain_value() {
  security find-generic-password -a "$KEYCHAIN_ACCOUNT" -s "$1" -w 2>/dev/null || true
}

save_keychain_value() {
  security add-generic-password -U -a "$KEYCHAIN_ACCOUNT" -s "$1" -w "$2" >/dev/null
}

CF_ID=${CF_ID:-$(keychain_value "$KEYCHAIN_ID_SERVICE")}
CF_SECRET=${CF_SECRET:-$(keychain_value "$KEYCHAIN_SECRET_SERVICE")}
SAVE_CF_ID=false
SAVE_CF_SECRET=false

if [ -z "$CF_ID" ]; then
  printf '%s' "Cloudflare Access client ID (saved after validation): " >&2
  IFS= read -r CF_ID
  test -n "$CF_ID" || { echo "client ID is required" >&2; exit 1; }
  SAVE_CF_ID=true
fi

if [ -z "$CF_SECRET" ]; then
  CF_SECRET=$(python3 -c 'import getpass; print(getpass.getpass("Cloudflare Access client secret (saved after validation, hidden): "))')
  test -n "$CF_SECRET" || { echo "client secret is required" >&2; exit 1; }
  SAVE_CF_SECRET=true
fi

umask 077
if ! SERVER_URL=$(python3 -c '
import json
import sys
from urllib.parse import urlsplit

config = json.load(open(sys.argv[1], encoding="utf-8"))
server_url = config["server_url"]
parsed = urlsplit(server_url)
if (
    parsed.scheme != "https"
    or not parsed.hostname
    or parsed.username is not None
    or parsed.password is not None
    or parsed.path not in {"", "/"}
    or parsed.query
    or parsed.fragment
):
    raise ValueError("server_url must be an HTTPS origin without credentials, path, query, or fragment")
print(server_url.rstrip("/"))
' "private/config.json"); then
  echo "invalid private server URL; no credentials were sent" >&2
  exit 1
fi
HEALTH_BODY=$(mktemp "${TMPDIR:-/tmp}/metube-sidecar-health.XXXXXX")
trap 'rm -f "$HEALTH_BODY"' EXIT
trap 'exit 1' HUP INT TERM

echo "Validating Cloudflare Access credentials..."
if ! HTTP_STATUS=$(printf '%s\n' \
  "CF-Access-Client-Id: $CF_ID" \
  "CF-Access-Client-Secret: $CF_SECRET" | \
  curl --silent --show-error \
    --output "$HEALTH_BODY" \
    --write-out '%{http_code}' \
    --connect-timeout 10 \
    --max-time 30 \
    --proto '=https' \
    --user-agent "$HEALTH_USER_AGENT" \
    --header @- \
    "$SERVER_URL/healthz"); then
  echo "credential validation failed: could not reach $SERVER_URL/healthz; no new credentials were saved" >&2
  exit 1
fi
if [ "$HTTP_STATUS" != "200" ]; then
  echo "credential validation failed: $SERVER_URL/healthz returned HTTP $HTTP_STATUS; no new credentials were saved" >&2
  echo "If these came from Keychain, run: sh ./run-on-mac.sh --forget-credentials" >&2
  exit 1
fi
if ! python3 -c 'import json, sys; data=json.load(open(sys.argv[1], encoding="utf-8")); raise SystemExit(0 if data == {"status": "ok"} else 1)' "$HEALTH_BODY"; then
  echo "credential validation failed: $SERVER_URL/healthz returned an unexpected response; no new credentials were saved" >&2
  exit 1
fi
echo "Cloudflare Access credentials validated"

if [ "$SAVE_CF_ID" = true ]; then
  save_keychain_value "$KEYCHAIN_ID_SERVICE" "$CF_ID"
fi
if [ "$SAVE_CF_SECRET" = true ]; then
  save_keychain_value "$KEYCHAIN_SECRET_SERVICE" "$CF_SECRET"
fi

mkdir -p "$LOCAL_DIR/private"
cp "MeTube Download_unsigned.shortcut" "$LOCAL_DIR/MeTube Download_unsigned.shortcut"
cp "prepare-private.py" "$LOCAL_DIR/prepare-private.py"
cp "finalize.py" "$LOCAL_DIR/finalize.py"
cp "private/config.json" "$LOCAL_DIR/private/config.json"

export CF_ID CF_SECRET
python3 "$LOCAL_DIR/prepare-private.py" --from-env

cd "$LOCAL_DIR/private"
rm -f "MeTube Download Configured.shortcut"
sh ./sign-private.sh
open "MeTube Download Configured.shortcut"
unset CF_ID CF_SECRET
printf '%s\n' "Opened signed MeTube Download Configured.shortcut for import"
