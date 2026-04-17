#!/usr/bin/env bash
set -euo pipefail

OCI_BIN="${OCI_BIN:-/Users/poluovoila/bin/oci}"
CONFIG_FILE="${OCI_CLI_CONFIG_FILE:-$HOME/.oci/config}"
PROFILE="${OCI_CLI_PROFILE:-DEFAULT}"
PLIST_ID="com.personalbuffett.oracle-capacity-retry"
LOG_FILE="$HOME/Library/Logs/personal-buffett/oracle-capacity-retry.log"
ERROR_FILE="$HOME/Library/Logs/personal-buffett/oracle-capacity-retry.err.log"
INSTANCE_NAME="${INSTANCE_NAME:-personal-buffett-vm}"
OCI_AUTH_MODE="${OCI_AUTH_MODE:-}"
REGION="${OCI_REGION:-}"

config_value() {
  local key="$1"
  awk -F= -v section="[$PROFILE]" -v wanted="$key" '
    $0 == section { in_section=1; next }
    /^\[/ { in_section=0 }
    in_section {
      line=$0
      k=$1
      sub(/^[[:space:]]+|[[:space:]]+$/, "", k)
      if (k == wanted) {
        value = substr(line, index(line, "=") + 1)
        sub(/^[[:space:]]+/, "", value)
        sub(/[[:space:]]+$/, "", value)
        print value
        exit
      }
    }
  ' "$CONFIG_FILE"
}

oci_raw() {
  if [ -n "$OCI_AUTH_MODE" ]; then
    "$OCI_BIN" --profile "$PROFILE" --region "$REGION" --auth "$OCI_AUTH_MODE" "$@"
  else
    "$OCI_BIN" --profile "$PROFILE" --region "$REGION" "$@"
  fi
}

last_useful_log_line() {
  local file="$1"
  if [ -f "$file" ]; then
    awk 'NF { line=$0 } END { if (line) print line }' "$file"
  fi
}

[ -f "$CONFIG_FILE" ] || {
  echo "oracle_cli: not configured"
  exit 1
}

if [ -z "$OCI_AUTH_MODE" ] && grep -q '^security_token_file=' "$CONFIG_FILE"; then
  OCI_AUTH_MODE="security_token"
fi

if [ -z "$REGION" ]; then
  REGION="$(config_value region)"
fi

TENANCY_OCID="$(config_value tenancy)"
COMPARTMENT_ID="${OCI_COMPARTMENT_ID:-$TENANCY_OCID}"

echo "oracle_region: ${REGION}"

launchd_state="$(
  launchctl print "gui/$(id -u)/${PLIST_ID}" 2>/dev/null | awk -F'= ' '/state = / {gsub(/^[ \t]+|[ \t]+$/, "", $2); print $2; exit}'
)"
launchd_pid="$(
  launchctl print "gui/$(id -u)/${PLIST_ID}" 2>/dev/null | awk -F'= ' '/pid = / {gsub(/^[ \t]+|[ \t]+$/, "", $2); print $2; exit}'
)"
launchd_interval="$(
  launchctl print "gui/$(id -u)/${PLIST_ID}" 2>/dev/null | awk -F'= ' '/run interval = / {gsub(/^[ \t]+|[ \t]+$/, "", $2); print $2; exit}'
)"

if [ -n "${launchd_state:-}" ]; then
  if [ -n "${launchd_pid:-}" ]; then
    echo "retry_agent: ${launchd_state} (pid=${launchd_pid})"
  elif [ "${launchd_state}" = "not running" ] && [ -n "${launchd_interval:-}" ]; then
    echo "retry_agent: installed (idle; reruns every ${launchd_interval})"
  else
    echo "retry_agent: ${launchd_state}"
  fi
else
  echo "retry_agent: not installed"
fi

instance_json="$(
  oci_raw compute instance list \
    --compartment-id "$COMPARTMENT_ID" \
    --all \
    --query "data[?\"display-name\"=='${INSTANCE_NAME}' && \"lifecycle-state\"!='TERMINATED'] | [0]" \
    --output json 2>/dev/null || true
)"

instance_id="$(printf '%s' "$instance_json" | python3 - <<'PY'
import json, sys
text = sys.stdin.read().strip()
if not text:
    print("")
    raise SystemExit
try:
    data = json.loads(text)
except Exception:
    print("")
    raise SystemExit
if not data:
    print("")
    raise SystemExit
print(data.get("id", ""))
PY
)"

instance_state="$(printf '%s' "$instance_json" | python3 - <<'PY'
import json, sys
text = sys.stdin.read().strip()
if not text:
    print("")
    raise SystemExit
try:
    data = json.loads(text)
except Exception:
    print("")
    raise SystemExit
if not data:
    print("")
    raise SystemExit
print(data.get("lifecycle-state", ""))
PY
)"

instance_shape="$(printf '%s' "$instance_json" | python3 - <<'PY'
import json, sys
text = sys.stdin.read().strip()
if not text:
    print("")
    raise SystemExit
try:
    data = json.loads(text)
except Exception:
    print("")
    raise SystemExit
if not data:
    print("")
    raise SystemExit
print(data.get("shape", ""))
PY
)"

if [ -n "$instance_id" ]; then
  echo "instance: ${INSTANCE_NAME}"
  echo "instance_state: ${instance_state}"
  echo "instance_shape: ${instance_shape}"
  echo "instance_id: ${instance_id}"

  vnic_id="$(
    oci_raw compute vnic-attachment list \
      --compartment-id "$COMPARTMENT_ID" \
      --instance-id "$instance_id" \
      --query 'data[0]."vnic-id"' \
      --raw-output 2>/dev/null || true
  )"

  if [ -n "${vnic_id:-}" ] && [ "$vnic_id" != "null" ]; then
    public_ip="$(
      oci_raw network vnic get \
        --vnic-id "$vnic_id" \
        --query 'data."public-ip"' \
        --raw-output 2>/dev/null || true
    )"
    if [ -n "${public_ip:-}" ] && [ "$public_ip" != "null" ]; then
      echo "public_url: http://${public_ip}"
      echo "health_url: http://${public_ip}/healthz"
      echo "login_url: http://${public_ip}/login"
    fi
  fi
else
  echo "instance: not created yet"
fi

log_hint="$(last_useful_log_line "$LOG_FILE" || true)"
err_hint="$(last_useful_log_line "$ERROR_FILE" || true)"

if [ -n "${log_hint:-}" ]; then
  echo "last_log: ${log_hint}"
fi

if [ -n "${err_hint:-}" ]; then
  echo "last_error: ${err_hint}"
fi
