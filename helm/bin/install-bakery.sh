#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CHART_PATH="${BAKERY_CHART_PATH:-${PROJECT_ROOT}/helm}"
NAMESPACE="${BAKERY_NAMESPACE:-${POUNDCAKE_NAMESPACE:-bakery}}"
RELEASE_NAME="${BAKERY_RELEASE_NAME:-${POUNDCAKE_RELEASE_NAME:-bakery}}"
VALUES_FILE="${BAKERY_VALUES_FILE:-${POUNDCAKE_BASE_OVERRIDES:-}}"
IMAGE_TAG="${BAKERY_IMAGE_TAG:-${POUNDCAKE_BAKERY_IMAGE_TAG:-}}"
HELM_WAIT="${BAKERY_HELM_WAIT:-true}"

ACTIVE_PROVIDER="${BAKERY_ACTIVE_PROVIDER:-${POUNDCAKE_BAKERY_ACTIVE_PROVIDER:-rackspace_core}}"
UPDATE_BAKERY_SECRET="${BAKERY_UPDATE_SECRET:-${POUNDCAKE_UPDATE_BAKERY_SECRET:-false}}"

BAKERY_AUTH_SECRET_NAME="${BAKERY_AUTH_SECRET_NAME:-${POUNDCAKE_BAKERY_AUTH_SECRET_NAME:-}}"
BAKERY_HMAC_ACTIVE_KEY_ID="${BAKERY_HMAC_ACTIVE_KEY_ID:-${POUNDCAKE_BAKERY_HMAC_ACTIVE_KEY_ID:-active}}"
BAKERY_HMAC_ACTIVE_KEY="${BAKERY_HMAC_ACTIVE_KEY:-${POUNDCAKE_BAKERY_HMAC_ACTIVE_KEY:-}}"
BAKERY_HMAC_NEXT_KEY_ID="${BAKERY_HMAC_NEXT_KEY_ID:-${POUNDCAKE_BAKERY_HMAC_NEXT_KEY_ID:-}}"
BAKERY_HMAC_NEXT_KEY="${BAKERY_HMAC_NEXT_KEY:-${POUNDCAKE_BAKERY_HMAC_NEXT_KEY:-}}"

BAKERY_RACKSPACE_SECRET_NAME="${BAKERY_RACKSPACE_SECRET_NAME:-${POUNDCAKE_BAKERY_RACKSPACE_SECRET_NAME:-bakery-rackspace-core}}"
BAKERY_RACKSPACE_URL="${BAKERY_RACKSPACE_URL:-${POUNDCAKE_BAKERY_RACKSPACE_URL:-}}"
BAKERY_RACKSPACE_USERNAME="${BAKERY_RACKSPACE_USERNAME:-${POUNDCAKE_BAKERY_RACKSPACE_USERNAME:-}}"
BAKERY_RACKSPACE_PASSWORD="${BAKERY_RACKSPACE_PASSWORD:-${POUNDCAKE_BAKERY_RACKSPACE_PASSWORD:-}}"

BAKERY_SERVICENOW_SECRET_NAME="${BAKERY_SERVICENOW_SECRET_NAME:-${POUNDCAKE_BAKERY_SERVICENOW_SECRET_NAME:-bakery-servicenow}}"
BAKERY_SERVICENOW_URL="${BAKERY_SERVICENOW_URL:-${POUNDCAKE_BAKERY_SERVICENOW_URL:-}}"
BAKERY_SERVICENOW_USERNAME="${BAKERY_SERVICENOW_USERNAME:-${POUNDCAKE_BAKERY_SERVICENOW_USERNAME:-}}"
BAKERY_SERVICENOW_PASSWORD="${BAKERY_SERVICENOW_PASSWORD:-${POUNDCAKE_BAKERY_SERVICENOW_PASSWORD:-}}"

