#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY_SCRIPT="$ROOT_DIR/deploy/oracle/deploy_vm.sh"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-6}"
SLEEP_SECONDS="${SLEEP_SECONDS:-30}"
FOREVER="${FOREVER:-0}"
RETRY_ON_ANY_ERROR="${RETRY_ON_ANY_ERROR:-0}"

if [ ! -x "$DEPLOY_SCRIPT" ]; then
  chmod +x "$DEPLOY_SCRIPT"
fi

log() {
  printf '[oracle-retry] %s\n' "$*"
}

try_deploy() {
  local shape="$1"
  local image_os_version="$2"
  local log_file
  log_file="$(mktemp -t oracle-capacity)"

  if OCI_SHAPE="$shape" OCI_IMAGE_OS_VERSION="$image_os_version" bash "$DEPLOY_SCRIPT" >"$log_file" 2>&1; then
    cat "$log_file"
    rm -f "$log_file"
    return 0
  fi

  cat "$log_file"

  if grep -q 'Out of host capacity' "$log_file" || grep -q 'timed out' "$log_file"; then
    rm -f "$log_file"
    return 10
  fi

  rm -f "$log_file"
  return 1
}

attempt=1
while :; do
  if [ "$FOREVER" != "1" ] && [ "$attempt" -gt "$MAX_ATTEMPTS" ]; then
    break
  fi

  if (( attempt % 2 == 1 )); then
    shape="VM.Standard.A1.Flex"
    image_os_version="24.04"
  else
    shape="VM.Standard.E2.1.Micro"
    image_os_version="24.04"
  fi

  log "attempt ${attempt}/${MAX_ATTEMPTS}: ${shape}"

  if try_deploy "$shape" "$image_os_version"; then
    log "deployment succeeded"
    exit 0
  else
    rc=$?
    if [ "$rc" -ne 10 ] && [ "$RETRY_ON_ANY_ERROR" != "1" ]; then
      log "deployment failed with a non-capacity error"
      exit "$rc"
    fi
  fi

  if [ "$FOREVER" = "1" ] || [ "$attempt" -lt "$MAX_ATTEMPTS" ]; then
    log "no free capacity yet, sleeping ${SLEEP_SECONDS}s"
    sleep "$SLEEP_SECONDS"
  fi

  attempt=$((attempt + 1))
done

log "all attempts exhausted"
exit 2
