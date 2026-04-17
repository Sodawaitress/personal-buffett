#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_DIR="$HOME/Library/Application Support/personal-buffett/oracle-runner"
RUN_SCRIPT="$APP_DIR/deploy/oracle/retry_capacity.sh"
LOG_DIR="$HOME/Library/Logs/personal-buffett"
PLIST_ID="com.personalbuffett.oracle-capacity-retry"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_ID}.plist"
LOG_FILE="$LOG_DIR/oracle-capacity-retry.log"
ERROR_FILE="$LOG_DIR/oracle-capacity-retry.err.log"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-300}"
ATTEMPT_SLEEP_SECONDS="${ATTEMPT_SLEEP_SECONDS:-5}"

mkdir -p "$LOG_DIR" "$HOME/Library/LaunchAgents" "$APP_DIR/deploy/oracle"
cp "$ROOT_DIR/deploy/oracle/retry_capacity.sh" "$APP_DIR/deploy/oracle/retry_capacity.sh"
cp "$ROOT_DIR/deploy/oracle/deploy_vm.sh" "$APP_DIR/deploy/oracle/deploy_vm.sh"
cp "$ROOT_DIR/deploy/oracle/cloud-init.yaml.tmpl" "$APP_DIR/deploy/oracle/cloud-init.yaml.tmpl"
if [ -f "$ROOT_DIR/.env" ]; then
  cp "$ROOT_DIR/.env" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
fi
chmod +x "$APP_DIR/deploy/oracle/"*.sh

cat >"$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>${PLIST_ID}</string>

    <key>ProgramArguments</key>
    <array>
      <string>/bin/bash</string>
      <string>${RUN_SCRIPT}</string>
    </array>

    <key>EnvironmentVariables</key>
    <dict>
      <key>HOME</key>
      <string>${HOME}</string>
      <key>TMPDIR</key>
      <string>${TMPDIR:-/tmp}</string>
      <key>MAX_ATTEMPTS</key>
      <string>2</string>
      <key>SLEEP_SECONDS</key>
      <string>${ATTEMPT_SLEEP_SECONDS}</string>
      <key>PATH</key>
      <string>/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>

    <key>WorkingDirectory</key>
    <string>${APP_DIR}</string>

    <key>RunAtLoad</key>
    <true/>

    <key>StartInterval</key>
    <integer>${INTERVAL_SECONDS}</integer>

    <key>StandardOutPath</key>
    <string>${LOG_FILE}</string>

    <key>StandardErrorPath</key>
    <string>${ERROR_FILE}</string>
  </dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/${PLIST_ID}" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"

echo "installed: ${PLIST_ID}"
echo "plist: $PLIST_PATH"
echo "runner dir: $APP_DIR"
echo "stdout: $LOG_FILE"
echo "stderr: $ERROR_FILE"
echo "status: launchctl print gui/$(id -u)/${PLIST_ID}"
