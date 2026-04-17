#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OCI_BIN="${OCI_BIN:-/Users/poluovoila/bin/oci}"
CONFIG_FILE="${OCI_CLI_CONFIG_FILE:-$HOME/.oci/config}"
PROFILE="${OCI_CLI_PROFILE:-DEFAULT}"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"
TEMPLATE_FILE="$ROOT_DIR/deploy/oracle/cloud-init.yaml.tmpl"
RENDERED_CLOUD_INIT="$(mktemp "${TMPDIR:-/tmp}/personal-buffett-cloud-init.XXXXXX.yaml")"
APP_NAME="${APP_NAME:-personal-buffett}"
INSTANCE_NAME="${INSTANCE_NAME:-personal-buffett-vm}"
VCN_NAME="${VCN_NAME:-personal-buffett-vcn}"
SUBNET_NAME="${SUBNET_NAME:-personal-buffett-subnet}"
SECURITY_LIST_NAME="${SECURITY_LIST_NAME:-personal-buffett-sl}"
INTERNET_GATEWAY_NAME="${INTERNET_GATEWAY_NAME:-personal-buffett-ig}"
REGION="${OCI_REGION:-}"
VCN_CIDR="${OCI_VCN_CIDR:-10.0.0.0/16}"
SUBNET_CIDR="${OCI_SUBNET_CIDR:-10.0.0.0/24}"
SHAPE="${OCI_SHAPE:-VM.Standard.A1.Flex}"
OCPUS="${OCI_OCPUS:-1}"
MEMORY_GB="${OCI_MEMORY_GB:-6}"
BOOT_VOLUME_GB="${OCI_BOOT_VOLUME_GB:-50}"
SSH_PUBLIC_KEY_FILE="${SSH_PUBLIC_KEY_FILE:-$HOME/.ssh/personal_buffett_oracle.pub}"
IMAGE_TAG="${IMAGE_TAG:-codex-pbc-refactor}"
IMAGE="ghcr.io/sodawaitress/personal-buffett:${IMAGE_TAG}"

log() {
  printf '[oracle-deploy] %s\n' "$*"
}

die() {
  printf '[oracle-deploy] ERROR: %s\n' "$*" >&2
  exit 1
}

cleanup() {
  rm -f "$RENDERED_CLOUD_INIT"
}
trap cleanup EXIT

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

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
  "$OCI_BIN" --profile "$PROFILE" --region "$REGION" "$@"
}

render_cloud_init() {
  while IFS= read -r line; do
    case "$line" in
      "__ENV_BLOCK__")
        printf '%s\n' "$ENV_BLOCK"
        ;;
      *)
        printf '%s\n' "${line//__IMAGE__/$IMAGE}"
        ;;
    esac
  done < "$TEMPLATE_FILE" > "$RENDERED_CLOUD_INIT"
}

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

require_cmd "$OCI_BIN"
require_cmd openssl

[ -f "$CONFIG_FILE" ] || die "OCI config not found: $CONFIG_FILE"
[ -f "$SSH_PUBLIC_KEY_FILE" ] || die "SSH public key not found: $SSH_PUBLIC_KEY_FILE"
[ -f "$TEMPLATE_FILE" ] || die "cloud-init template not found: $TEMPLATE_FILE"

TENANCY_OCID="${OCI_TENANCY_OCID:-$(config_value tenancy)}"
[ -n "$TENANCY_OCID" ] || die "could not read tenancy from $CONFIG_FILE profile $PROFILE"

if [ -z "$REGION" ]; then
  REGION="$(config_value region)"
fi
[ -n "$REGION" ] || die "set OCI_REGION or configure region in $CONFIG_FILE"

COMPARTMENT_ID="${OCI_COMPARTMENT_ID:-$TENANCY_OCID}"

: "${GROQ_API_KEY:?need GROQ_API_KEY in env or .env}"
FLASK_SECRET_KEY="${FLASK_SECRET_KEY:-$(openssl rand -hex 32)}"
RADAR_DB_PATH="${RADAR_DB_PATH:-/data/radar.db}"
FLASK_DEBUG="${FLASK_DEBUG:-0}"

EXISTING_INSTANCE_ID="$(
  oci_raw compute instance list --compartment-id "$COMPARTMENT_ID" --all \
    --query "data[?\"display-name\"=='${INSTANCE_NAME}' && \"lifecycle-state\"!='TERMINATED'] | [0].id" \
    --raw-output 2>/dev/null || true
)"

