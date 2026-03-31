#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
INSTALLER="${ROOT_DIR}/bin/install-bakery.sh"

fail() {
  echo "[FAIL] $*" >&2
  exit 1
}

assert_contains() {
  local needle="$1"
  local file="$2"
  if ! rg -Fq -- "${needle}" "${file}"; then
    echo "Expected to find: ${needle}" >&2
    echo "In file: ${file}" >&2
    echo "--- file contents ---" >&2
    cat "${file}" >&2 || true
    echo "---------------------" >&2
    fail "missing expected content"
  fi
}

assert_not_contains() {
  local needle="$1"
  local file="$2"
  if rg -Fq -- "${needle}" "${file}"; then
    echo "Did not expect to find: ${needle}" >&2
    echo "In file: ${file}" >&2
    echo "--- file contents ---" >&2
    cat "${file}" >&2 || true
    echo "---------------------" >&2
    fail "unexpected content present"
  fi
}

echo "Checking standalone Bakery installer entrypoint..."
[[ -x "${INSTALLER}" ]] || fail "missing ${INSTALLER}"
assert_contains 'CHART_REF="${BAKERY_CHART_REF:-oci://ghcr.io/rackerlabs/charts/bakery}"' "${INSTALLER}"
assert_not_contains "install-poundcake" "${INSTALLER}"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT
MOCK_BIN="${TMP_DIR}/mockbin"
mkdir -p "${MOCK_BIN}"

cat > "${MOCK_BIN}/helm" <<'HELM_EOF'
#!/usr/bin/env bash
set -euo pipefail
: "${TEST_HELM_LOG:?missing TEST_HELM_LOG}"
printf '%s\n' "$*" >> "${TEST_HELM_LOG}"
exit 0
HELM_EOF
chmod +x "${MOCK_BIN}/helm"

cat > "${MOCK_BIN}/kubectl" <<'KUBE_EOF'
#!/usr/bin/env bash
set -euo pipefail
: "${TEST_KUBECTL_LOG:?missing TEST_KUBECTL_LOG}"
: "${TEST_KUBECTL_CREATED_SECRETS:?missing TEST_KUBECTL_CREATED_SECRETS}"
printf '%s\n' "$*" >> "${TEST_KUBECTL_LOG}"

secret_exists_for_name() {
  local secret_name="$1"
  case "${secret_name}" in
    bakery-rackspace-core)
      printf '%s\n' "${MOCK_BAKERY_RACKSPACE_SECRET_EXISTS:-1}"
      ;;
    bakery-secret)
      printf '%s\n' "${MOCK_BAKERY_AUTH_SECRET_EXISTS:-0}"
      ;;
    custom-auth)
      printf '%s\n' "${MOCK_CUSTOM_AUTH_SECRET_EXISTS:-0}"
      ;;
    *)
      printf '%s\n' "${MOCK_GENERIC_SECRET_EXISTS:-0}"
      ;;
  esac
}

if [[ "${1:-}" == "get" && "${2:-}" == "namespace" ]]; then
  exit 1
fi

if [[ "${1:-}" == "create" && "${2:-}" == "namespace" ]]; then
  exit 0
fi

if [[ "${1:-}" == "-n" && "${3:-}" == "get" && "${4:-}" == "secret" ]]; then
  secret_name="${5:-}"
  if [[ -f "${TEST_KUBECTL_CREATED_SECRETS}" ]] && rg -Fxq -- "${secret_name}" "${TEST_KUBECTL_CREATED_SECRETS}"; then
    exit 0
  fi
  if [[ "$(secret_exists_for_name "${secret_name}")" == "1" ]]; then
    exit 0
  fi
  exit 1
fi

if [[ "${1:-}" == "-n" && "${3:-}" == "create" && "${4:-}" == "secret" && "${5:-}" == "generic" ]]; then
  secret_name="${6:-mock-secret}"
  printf 'apiVersion: v1\nkind: Secret\nmetadata:\n  name: %s\n' "${secret_name}"
  exit 0
fi

if [[ "${1:-}" == "apply" && "${2:-}" == "-f" && "${3:-}" == "-" ]]; then
  manifest="$(cat)"
  secret_name="$(printf '%s\n' "${manifest}" | awk '/^  name:/ { print $2; exit }')"
  if [[ -n "${secret_name}" ]]; then
    printf '%s\n' "${secret_name}" >> "${TEST_KUBECTL_CREATED_SECRETS}"
  fi
  exit 0
fi

exit 0
KUBE_EOF
chmod +x "${MOCK_BIN}/kubectl"

cat > "${TMP_DIR}/values.yaml" <<'VALUES_EOF'
bakery:
  gateway:
    enabled: false
VALUES_EOF

