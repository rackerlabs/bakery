#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="${BAKERY_NAMESPACE:-bakery}"
RELEASE_NAME="${BAKERY_RELEASE_NAME:-bakery}"
VALUES_FILE="${BAKERY_VALUES_FILE:-}"
DEFAULT_OVERRIDES_DIR="${BAKERY_DEFAULT_OVERRIDES_DIR:-/etc/genestack/helm-configs/bakery}"
if [[ "${BAKERY_OVERRIDES_DIR+set}" == "set" ]]; then
  OVERRIDES_DIR="${BAKERY_OVERRIDES_DIR}"
else
  OVERRIDES_DIR="${DEFAULT_OVERRIDES_DIR}"
fi
VERSION_FILE="${BAKERY_VERSION_FILE:-/etc/genestack/helm-chart-versions.yaml}"
IMAGE_TAG="${BAKERY_IMAGE_TAG:-}"
HELM_WAIT="${BAKERY_HELM_WAIT:-true}"

ACTIVE_PROVIDER="${BAKERY_ACTIVE_PROVIDER:-}"
UPDATE_BAKERY_SECRET="${BAKERY_UPDATE_SECRET:-false}"

BAKERY_AUTH_SECRET_NAME="${BAKERY_AUTH_SECRET_NAME:-}"
BAKERY_HMAC_ACTIVE_KEY_ID="${BAKERY_HMAC_ACTIVE_KEY_ID:-active}"
BAKERY_HMAC_ACTIVE_KEY="${BAKERY_HMAC_ACTIVE_KEY:-}"
BAKERY_HMAC_NEXT_KEY_ID="${BAKERY_HMAC_NEXT_KEY_ID:-}"
BAKERY_HMAC_NEXT_KEY="${BAKERY_HMAC_NEXT_KEY:-}"

BAKERY_RACKSPACE_SECRET_NAME="${BAKERY_RACKSPACE_SECRET_NAME:-}"
BAKERY_RACKSPACE_URL="${BAKERY_RACKSPACE_URL:-}"
BAKERY_RACKSPACE_USERNAME="${BAKERY_RACKSPACE_USERNAME:-}"
BAKERY_RACKSPACE_PASSWORD="${BAKERY_RACKSPACE_PASSWORD:-}"

BAKERY_SERVICENOW_SECRET_NAME="${BAKERY_SERVICENOW_SECRET_NAME:-}"
BAKERY_SERVICENOW_URL="${BAKERY_SERVICENOW_URL:-}"
BAKERY_SERVICENOW_USERNAME="${BAKERY_SERVICENOW_USERNAME:-}"
BAKERY_SERVICENOW_PASSWORD="${BAKERY_SERVICENOW_PASSWORD:-}"

BAKERY_JIRA_SECRET_NAME="${BAKERY_JIRA_SECRET_NAME:-}"
BAKERY_JIRA_URL="${BAKERY_JIRA_URL:-}"
BAKERY_JIRA_USERNAME="${BAKERY_JIRA_USERNAME:-}"
BAKERY_JIRA_API_TOKEN="${BAKERY_JIRA_API_TOKEN:-}"

BAKERY_GITHUB_SECRET_NAME="${BAKERY_GITHUB_SECRET_NAME:-}"
BAKERY_GITHUB_TOKEN="${BAKERY_GITHUB_TOKEN:-}"

BAKERY_PAGERDUTY_SECRET_NAME="${BAKERY_PAGERDUTY_SECRET_NAME:-}"
BAKERY_PAGERDUTY_API_KEY="${BAKERY_PAGERDUTY_API_KEY:-}"

BAKERY_TEAMS_SECRET_NAME="${BAKERY_TEAMS_SECRET_NAME:-}"
BAKERY_TEAMS_WEBHOOK_URL="${BAKERY_TEAMS_WEBHOOK_URL:-}"

BAKERY_DISCORD_SECRET_NAME="${BAKERY_DISCORD_SECRET_NAME:-}"
BAKERY_DISCORD_WEBHOOK_URL="${BAKERY_DISCORD_WEBHOOK_URL:-}"

FORWARD_ARGS=()
ARG_VALUES_FILES=()
VALUES_FILES=()

log_info() {
  echo "[INFO] $*" >&2
}

log_error() {
  echo "[ERROR] $*" >&2
}

if [[ "${BAKERY_CHART_VERSION+set}" == "set" ]]; then
  CHART_VERSION="${BAKERY_CHART_VERSION}"
else
  CHART_VERSION=""
