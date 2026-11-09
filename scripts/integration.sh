#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
INTEGRATION_ID=$(python3 -c 'import uuid; print(uuid.uuid4().hex[:12])')
INTEGRATION_PROJECT="metube-synthetic-$INTEGRATION_ID"
METUBE_TEST_IMAGE="metube-sidecar-integration:$INTEGRATION_ID"
export METUBE_TEST_IMAGE

compose() {
  docker compose --project-name "$INTEGRATION_PROJECT" -f docker-compose.integration.yml "$@"
}
cleanup() {
  INTEGRATION_RESULT=$?
  trap - EXIT
  if ! compose down --volumes >/dev/null 2>&1; then
    echo "Cleanup failed for disposable project $INTEGRATION_PROJECT" >&2
    INTEGRATION_RESULT=1
  fi
  docker image rm "$METUBE_TEST_IMAGE" >/dev/null 2>&1 || true
  exit "$INTEGRATION_RESULT"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
compose config --quiet
compose build sidecar
compose up -d fixture metube sidecar
compose run --rm -T check