run_with_mocks() {
  local out_file="$1"
  shift
  TEST_HELM_LOG="${TMP_DIR}/helm.log"
  TEST_KUBECTL_LOG="${TMP_DIR}/kubectl.log"
  TEST_KUBECTL_CREATED_SECRETS="${TMP_DIR}/kubectl-created-secrets.log"
  : > "${TEST_HELM_LOG}"
  : > "${TEST_KUBECTL_LOG}"
  : > "${TEST_KUBECTL_CREATED_SECRETS}"

  PATH="${MOCK_BIN}:${PATH}" \
  TEST_HELM_LOG="${TEST_HELM_LOG}" \
  TEST_KUBECTL_LOG="${TEST_KUBECTL_LOG}" \
  TEST_KUBECTL_CREATED_SECRETS="${TEST_KUBECTL_CREATED_SECRETS}" \
  "$@" > "${out_file}" 2>&1
}

echo "Validating standalone Bakery install with an existing provider secret..."
EXISTING_PROVIDER_OUT="${TMP_DIR}/existing-provider.out"
run_with_mocks "${EXISTING_PROVIDER_OUT}" \
  env \
  BAKERY_NAMESPACE="env-ns" \
  BAKERY_RELEASE_NAME="bakery" \
  BAKERY_VALUES_FILE="${TMP_DIR}/values.yaml" \
  BAKERY_IMAGE_TAG="0.1.9" \
  BAKERY_HELM_WAIT="true" \
  MOCK_BAKERY_RACKSPACE_SECRET_EXISTS="1" \
  MOCK_BAKERY_AUTH_SECRET_EXISTS="0" \
  "${INSTALLER}" \
  --bakery-active-provider rackspace_core

assert_contains "Installing Bakery release bakery into namespace env-ns" "${EXISTING_PROVIDER_OUT}"
assert_contains "upgrade --install bakery" "${TMP_DIR}/helm.log"
assert_contains "oci://ghcr.io/rackerlabs/charts/bakery" "${TMP_DIR}/helm.log"
assert_contains "--namespace env-ns" "${TMP_DIR}/helm.log"
assert_contains "--set bakery.enabled=true" "${TMP_DIR}/helm.log"
assert_contains "--set-string bakery.config.activeProvider=rackspace_core" "${TMP_DIR}/helm.log"
assert_contains "--set-string bakery.auth.existingSecret=bakery-secret" "${TMP_DIR}/helm.log"
assert_contains "--set-string bakery.rackspaceCore.existingSecret=bakery-rackspace-core" "${TMP_DIR}/helm.log"
assert_contains "--version 0.1.1" "${TMP_DIR}/helm.log"
assert_contains "-f ${TMP_DIR}/values.yaml" "${TMP_DIR}/helm.log"
assert_contains "--set-string bakery.image.tag=0.1.9" "${TMP_DIR}/helm.log"
assert_contains "--wait" "${TMP_DIR}/helm.log"
assert_contains "bakery-secret" "${TMP_DIR}/kubectl-created-secrets.log"

echo "Validating installer-managed Bakery auth and provider secret creation..."
CREATE_PROVIDER_OUT="${TMP_DIR}/create-provider.out"
run_with_mocks "${CREATE_PROVIDER_OUT}" \
  env \
  BAKERY_NAMESPACE="env-ns" \
  BAKERY_RELEASE_NAME="bakery" \
  BAKERY_HELM_WAIT="false" \
  MOCK_BAKERY_RACKSPACE_SECRET_EXISTS="0" \
  MOCK_CUSTOM_AUTH_SECRET_EXISTS="0" \
  "${INSTALLER}" \
  --bakery-active-provider rackspace_core \
  --bakery-auth-secret-name custom-auth \
  --bakery-rackspace-url https://core.example.com \
  --bakery-rackspace-username bakery-user \
  --bakery-rackspace-password bakery-pass

assert_contains "--set-string bakery.auth.existingSecret=custom-auth" "${TMP_DIR}/helm.log"
assert_not_contains "--wait" "${TMP_DIR}/helm.log"
assert_contains "custom-auth" "${TMP_DIR}/kubectl-created-secrets.log"
assert_contains "bakery-rackspace-core" "${TMP_DIR}/kubectl-created-secrets.log"

echo "Validating installer failure when provider credentials are missing..."
MISSING_PROVIDER_OUT="${TMP_DIR}/missing-provider.out"
if run_with_mocks "${MISSING_PROVIDER_OUT}" \
  env \
  BAKERY_NAMESPACE="env-ns" \
  BAKERY_RELEASE_NAME="bakery" \
  MOCK_BAKERY_RACKSPACE_SECRET_EXISTS="0" \
  MOCK_BAKERY_AUTH_SECRET_EXISTS="0" \
  "${INSTALLER}" \
  --bakery-active-provider rackspace_core; then
  fail "expected missing provider credentials to fail"
fi
assert_contains "Active provider rackspace_core requires credentials or an existing secret." "${MISSING_PROVIDER_OUT}"

echo "[PASS] Bakery install script regression checks passed"