BAKERY_JIRA_SECRET_NAME="${BAKERY_JIRA_SECRET_NAME:-${POUNDCAKE_BAKERY_JIRA_SECRET_NAME:-bakery-jira}}"
BAKERY_JIRA_URL="${BAKERY_JIRA_URL:-${POUNDCAKE_BAKERY_JIRA_URL:-}}"
BAKERY_JIRA_USERNAME="${BAKERY_JIRA_USERNAME:-${POUNDCAKE_BAKERY_JIRA_USERNAME:-}}"
BAKERY_JIRA_API_TOKEN="${BAKERY_JIRA_API_TOKEN:-${POUNDCAKE_BAKERY_JIRA_API_TOKEN:-}}"

BAKERY_GITHUB_SECRET_NAME="${BAKERY_GITHUB_SECRET_NAME:-${POUNDCAKE_BAKERY_GITHUB_SECRET_NAME:-bakery-github}}"
BAKERY_GITHUB_TOKEN="${BAKERY_GITHUB_TOKEN:-${POUNDCAKE_BAKERY_GITHUB_TOKEN:-}}"

BAKERY_PAGERDUTY_SECRET_NAME="${BAKERY_PAGERDUTY_SECRET_NAME:-${POUNDCAKE_BAKERY_PAGERDUTY_SECRET_NAME:-bakery-pagerduty}}"
BAKERY_PAGERDUTY_API_KEY="${BAKERY_PAGERDUTY_API_KEY:-${POUNDCAKE_BAKERY_PAGERDUTY_API_KEY:-}}"

BAKERY_TEAMS_SECRET_NAME="${BAKERY_TEAMS_SECRET_NAME:-${POUNDCAKE_BAKERY_TEAMS_SECRET_NAME:-bakery-teams}}"
BAKERY_TEAMS_WEBHOOK_URL="${BAKERY_TEAMS_WEBHOOK_URL:-${POUNDCAKE_BAKERY_TEAMS_WEBHOOK_URL:-}}"

BAKERY_DISCORD_SECRET_NAME="${BAKERY_DISCORD_SECRET_NAME:-${POUNDCAKE_BAKERY_DISCORD_SECRET_NAME:-bakery-discord}}"
BAKERY_DISCORD_WEBHOOK_URL="${BAKERY_DISCORD_WEBHOOK_URL:-${POUNDCAKE_BAKERY_DISCORD_WEBHOOK_URL:-}}"

FORWARD_ARGS=()

log_info() {
  echo "[INFO] $*" >&2
}

log_error() {
  echo "[ERROR] $*" >&2
}

usage() {
  cat <<'USAGE'
Usage:
  install-bakery.sh [bakery secret options] [helm args]

Supported secret flags:
  --bakery-active-provider <provider>
  --bakery-auth-secret-name <name>
  --bakery-rackspace-secret-name <name>
  --bakery-rackspace-url <url>
  --bakery-rackspace-username <username>
  --bakery-rackspace-password <password>
  --bakery-servicenow-secret-name <name>
  --bakery-servicenow-url <url>
  --bakery-servicenow-username <username>
  --bakery-servicenow-password <password>
  --bakery-jira-secret-name <name>
  --bakery-jira-url <url>
  --bakery-jira-username <username>
  --bakery-jira-api-token <token>
  --bakery-github-secret-name <name>
  --bakery-github-token <token>
  --bakery-pagerduty-secret-name <name>
  --bakery-pagerduty-api-key <key>
  --bakery-teams-secret-name <name>
  --bakery-teams-webhook-url <url>
  --bakery-discord-secret-name <name>
  --bakery-discord-webhook-url <url>
  --update-bakery-secret

All other arguments are forwarded to helm upgrade --install.
USAGE
}

normalize_bool() {
  local value="${1:-}"
  value="$(printf '%s' "${value}" | tr '[:upper:]' '[:lower:]')"
  case "${value}" in
    true|1|yes|on) echo "true" ;;
    false|0|no|off|"") echo "false" ;;
    *)
      log_error "Unsupported boolean value: ${value}"
      exit 1
      ;;
  esac
}

