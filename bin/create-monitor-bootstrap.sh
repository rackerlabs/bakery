#!/usr/bin/env bash

set -Eeuo pipefail

MONITOR_ID=""
POUNDCAKE_NAMESPACE="rackspace"
SECRET_NAME="bakery-monitor-bootstrap"
BAKERY_NAMESPACE="bakery"
BAKERY_DEPLOYMENT=""
BAKERY_CONTAINER="bakery"
ROTATE="false"
NON_INTERACTIVE="false"

usage() {
  cat <<'USAGE'
Usage:
  create-monitor-bootstrap.sh [options]

Create or rotate a Bakery monitor bootstrap credential and print a Kubernetes
Secret manifest for the remote PoundCake namespace.

Options:
  --monitor-id <id>              PoundCake monitor id, for example iad3-flex
  --poundcake-namespace <name>   Remote PoundCake namespace (default: rackspace)
  --secret-name <name>           Remote PoundCake Secret name (default: bakery-monitor-bootstrap)
  --bakery-namespace <name>      Bakery namespace in this cluster (default: bakery)
  --bakery-deployment <name>     Bakery API deployment name; auto-discovered when omitted
  --rotate                       Rotate an existing bootstrap credential without prompting
  --non-interactive              Fail instead of prompting for missing input/rotation
  -h, --help                     Show this help

The generated YAML is written to stdout. Status messages are written to stderr.
Apply the generated YAML in the PoundCake cluster/namespace, then restart the
PoundCake API deployment so it reads the updated Secret.
USAGE
}

log_info() {
  printf '[INFO] %s\n' "$*" >&2
}

log_error() {
  printf '[ERROR] %s\n' "$*" >&2
}

require_command() {
  local command_name="$1"
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    log_error "Required command not found: ${command_name}"
    exit 1
  fi
}

require_arg() {
  local option="$1"
  local value="${2:-}"
  if [[ -z "${value}" || "${value}" == --* ]]; then
    log_error "${option} requires a value"
    exit 1
  fi
}

yaml_quote() {
  printf '%s' "$1" | sed "s/'/''/g; s/^/'/; s/$/'/"
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --monitor-id)
        require_arg "$1" "${2:-}"
        MONITOR_ID="$2"
        shift 2
        ;;
      --monitor-id=*)
        MONITOR_ID="${1#*=}"
        shift
        ;;
      --poundcake-namespace)
        require_arg "$1" "${2:-}"
        POUNDCAKE_NAMESPACE="$2"
        shift 2
        ;;
      --poundcake-namespace=*)
        POUNDCAKE_NAMESPACE="${1#*=}"
        shift
        ;;
      --secret-name)
        require_arg "$1" "${2:-}"
        SECRET_NAME="$2"
        shift 2
        ;;
      --secret-name=*)
        SECRET_NAME="${1#*=}"
        shift
        ;;
      --bakery-namespace)
        require_arg "$1" "${2:-}"
        BAKERY_NAMESPACE="$2"
        shift 2
        ;;
      --bakery-namespace=*)
        BAKERY_NAMESPACE="${1#*=}"
        shift
        ;;
      --bakery-deployment)
        require_arg "$1" "${2:-}"
        BAKERY_DEPLOYMENT="$2"
        shift 2
        ;;
      --bakery-deployment=*)
        BAKERY_DEPLOYMENT="${1#*=}"
        shift
        ;;
      --rotate)
        ROTATE="true"
        shift
        ;;
      --non-interactive)
        NON_INTERACTIVE="true"
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        log_error "Unknown option: $1"
        usage >&2
        exit 1
        ;;
    esac
  done
}

prompt_for_monitor_id() {
  if [[ -n "${MONITOR_ID}" ]]; then
    return
  fi
  if [[ "${NON_INTERACTIVE}" == "true" ]]; then
    log_error "--monitor-id is required in --non-interactive mode"
    exit 1
  fi
  printf 'PoundCake monitor id: ' >&2
  IFS= read -r MONITOR_ID
  if [[ -z "${MONITOR_ID}" ]]; then
    log_error "Monitor id is required"
    exit 1
  fi
}

discover_bakery_deployment() {
  if [[ -n "${BAKERY_DEPLOYMENT}" ]]; then
    return
  fi

  local deployments deployment_count
  deployments="$(
    kubectl -n "${BAKERY_NAMESPACE}" get deploy \
      -l app.kubernetes.io/component=api \
      -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' | sed '/^$/d'
  )"

  if [[ -z "${deployments}" ]]; then
    log_error "No Bakery API deployment found in namespace '${BAKERY_NAMESPACE}'. Use --bakery-deployment."
    exit 1
  fi
  deployment_count="$(printf '%s\n' "${deployments}" | wc -l | tr -d ' ')"
  if [[ "${deployment_count}" != "1" ]]; then
    log_error "Multiple Bakery API deployments found: ${deployments}. Use --bakery-deployment."
    exit 1
  fi

  BAKERY_DEPLOYMENT="${deployments}"
}

