#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RETRY_SCRIPT="$ROOT_DIR/deploy/oracle/retry_capacity.sh"
RUN_DIR="$ROOT_DIR/deploy/oracle/run"
PID_FILE="$RUN_DIR/capacity-retry.pid"
LOG_FILE="$RUN_DIR/capacity-retry.log"
SLEEP_SECONDS="${SLEEP_SECONDS:-300}"

mkdir -p "$RUN_DIR"
chmod +x "$RETRY_SCRIPT"

if [ -f "$PID_FILE" ]; then
  existing_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "${existing_pid:-}" ] && kill -0 "$existing_pid" 2>/dev/null; then
    echo "already running: pid=$existing_pid"
    echo "log: $LOG_FILE"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

nohup env FOREVER=1 SLEEP_SECONDS="$SLEEP_SECONDS" bash "$RETRY_SCRIPT" >>"$LOG_FILE" 2>&1 </dev/null &
pid=$!
echo "$pid" >"$PID_FILE"

echo "started: pid=$pid"
echo "log: $LOG_FILE"
echo "stop: bash deploy/oracle/stop_capacity_retry.sh"
echo "status: bash deploy/oracle/status_capacity_retry.sh"