default_auth_secret_name() {
  local release_name="$1"
  local fullname=""
  local secret_name=""

  if [[ "${release_name}" == *bakery* ]]; then
    fullname="${release_name}"
  else
    fullname="${release_name}-bakery"
  fi
  fullname="${fullname:0:63}"
  fullname="${fullname%-}"
  secret_name="${fullname}-secret"
  secret_name="${secret_name:0:63}"
  secret_name="${secret_name%-}"
  printf '%s\n' "${secret_name}"
}

ensure_namespace_exists() {
  if ! kubectl get namespace "${NAMESPACE}" >/dev/null 2>&1; then
    log_info "Creating namespace ${NAMESPACE}"
    kubectl create namespace "${NAMESPACE}" >/dev/null
  fi
}

secret_exists() {
  kubectl -n "${NAMESPACE}" get secret "$1" >/dev/null 2>&1
}

generate_hmac_key() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 32
    return
  fi
  od -An -N32 -tx1 /dev/urandom | tr -d ' \n'
}

apply_secret() {
  local secret_name="$1"
  shift
  kubectl -n "${NAMESPACE}" create secret generic "${secret_name}" "$@" --dry-run=client -o yaml | kubectl apply -f -
}

ensure_auth_secret() {
  local secret_name="${BAKERY_AUTH_SECRET_NAME}"
  local provided_material="false"

  if [[ -z "${secret_name}" ]]; then
    secret_name="$(default_auth_secret_name "${RELEASE_NAME}")"
  fi
  BAKERY_AUTH_SECRET_NAME="${secret_name}"

  if [[ -n "${BAKERY_HMAC_ACTIVE_KEY}" || -n "${BAKERY_HMAC_NEXT_KEY}" ]]; then
    provided_material="true"
  fi

  if secret_exists "${secret_name}" && [[ "${provided_material}" == "true" ]] && [[ "$(normalize_bool "${UPDATE_BAKERY_SECRET}")" != "true" ]]; then
    log_error "Bakery auth secret ${secret_name} already exists. Use --update-bakery-secret to rotate keys."
    exit 1
  fi

  if secret_exists "${secret_name}" && [[ "$(normalize_bool "${UPDATE_BAKERY_SECRET}")" != "true" ]]; then
    log_info "Using existing Bakery auth secret ${secret_name}"
    return
  fi

  if [[ -z "${BAKERY_HMAC_ACTIVE_KEY}" ]]; then
    BAKERY_HMAC_ACTIVE_KEY="$(generate_hmac_key)"
  fi

  log_info "Applying Bakery auth secret ${secret_name}"
  apply_secret "${secret_name}" \
    --from-literal=active-key-id="${BAKERY_HMAC_ACTIVE_KEY_ID}" \
    --from-literal=active-key="${BAKERY_HMAC_ACTIVE_KEY}" \
    ${BAKERY_HMAC_NEXT_KEY_ID:+--from-literal=next-key-id="${BAKERY_HMAC_NEXT_KEY_ID}"} \
    ${BAKERY_HMAC_NEXT_KEY:+--from-literal=next-key="${BAKERY_HMAC_NEXT_KEY}"}
}