mint_bootstrap_credential() {
  local allow_rotate="$1"
  kubectl -n "${BAKERY_NAMESPACE}" exec -i "deploy/${BAKERY_DEPLOYMENT}" -c "${BAKERY_CONTAINER}" -- \
    env MONITOR_ID="${MONITOR_ID}" ALLOW_ROTATE="${allow_rotate}" python - <<'PY'
from __future__ import annotations

import json
import os
import sys

from bakery.database import SessionLocal
from bakery.models import MonitorBootstrapCredential
from bakery.monitoring import create_or_rotate_bootstrap_credential

monitor_id = os.environ["MONITOR_ID"].strip()
allow_rotate = os.environ.get("ALLOW_ROTATE", "").lower() == "true"

db = SessionLocal()
try:
    existing = (
        db.query(MonitorBootstrapCredential)
        .filter(MonitorBootstrapCredential.monitor_id == monitor_id)
        .first()
    )
    if existing is not None and not allow_rotate:
        print(
            json.dumps(
                {
                    "exists": True,
                    "monitor_id": monitor_id,
                    "key_id": existing.key_id,
                },
                sort_keys=True,
            )
        )
        sys.exit(42)

    response = create_or_rotate_bootstrap_credential(db, monitor_id=monitor_id)
    db.commit()
    print(response.model_dump_json())
except SystemExit:
    raise
except Exception:
    db.rollback()
    raise
finally:
    db.close()
PY
}

confirm_rotation() {
  local existing_json="$1"
  local existing_key_id
  existing_key_id="$(printf '%s' "${existing_json}" | jq -r '.key_id // "unknown"')"

  if [[ "${NON_INTERACTIVE}" == "true" ]]; then
    log_error "Bootstrap credential for monitor '${MONITOR_ID}' already exists (key_id=${existing_key_id}). Use --rotate to replace it."
    exit 1
  fi

  local answer=""
  printf "Bootstrap credential for monitor '%s' already exists (key_id=%s). Rotate it? [y/N] " "${MONITOR_ID}" "${existing_key_id}" >&2
  IFS= read -r answer
  case "${answer}" in
    y|Y|yes|YES)
      ROTATE="true"
      ;;
    *)
      log_error "Aborted without rotating bootstrap credential."
      exit 1
      ;;
  esac
}

emit_secret_yaml() {
  local credential_json="$1"
  local key_id secret monitor_encryption_key
  key_id="$(printf '%s' "${credential_json}" | jq -r '.key_id')"
  secret="$(printf '%s' "${credential_json}" | jq -r '.secret')"
  monitor_encryption_key="$(openssl rand -base64 32)"

  if [[ -z "${key_id}" || "${key_id}" == "null" || -z "${secret}" || "${secret}" == "null" ]]; then
    log_error "Bakery did not return a valid bootstrap credential."
    exit 1
  fi

  cat <<YAML
apiVersion: v1
kind: Secret
metadata:
  name: ${SECRET_NAME}
  namespace: ${POUNDCAKE_NAMESPACE}
  annotations:
    bakery.rackerlabs.com/monitor-id: $(yaml_quote "${MONITOR_ID}")
type: Opaque
stringData:
  bootstrap-key-id: $(yaml_quote "${key_id}")
  bootstrap-key: $(yaml_quote "${secret}")
  monitor-encryption-key: $(yaml_quote "${monitor_encryption_key}")
YAML
}

main() {
  parse_args "$@"
  prompt_for_monitor_id

  require_command kubectl
  require_command jq
  require_command openssl

  discover_bakery_deployment
  log_info "Using Bakery API deployment ${BAKERY_NAMESPACE}/${BAKERY_DEPLOYMENT}"

  local credential_json status
  set +e
  credential_json="$(mint_bootstrap_credential "${ROTATE}")"
  status=$?
  set -e

  if [[ "${status}" -eq 42 ]]; then
    confirm_rotation "${credential_json}"
    credential_json="$(mint_bootstrap_credential "true")"
  elif [[ "${status}" -ne 0 ]]; then
    log_error "Failed to create Bakery monitor bootstrap credential for '${MONITOR_ID}'."
    exit "${status}"
  fi

  log_info "Created Bakery bootstrap credential for monitor '${MONITOR_ID}'."
  emit_secret_yaml "${credential_json}"
}

main "$@"
