#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PID_FILE="$ROOT_DIR/deploy/oracle/run/capacity-retry.pid"
LOG_FILE="$ROOT_DIR/deploy/oracle/run/capacity-retry.log"

if [ ! -f "$PID_FILE" ]; then
  echo "status: not running"
  [ -f "$LOG_FILE" ] && echo "log: $LOG_FILE"
  exit 0
fi

pid="$(cat "$PID_FILE" 2>/dev/null || true)"
if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null; then
  echo "status: running (pid=$pid)"
else
  echo "status: not running (stale pid file)"
fi

if [ -f "$LOG_FILE" ]; then
  echo "log: $LOG_FILE"
  echo "--- last 20 lines ---"
  tail -n 20 "$LOG_FILE"
fi