fi
CHART_REF="${BAKERY_CHART_REF:-oci://ghcr.io/rackerlabs/charts/bakery}"

usage() {
  cat <<'USAGE'
Usage:
  install-bakery.sh [bakery secret options] [helm args]

Supported installer flags:
  --bakery-chart-ref <oci-ref>
  --bakery-chart-version <version>
  --bakery-overrides-dir <path>
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

The installer auto-loads extra values files from
`/etc/genestack/helm-configs/bakery` when that directory exists. Set
`BAKERY_OVERRIDES_DIR` or pass `--bakery-overrides-dir` to use a different
directory.

When `BAKERY_CHART_VERSION` / `--bakery-chart-version` is not set, the
installer reads the `bakery` chart version from
`/etc/genestack/helm-chart-versions.yaml`. Set `BAKERY_VERSION_FILE` to use a
different version file.

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

get_chart_version_from_file() {
  local version_file="$1"
  local chart_name="$2"
  local resolved_version=""

  resolved_version="$(
    awk -v chart="${chart_name}" '
      BEGIN { in_charts = 0 }
      /^[[:space:]]*charts:[[:space:]]*$/ { in_charts = 1; next }
      in_charts == 1 {
        if ($0 ~ /^[^[:space:]]/) { in_charts = 0; next }
        line = $0
        sub(/^[[:space:]]+/, "", line)
        if (line ~ ("^" chart ":[[:space:]]*")) {
          sub("^" chart ":[[:space:]]*", "", line)
          gsub(/[[:space:]]*$/, "", line)
          print line
          exit
        }
      }
    ' "${version_file}" | head -n1
  )"

  if [[ -n "${resolved_version}" ]]; then
    printf '%s\n' "${resolved_version}"
    return 0
  fi

  resolved_version="$(
    grep -E "^[[:space:]]*${chart_name}:[[:space:]]*" "${version_file}" | head -n1 | sed -E "s/^[[:space:]]*${chart_name}:[[:space:]]*//"
  )"
  if [[ -n "${resolved_version}" ]]; then
    printf '%s\n' "${resolved_version}"
    return 0
  fi

  return 1
}

resolve_chart_version() {
  if [[ -n "${CHART_VERSION}" ]]; then
    return 0
  fi

  if [[ ! -f "${VERSION_FILE}" ]]; then
    log_error "Chart version file not found at ${VERSION_FILE}. Set BAKERY_CHART_VERSION or create ${VERSION_FILE} with a bakery entry."
    exit 1
  fi

  if ! CHART_VERSION="$(get_chart_version_from_file "${VERSION_FILE}" "bakery")"; then
    log_error "Could not resolve the bakery chart version from ${VERSION_FILE}. Set BAKERY_CHART_VERSION or add a bakery entry."
    exit 1
  fi
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

default_provider_secret_name() {
  case "$1" in
    rackspace_core) printf '%s\n' "bakery-rackspace-core" ;;
    servicenow) printf '%s\n' "bakery-servicenow" ;;
    jira) printf '%s\n' "bakery-jira" ;;
    github) printf '%s\n' "bakery-github" ;;
    pagerduty) printf '%s\n' "bakery-pagerduty" ;;
    teams) printf '%s\n' "bakery-teams" ;;
    discord) printf '%s\n' "bakery-discord" ;;
    *)
      log_error "Unsupported provider: $1"
      exit 1
      ;;
  esac
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