ensure_provider_secret() {
  local provider="$1"
  local secret_name=""
  local value_args=()
  local provided="false"

  case "${provider}" in
    rackspace_core)
      secret_name="${BAKERY_RACKSPACE_SECRET_NAME}"
      [[ -n "${BAKERY_RACKSPACE_URL}${BAKERY_RACKSPACE_USERNAME}${BAKERY_RACKSPACE_PASSWORD}" ]] && provided="true"
      value_args=(
        --from-literal=rackspace-core-url="${BAKERY_RACKSPACE_URL}"
        --from-literal=rackspace-core-username="${BAKERY_RACKSPACE_USERNAME}"
        --from-literal=rackspace-core-password="${BAKERY_RACKSPACE_PASSWORD}"
      )
      ;;
    servicenow)
      secret_name="${BAKERY_SERVICENOW_SECRET_NAME}"
      [[ -n "${BAKERY_SERVICENOW_URL}${BAKERY_SERVICENOW_USERNAME}${BAKERY_SERVICENOW_PASSWORD}" ]] && provided="true"
      value_args=(
        --from-literal=servicenow-url="${BAKERY_SERVICENOW_URL}"
        --from-literal=servicenow-username="${BAKERY_SERVICENOW_USERNAME}"
        --from-literal=servicenow-password="${BAKERY_SERVICENOW_PASSWORD}"
      )
      ;;
    jira)
      secret_name="${BAKERY_JIRA_SECRET_NAME}"
      [[ -n "${BAKERY_JIRA_URL}${BAKERY_JIRA_USERNAME}${BAKERY_JIRA_API_TOKEN}" ]] && provided="true"
      value_args=(
        --from-literal=jira-url="${BAKERY_JIRA_URL}"
        --from-literal=jira-username="${BAKERY_JIRA_USERNAME}"
        --from-literal=jira-api-token="${BAKERY_JIRA_API_TOKEN}"
      )
      ;;
    github)
      secret_name="${BAKERY_GITHUB_SECRET_NAME}"
      [[ -n "${BAKERY_GITHUB_TOKEN}" ]] && provided="true"
      value_args=(--from-literal=github-token="${BAKERY_GITHUB_TOKEN}")
      ;;
    pagerduty)
      secret_name="${BAKERY_PAGERDUTY_SECRET_NAME}"
      [[ -n "${BAKERY_PAGERDUTY_API_KEY}" ]] && provided="true"
      value_args=(--from-literal=pagerduty-api-key="${BAKERY_PAGERDUTY_API_KEY}")
      ;;
    teams)
      secret_name="${BAKERY_TEAMS_SECRET_NAME}"
      [[ -n "${BAKERY_TEAMS_WEBHOOK_URL}" ]] && provided="true"
      value_args=(--from-literal=teams-webhook-url="${BAKERY_TEAMS_WEBHOOK_URL}")
      ;;
    discord)
      secret_name="${BAKERY_DISCORD_SECRET_NAME}"
      [[ -n "${BAKERY_DISCORD_WEBHOOK_URL}" ]] && provided="true"
      value_args=(--from-literal=discord-webhook-url="${BAKERY_DISCORD_WEBHOOK_URL}")
      ;;
    *)
      log_error "Unsupported provider: ${provider}"
      exit 1
      ;;
  esac

  if secret_exists "${secret_name}" && [[ "${provided}" == "true" ]] && [[ "$(normalize_bool "${UPDATE_BAKERY_SECRET}")" != "true" ]]; then
    log_error "Secret ${secret_name} already exists. Use --update-bakery-secret to rotate provider credentials."
    exit 1
  fi

  if secret_exists "${secret_name}" && [[ "$(normalize_bool "${UPDATE_BAKERY_SECRET}")" != "true" ]]; then
    log_info "Using existing ${provider} secret ${secret_name}"
    printf '%s\n' "${secret_name}"
    return
  fi

  if [[ "${provided}" != "true" ]]; then
    log_error "Active provider ${provider} requires credentials or an existing secret."
    exit 1
  fi

  log_info "Applying ${provider} secret ${secret_name}"
  apply_secret "${secret_name}" "${value_args[@]}"
  printf '%s\n' "${secret_name}"
}