if [ -n "$EXISTING_INSTANCE_ID" ] && [ "$EXISTING_INSTANCE_ID" != "null" ]; then
  log "instance already exists: $INSTANCE_NAME"
  EXISTING_VNIC_ID="$(
    oci_raw compute vnic-attachment list --compartment-id "$COMPARTMENT_ID" --instance-id "$EXISTING_INSTANCE_ID" \
      --query 'data[0]."vnic-id"' --raw-output
  )"
  EXISTING_PUBLIC_IP="$(
    oci_raw network vnic get --vnic-id "$EXISTING_VNIC_ID" \
      --query 'data."public-ip"' --raw-output
  )"
  log "reuse IP: http://${EXISTING_PUBLIC_IP}"
  exit 0
fi

log "using region: $REGION"
log "using image: $IMAGE"

VCN_ID="$(
  oci_raw network vcn list --compartment-id "$COMPARTMENT_ID" --all \
    --query "data[?\"display-name\"=='${VCN_NAME}'] | [0].id" \
    --raw-output 2>/dev/null || true
)"
if [ -z "$VCN_ID" ] || [ "$VCN_ID" = "null" ]; then
  log "creating VCN"
  VCN_ID="$(
    oci_raw network vcn create \
      --compartment-id "$COMPARTMENT_ID" \
      --display-name "$VCN_NAME" \
      --cidr-block "$VCN_CIDR" \
      --query 'data.id' --raw-output
  )"
  ROUTE_TABLE_ID="$(
    oci_raw network vcn get --vcn-id "$VCN_ID" \
      --query 'data."default-route-table-id"' --raw-output
  )"
else
  log "reusing VCN"
  ROUTE_TABLE_ID="$(
    oci_raw network vcn get --vcn-id "$VCN_ID" \
      --query 'data."default-route-table-id"' --raw-output
  )"
fi

[ -n "$VCN_ID" ] || die "failed to get VCN ID"
[ -n "$ROUTE_TABLE_ID" ] || die "failed to get route table ID"

INTERNET_GATEWAY_ID="$(
  oci_raw network internet-gateway list --compartment-id "$COMPARTMENT_ID" --all \
    --query "data[?\"display-name\"=='${INTERNET_GATEWAY_NAME}'] | [0].id" \
    --raw-output 2>/dev/null || true
)"

if [ -z "$INTERNET_GATEWAY_ID" ] || [ "$INTERNET_GATEWAY_ID" = "null" ]; then
  log "creating Internet Gateway"
  INTERNET_GATEWAY_ID="$(
    oci_raw network internet-gateway create \
      --compartment-id "$COMPARTMENT_ID" \
      --display-name "$INTERNET_GATEWAY_NAME" \
      --is-enabled true \
      --vcn-id "$VCN_ID" \
      --query 'data.id' --raw-output
  )"
fi

log "configuring route table"
oci_raw network route-table update \
  --rt-id "$ROUTE_TABLE_ID" \
  --force \
  --route-rules "[{\"cidrBlock\":\"0.0.0.0/0\",\"networkEntityId\":\"${INTERNET_GATEWAY_ID}\"}]"

SECURITY_LIST_ID="$(
  oci_raw network security-list list --compartment-id "$COMPARTMENT_ID" --all \
    --query "data[?\"display-name\"=='${SECURITY_LIST_NAME}'] | [0].id" \
    --raw-output 2>/dev/null || true
)"

if [ -z "$SECURITY_LIST_ID" ] || [ "$SECURITY_LIST_ID" = "null" ]; then
  log "creating security list"
  SECURITY_LIST_ID="$(
    oci_raw network security-list create \
      --compartment-id "$COMPARTMENT_ID" \
      --display-name "$SECURITY_LIST_NAME" \
      --vcn-id "$VCN_ID" \
      --egress-security-rules '[{"destination":"0.0.0.0/0","protocol":"all"}]' \
      --ingress-security-rules '[{"protocol":"6","source":"0.0.0.0/0","tcpOptions":{"destinationPortRange":{"min":22,"max":22}}},{"protocol":"6","source":"0.0.0.0/0","tcpOptions":{"destinationPortRange":{"min":80,"max":80}}}]' \
      --query 'data.id' --raw-output
  )"
fi

SUBNET_ID="$(
  oci_raw network subnet list --compartment-id "$COMPARTMENT_ID" --all \
    --query "data[?\"display-name\"=='${SUBNET_NAME}'] | [0].id" \
    --raw-output 2>/dev/null || true
)"