append_values_file() {
  local values_file="$1"
  local existing_file=""

  [[ -n "${values_file}" ]] || return 0

  if ((${#VALUES_FILES[@]} > 0)); then
    for existing_file in "${VALUES_FILES[@]}"; do
      if [[ "${existing_file}" == "${values_file}" ]]; then
        return 0
      fi
    done
  fi

  VALUES_FILES+=("${values_file}")
}

collect_values_files() {
  local discovered_file=""
  local arg_values_file=""

  VALUES_FILES=()

  if [[ -n "${VALUES_FILE}" ]]; then
    append_values_file "${VALUES_FILE}"
  fi

  if [[ -d "${OVERRIDES_DIR}" ]]; then
    while IFS= read -r discovered_file; do
      append_values_file "${discovered_file}"
    done < <(find "${OVERRIDES_DIR}" -maxdepth 1 -type f \( -name '*.yaml' -o -name '*.yml' \) | sort)
  fi

  if ((${#ARG_VALUES_FILES[@]} > 0)); then
    for arg_values_file in "${ARG_VALUES_FILES[@]}"; do
      append_values_file "${arg_values_file}"
    done
  fi
}

yaml_value_from_file() {
  local path="$1"
  local file="$2"

  awk -v want="${path}" '
    BEGIN {
      depth = split(want, parts, ".")
      found = 0
      result = ""
    }

    /^[[:space:]]*#/ { next }
    /^[[:space:]]*$/ { next }

    {
      line = $0
      indent = 0

      while (substr(line, 1, 1) == " ") {
        indent++
        line = substr(line, 2)
      }

      if (line !~ /^[A-Za-z0-9_-]+:/) {
        next
      }

      key = line
      sub(/:.*/, "", key)
      value = line
      sub(/^[^:]+:[[:space:]]*/, "", value)
      if (line ~ /^[^:]+:[[:space:]]*$/) {
        value = ""
      }
      level = int(indent / 2)

      keys[level] = key
      for (i = level + 1; i < 32; i++) {
        delete keys[i]
      }

      if (level + 1 != depth) {
        next
      }

      matched = 1
      for (i = 1; i <= depth; i++) {
        if (!(i - 1 in keys) || keys[i - 1] != parts[i]) {
          matched = 0
          break
        }
      }

      if (!matched) {
        next
      }

      sub(/[[:space:]]+#.*$/, "", value)
      gsub(/^[[:space:]]+/, "", value)
      gsub(/[[:space:]]+$/, "", value)

      if (value ~ /^".*"$/ || value ~ /^'\''.*'\''$/) {
        value = substr(value, 2, length(value) - 2)
      }

      found = 1
      result = value
    }

    END {
      if (found) {
        print result
        exit 0
      }
      exit 1
    }
  ' "${file}"
}

merged_yaml_value() {
  local path="$1"
  local current_value=""
  local merged_value=""
  local values_file=""
  local found="false"

  if ((${#VALUES_FILES[@]} > 0)); then
    for values_file in "${VALUES_FILES[@]}"; do
      if current_value="$(yaml_value_from_file "${path}" "${values_file}")"; then
        merged_value="${current_value}"
        found="true"
      fi
    done
  fi

  if [[ "${found}" == "true" ]]; then
    printf '%s\n' "${merged_value}"
    return 0
  fi

  return 1
}

provider_secret_name_var_name() {
  case "$1" in
    rackspace_core) printf '%s\n' "BAKERY_RACKSPACE_SECRET_NAME" ;;
    servicenow) printf '%s\n' "BAKERY_SERVICENOW_SECRET_NAME" ;;
    jira) printf '%s\n' "BAKERY_JIRA_SECRET_NAME" ;;
    github) printf '%s\n' "BAKERY_GITHUB_SECRET_NAME" ;;
    pagerduty) printf '%s\n' "BAKERY_PAGERDUTY_SECRET_NAME" ;;
    teams) printf '%s\n' "BAKERY_TEAMS_SECRET_NAME" ;;
    discord) printf '%s\n' "BAKERY_DISCORD_SECRET_NAME" ;;
    *)
      log_error "Unsupported provider: $1"
      exit 1
      ;;
  esac
}

resolve_values_backed_settings() {
  local resolved_value=""
  local provider_secret_path=""
  local provider_secret_var=""

  if [[ -z "${ACTIVE_PROVIDER}" ]]; then
    if resolved_value="$(merged_yaml_value "bakery.config.activeProvider")"; then
      ACTIVE_PROVIDER="${resolved_value}"
    else
      ACTIVE_PROVIDER="rackspace_core"
    fi
  fi

  if [[ -z "${BAKERY_AUTH_SECRET_NAME}" ]]; then
    if resolved_value="$(merged_yaml_value "bakery.auth.existingSecret")"; then
      BAKERY_AUTH_SECRET_NAME="${resolved_value}"
    fi
  fi

  provider_secret_path="$(provider_values_path "${ACTIVE_PROVIDER}")"
  provider_secret_var="$(provider_secret_name_var_name "${ACTIVE_PROVIDER}")"

  if [[ -z "${!provider_secret_var}" ]]; then
    if resolved_value="$(merged_yaml_value "${provider_secret_path}")"; then
      printf -v "${provider_secret_var}" '%s' "${resolved_value}"
    else
      printf -v "${provider_secret_var}" '%s' "$(default_provider_secret_name "${ACTIVE_PROVIDER}")"
    fi
  fi
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
      secret_name="${BAKERY_RACKSPACE_SECRET_NAME:-$(default_provider_secret_name "${provider}")}"
      [[ -n "${BAKERY_RACKSPACE_URL}${BAKERY_RACKSPACE_USERNAME}${BAKERY_RACKSPACE_PASSWORD}" ]] && provided="true"
      value_args=(
        --from-literal=rackspace-core-url="${BAKERY_RACKSPACE_URL}"
        --from-literal=rackspace-core-username="${BAKERY_RACKSPACE_USERNAME}"
        --from-literal=rackspace-core-password="${BAKERY_RACKSPACE_PASSWORD}"
      )
      ;;
    servicenow)
      secret_name="${BAKERY_SERVICENOW_SECRET_NAME:-$(default_provider_secret_name "${provider}")}"
      [[ -n "${BAKERY_SERVICENOW_URL}${BAKERY_SERVICENOW_USERNAME}${BAKERY_SERVICENOW_PASSWORD}" ]] && provided="true"
      value_args=(
        --from-literal=servicenow-url="${BAKERY_SERVICENOW_URL}"
        --from-literal=servicenow-username="${BAKERY_SERVICENOW_USERNAME}"
        --from-literal=servicenow-password="${BAKERY_SERVICENOW_PASSWORD}"
      )
      ;;
    jira)
      secret_name="${BAKERY_JIRA_SECRET_NAME:-$(default_provider_secret_name "${provider}")}"
      [[ -n "${BAKERY_JIRA_URL}${BAKERY_JIRA_USERNAME}${BAKERY_JIRA_API_TOKEN}" ]] && provided="true"
      value_args=(
        --from-literal=jira-url="${BAKERY_JIRA_URL}"
        --from-literal=jira-username="${BAKERY_JIRA_USERNAME}"
        --from-literal=jira-api-token="${BAKERY_JIRA_API_TOKEN}"
      )
      ;;
    github)
      secret_name="${BAKERY_GITHUB_SECRET_NAME:-$(default_provider_secret_name "${provider}")}"
      [[ -n "${BAKERY_GITHUB_TOKEN}" ]] && provided="true"
      value_args=(--from-literal=github-token="${BAKERY_GITHUB_TOKEN}")
      ;;
    pagerduty)
      secret_name="${BAKERY_PAGERDUTY_SECRET_NAME:-$(default_provider_secret_name "${provider}")}"
      [[ -n "${BAKERY_PAGERDUTY_API_KEY}" ]] && provided="true"
      value_args=(--from-literal=pagerduty-api-key="${BAKERY_PAGERDUTY_API_KEY}")
      ;;
    teams)
      secret_name="${BAKERY_TEAMS_SECRET_NAME:-$(default_provider_secret_name "${provider}")}"
      [[ -n "${BAKERY_TEAMS_WEBHOOK_URL}" ]] && provided="true"
      value_args=(--from-literal=teams-webhook-url="${BAKERY_TEAMS_WEBHOOK_URL}")
      ;;
    discord)
      secret_name="${BAKERY_DISCORD_SECRET_NAME:-$(default_provider_secret_name "${provider}")}"
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
      --bakery-chart-ref) CHART_REF="$2"; shift 2 ;;
      --bakery-chart-version) CHART_VERSION="$2"; shift 2 ;;
      --bakery-overrides-dir) OVERRIDES_DIR="$2"; shift 2 ;;
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
      -f|--values) ARG_VALUES_FILES+=("$2"); shift 2 ;;
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
  resolve_chart_version
  collect_values_files
  resolve_values_backed_settings
  ensure_namespace_exists
  ensure_auth_secret

  local provider_secret_name
  local provider_values_key
  provider_secret_name="$(ensure_provider_secret "${ACTIVE_PROVIDER}")"
  provider_values_key="$(provider_values_path "${ACTIVE_PROVIDER}")"

  local helm_cmd=(
    helm upgrade --install "${RELEASE_NAME}" "${CHART_REF}"
    --namespace "${NAMESPACE}"
    --create-namespace
    --set bakery.enabled=true
    --set-string "bakery.config.activeProvider=${ACTIVE_PROVIDER}"
    --set-string "bakery.auth.existingSecret=${BAKERY_AUTH_SECRET_NAME}"
    --set-string "${provider_values_key}=${provider_secret_name}"
  )

  if [[ -n "${CHART_VERSION}" ]]; then
    helm_cmd+=(--version "${CHART_VERSION}")
  fi
  if ((${#VALUES_FILES[@]} > 0)); then
    local values_file=""
    for values_file in "${VALUES_FILES[@]}"; do
      helm_cmd+=(-f "${values_file}")
    done
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

  log_info "Installing Bakery release ${RELEASE_NAME} into namespace ${NAMESPACE} from ${CHART_REF}"
  "${helm_cmd[@]}"
}

main "$@"
