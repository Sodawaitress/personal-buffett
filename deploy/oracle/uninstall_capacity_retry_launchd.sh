#!/usr/bin/env bash
set -euo pipefail

PLIST_ID="com.personalbuffett.oracle-capacity-retry"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_ID}.plist"
APP_DIR="$HOME/Library/Application Support/personal-buffett/oracle-runner"

launchctl bootout "gui/$(id -u)/${PLIST_ID}" >/dev/null 2>&1 || true
rm -f "$PLIST_PATH"
rm -rf "$APP_DIR"

echo "removed: ${PLIST_ID}"