if [ -z "$SUBNET_ID" ] || [ "$SUBNET_ID" = "null" ]; then
  log "creating subnet"
  SUBNET_ID="$(
    oci_raw network subnet create \
      --compartment-id "$COMPARTMENT_ID" \
      --display-name "$SUBNET_NAME" \
      --cidr-block "$SUBNET_CIDR" \
      --vcn-id "$VCN_ID" \
      --route-table-id "$ROUTE_TABLE_ID" \
      --security-list-ids "[\"${SECURITY_LIST_ID}\"]" \
      --prohibit-public-ip-on-vnic false \
      --query 'data.id' --raw-output
  )"
fi

AVAILABILITY_DOMAIN="$(
  oci_raw iam availability-domain list --compartment-id "$TENANCY_OCID" \
    --query 'data[0].name' --raw-output
)"
[ -n "$AVAILABILITY_DOMAIN" ] || die "failed to get availability domain"

IMAGE_ID="$(
  oci_raw compute image list --all \
    --compartment-id "$TENANCY_OCID" \
    --operating-system "Canonical Ubuntu" \
    --operating-system-version "24.04" \
    --shape "$SHAPE" \
    --sort-by TIMECREATED \
    --sort-order DESC \
    --query 'data[0].id' --raw-output 2>/dev/null || true
)"

if [ -z "$IMAGE_ID" ] || [ "$IMAGE_ID" = "null" ]; then
  IMAGE_ID="$(
    oci_raw compute image list --all \
      --compartment-id "$TENANCY_OCID" \
      --operating-system "Canonical Ubuntu" \
      --operating-system-version "22.04" \
      --shape "$SHAPE" \
      --sort-by TIMECREATED \
      --sort-order DESC \
      --query 'data[0].id' --raw-output
  )"
fi
[ -n "$IMAGE_ID" ] || die "failed to find Ubuntu image for shape $SHAPE"

ENV_BLOCK="$(cat <<EOF
      FLASK_SECRET_KEY=$FLASK_SECRET_KEY
      GROQ_API_KEY=$GROQ_API_KEY
      RADAR_DB_PATH=$RADAR_DB_PATH
      FLASK_DEBUG=$FLASK_DEBUG
EOF
)"

if [ -n "${GOOGLE_CLIENT_ID:-}" ]; then
  ENV_BLOCK="${ENV_BLOCK}"$'\n'"      GOOGLE_CLIENT_ID=$GOOGLE_CLIENT_ID"
fi

if [ -n "${GOOGLE_CLIENT_SECRET:-}" ]; then
  ENV_BLOCK="${ENV_BLOCK}"$'\n'"      GOOGLE_CLIENT_SECRET=$GOOGLE_CLIENT_SECRET"
fi

render_cloud_init

log "launching instance"
INSTANCE_ID="$(
  oci_raw compute instance launch \
    --availability-domain "$AVAILABILITY_DOMAIN" \
    --compartment-id "$COMPARTMENT_ID" \
    --display-name "$INSTANCE_NAME" \
    --shape "$SHAPE" \
    --shape-config "{\"ocpus\":${OCPUS},\"memoryInGBs\":${MEMORY_GB}}" \
    --subnet-id "$SUBNET_ID" \
    --assign-public-ip true \
    --image-id "$IMAGE_ID" \
    --boot-volume-size-in-gbs "$BOOT_VOLUME_GB" \
    --ssh-authorized-keys-file "$SSH_PUBLIC_KEY_FILE" \
    --user-data-file "$RENDERED_CLOUD_INIT" \
    --query 'data.id' --raw-output
)"

[ -n "$INSTANCE_ID" ] || die "instance launch failed"

log "waiting for instance to be RUNNING"
oci_raw compute instance get --instance-id "$INSTANCE_ID" --wait-for-state RUNNING >/dev/null

VNIC_ID="$(
  oci_raw compute vnic-attachment list --compartment-id "$COMPARTMENT_ID" --instance-id "$INSTANCE_ID" \
    --query 'data[0]."vnic-id"' --raw-output
)"
[ -n "$VNIC_ID" ] || die "failed to get VNIC ID"

PUBLIC_IP="$(
  oci_raw network vnic get --vnic-id "$VNIC_ID" \
    --query 'data."public-ip"' --raw-output
)"
[ -n "$PUBLIC_IP" ] || die "failed to get public IP"

log "done"
printf '\n'
printf 'Instance ID: %s\n' "$INSTANCE_ID"
printf 'Public URL: http://%s\n' "$PUBLIC_IP"
printf 'Health URL: http://%s/healthz\n' "$PUBLIC_IP"
printf 'Login URL:  http://%s/login\n' "$PUBLIC_IP"
printf 'SSH:        ssh -i %s ubuntu@%s\n' "$SSH_PUBLIC_KEY_FILE" "$PUBLIC_IP"
