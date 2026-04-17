#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PID_FILE="$ROOT_DIR/deploy/oracle/run/capacity-retry.pid"

if [ ! -f "$PID_FILE" ]; then
  echo "not running"
  exit 0
fi

pid="$(cat "$PID_FILE" 2>/dev/null || true)"
if [ -z "${pid:-}" ]; then
  rm -f "$PID_FILE"
  echo "not running"
  exit 0
fi

if kill -0 "$pid" 2>/dev/null; then
  kill "$pid"
  echo "stopped: pid=$pid"
else
  echo "stale pid file removed"
fi

rm -f "$PID_FILE"