provider_values_path() {
  case "$1" in
    rackspace_core) printf '%s\n' "bakery.rackspaceCore.existingSecret" ;;
    servicenow) printf '%s\n' "bakery.servicenow.existingSecret" ;;
    jira) printf '%s\n' "bakery.jira.existingSecret" ;;
    github) printf '%s\n' "bakery.github.existingSecret" ;;
    pagerduty) printf '%s\n' "bakery.pagerduty.existingSecret" ;;
    teams) printf '%s\n' "bakery.teams.existingSecret" ;;
    discord) printf '%s\n' "bakery.discord.existingSecret" ;;
    *)
      log_error "Unsupported provider: $1"
      exit 1
      ;;
  esac
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --bakery-active-provider) ACTIVE_PROVIDER="$2"; shift 2 ;;
      --bakery-auth-secret-name) BAKERY_AUTH_SECRET_NAME="$2"; shift 2 ;;
      --bakery-rackspace-secret-name) BAKERY_RACKSPACE_SECRET_NAME="$2"; shift 2 ;;
      --bakery-rackspace-url) BAKERY_RACKSPACE_URL="$2"; shift 2 ;;
      --bakery-rackspace-username) BAKERY_RACKSPACE_USERNAME="$2"; shift 2 ;;
      --bakery-rackspace-password) BAKERY_RACKSPACE_PASSWORD="$2"; shift 2 ;;
      --bakery-servicenow-secret-name) BAKERY_SERVICENOW_SECRET_NAME="$2"; shift 2 ;;
      --bakery-servicenow-url) BAKERY_SERVICENOW_URL="$2"; shift 2 ;;
      --bakery-servicenow-username) BAKERY_SERVICENOW_USERNAME="$2"; shift 2 ;;
      --bakery-servicenow-password) BAKERY_SERVICENOW_PASSWORD="$2"; shift 2 ;;
      --bakery-jira-secret-name) BAKERY_JIRA_SECRET_NAME="$2"; shift 2 ;;
      --bakery-jira-url) BAKERY_JIRA_URL="$2"; shift 2 ;;
      --bakery-jira-username) BAKERY_JIRA_USERNAME="$2"; shift 2 ;;
      --bakery-jira-api-token) BAKERY_JIRA_API_TOKEN="$2"; shift 2 ;;
      --bakery-github-secret-name) BAKERY_GITHUB_SECRET_NAME="$2"; shift 2 ;;
      --bakery-github-token) BAKERY_GITHUB_TOKEN="$2"; shift 2 ;;
      --bakery-pagerduty-secret-name) BAKERY_PAGERDUTY_SECRET_NAME="$2"; shift 2 ;;
      --bakery-pagerduty-api-key) BAKERY_PAGERDUTY_API_KEY="$2"; shift 2 ;;
      --bakery-teams-secret-name) BAKERY_TEAMS_SECRET_NAME="$2"; shift 2 ;;
      --bakery-teams-webhook-url) BAKERY_TEAMS_WEBHOOK_URL="$2"; shift 2 ;;
      --bakery-discord-secret-name) BAKERY_DISCORD_SECRET_NAME="$2"; shift 2 ;;
      --bakery-discord-webhook-url) BAKERY_DISCORD_WEBHOOK_URL="$2"; shift 2 ;;
      --update-bakery-secret) UPDATE_BAKERY_SECRET="true"; shift ;;
      -h|--help) usage; exit 0 ;;
      *)
        FORWARD_ARGS+=("$1")
        shift
        ;;
    esac
  done
}

main() {
  parse_args "$@"
  ensure_namespace_exists
  ensure_auth_secret

  local provider_secret_name
  local provider_values_key
  provider_secret_name="$(ensure_provider_secret "${ACTIVE_PROVIDER}")"
  provider_values_key="$(provider_values_path "${ACTIVE_PROVIDER}")"

  local helm_cmd=(
    helm upgrade --install "${RELEASE_NAME}" "${CHART_PATH}"
    --namespace "${NAMESPACE}"
    --create-namespace
    --set bakery.enabled=true
    --set-string "bakery.config.activeProvider=${ACTIVE_PROVIDER}"
    --set-string "bakery.auth.existingSecret=${BAKERY_AUTH_SECRET_NAME}"
    --set-string "${provider_values_key}=${provider_secret_name}"
  )

  if [[ -n "${VALUES_FILE}" ]]; then
    helm_cmd+=(-f "${VALUES_FILE}")
  fi
  if [[ -n "${IMAGE_TAG}" ]]; then
    helm_cmd+=(--set-string "bakery.image.tag=${IMAGE_TAG}")
  fi
  if [[ "$(normalize_bool "${HELM_WAIT}")" == "true" ]]; then
    helm_cmd+=(--wait)
  fi
  if ((${#FORWARD_ARGS[@]} > 0)); then
    helm_cmd+=("${FORWARD_ARGS[@]}")
  fi

  log_info "Installing Bakery release ${RELEASE_NAME} into namespace ${NAMESPACE}"
  "${helm_cmd[@]}"
}

main "$@"
