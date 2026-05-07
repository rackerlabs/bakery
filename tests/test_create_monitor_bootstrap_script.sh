#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="${ROOT_DIR}/bin/create-monitor-bootstrap.sh"

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

assert_line_count() {
  local expected="$1"
  local pattern="$2"
  local file="$3"
  local actual
  actual="$(rg -c -- "${pattern}" "${file}" || true)"
  if [[ "${actual}" != "${expected}" ]]; then
    echo "Expected ${expected} matches for ${pattern}, got ${actual}" >&2
    echo "--- file contents ---" >&2
    cat "${file}" >&2 || true
    echo "---------------------" >&2
    fail "unexpected match count"
  fi
}

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT
MOCK_BIN="${TMP_DIR}/mockbin"
mkdir -p "${MOCK_BIN}"

cat > "${MOCK_BIN}/kubectl" <<'KUBE_EOF'
#!/usr/bin/env bash
set -euo pipefail
: "${TEST_KUBECTL_LOG:?missing TEST_KUBECTL_LOG}"
printf '%s\n' "$*" >> "${TEST_KUBECTL_LOG}"

if [[ "${1:-}" == "-n" && "${3:-}" == "get" && "${4:-}" == "deploy" ]]; then
  case "${MOCK_DEPLOYMENTS:-bakery-api}" in
    __none__)
      exit 0
      ;;
    *)
      printf '%s\n' "${MOCK_DEPLOYMENTS:-bakery-api}"
      exit 0
      ;;
  esac
fi

if [[ "${1:-}" == "-n" && "${3:-}" == "exec" ]]; then
  cat >/dev/null
  monitor_id=""
  allow_rotate="false"
  for arg in "$@"; do
    case "${arg}" in
      MONITOR_ID=*)
        monitor_id="${arg#MONITOR_ID=}"
        ;;
      ALLOW_ROTATE=*)
        allow_rotate="${arg#ALLOW_ROTATE=}"
        ;;
    esac
  done

  if [[ "${MOCK_BOOTSTRAP_EXISTS:-0}" == "1" && "${allow_rotate}" != "true" ]]; then
    printf '{"exists":true,"key_id":"bootstrap","monitor_id":"%s"}\n' "${monitor_id}"
    exit 42
  fi

  printf '{"monitor_id":"%s","key_id":"bootstrap","secret":"mock-bootstrap-credential-value","created_at":"2026-05-07T00:00:00Z"}\n' "${monitor_id}"
  exit 0
fi

echo "unhandled kubectl args: $*" >&2
exit 1
KUBE_EOF
chmod +x "${MOCK_BIN}/kubectl"

cat > "${MOCK_BIN}/openssl" <<'OPENSSL_EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "rand" && "${2:-}" == "-base64" && "${3:-}" == "32" ]]; then
  printf 'mock-monitor-encryption-key\n'
  exit 0
fi
echo "unhandled openssl args: $*" >&2
exit 1
OPENSSL_EOF
chmod +x "${MOCK_BIN}/openssl"

run_script() {
  TEST_KUBECTL_LOG="${TMP_DIR}/kubectl.log"
  : > "${TEST_KUBECTL_LOG}"
  env \
    TEST_KUBECTL_LOG="${TEST_KUBECTL_LOG}" \
    MOCK_DEPLOYMENTS="${MOCK_DEPLOYMENTS:-}" \
    MOCK_BOOTSTRAP_EXISTS="${MOCK_BOOTSTRAP_EXISTS:-0}" \
    PATH="${MOCK_BIN}:${PATH}" \
    "$SCRIPT" "$@"
}

echo "Checking monitor bootstrap helper exists..."
[[ -x "${SCRIPT}" ]] || fail "missing executable ${SCRIPT}"

echo "Checking non-interactive flag-only execution..."
out_file="${TMP_DIR}/flag-only.yaml"
err_file="${TMP_DIR}/flag-only.err"
run_script \
  --monitor-id iad3-flex \
  --poundcake-namespace rackspace \
  --secret-name bakery-monitor-bootstrap \
  --bakery-namespace bakery \
  --bakery-deployment bakery-api \
  --non-interactive \
  > "${out_file}" 2> "${err_file}"

assert_contains "kind: Secret" "${out_file}"
assert_contains "  name: bakery-monitor-bootstrap" "${out_file}"
assert_contains "  namespace: rackspace" "${out_file}"
assert_contains "    bakery.rackerlabs.com/monitor-id: 'iad3-flex'" "${out_file}"
assert_contains "  bootstrap-key-id: 'bootstrap'" "${out_file}"
assert_contains "  bootstrap-key: 'mock-bootstrap-credential-value'" "${out_file}"
assert_contains "  monitor-encryption-key: 'mock-monitor-encryption-key'" "${out_file}"
assert_contains "exec -i deploy/bakery-api -c bakery -- env MONITOR_ID=iad3-flex ALLOW_ROTATE=false python -" "${TEST_KUBECTL_LOG}"

echo "Checking interactive monitor id prompt..."
out_file="${TMP_DIR}/prompt.yaml"
err_file="${TMP_DIR}/prompt.err"
printf 'prompt-monitor\n' | run_script --bakery-deployment bakery-api > "${out_file}" 2> "${err_file}"
assert_contains "PoundCake monitor id:" "${err_file}"
assert_contains "    bakery.rackerlabs.com/monitor-id: 'prompt-monitor'" "${out_file}"

echo "Checking Bakery deployment auto-discovery..."
out_file="${TMP_DIR}/autodiscover.yaml"
err_file="${TMP_DIR}/autodiscover.err"
MOCK_DEPLOYMENTS="autodiscovered-api" run_script \
  --monitor-id discovered-monitor \
  --non-interactive \
  > "${out_file}" 2> "${err_file}"
assert_contains "get deploy -l app.kubernetes.io/component=api" "${TEST_KUBECTL_LOG}"
assert_contains "exec -i deploy/autodiscovered-api -c bakery -- env MONITOR_ID=discovered-monitor ALLOW_ROTATE=false python -" "${TEST_KUBECTL_LOG}"

echo "Checking missing monitor id fails in non-interactive mode..."
out_file="${TMP_DIR}/missing.out"
err_file="${TMP_DIR}/missing.err"
if run_script --non-interactive > "${out_file}" 2> "${err_file}"; then
  fail "expected missing monitor id to fail"
fi
assert_contains "--monitor-id is required in --non-interactive mode" "${err_file}"

echo "Checking existing credential requires rotation in non-interactive mode..."
out_file="${TMP_DIR}/exists.out"
err_file="${TMP_DIR}/exists.err"
if MOCK_BOOTSTRAP_EXISTS=1 run_script \
  --monitor-id existing-monitor \
  --bakery-deployment bakery-api \
  --non-interactive \
  > "${out_file}" 2> "${err_file}"; then
  fail "expected existing credential without --rotate to fail"
fi
assert_contains "already exists" "${err_file}"
assert_contains "Use --rotate" "${err_file}"

echo "Checking existing credential can be rotated with confirmation..."
out_file="${TMP_DIR}/rotate-confirm.yaml"
err_file="${TMP_DIR}/rotate-confirm.err"
printf 'y\n' | MOCK_BOOTSTRAP_EXISTS=1 run_script \
  --monitor-id existing-monitor \
  --bakery-deployment bakery-api \
  > "${out_file}" 2> "${err_file}"
assert_contains "Rotate it?" "${err_file}"
assert_contains "    bakery.rackerlabs.com/monitor-id: 'existing-monitor'" "${out_file}"
assert_line_count "2" "exec -i deploy/bakery-api" "${TEST_KUBECTL_LOG}"
assert_contains "ALLOW_ROTATE=true" "${TEST_KUBECTL_LOG}"

echo "Checking --rotate skips confirmation..."
out_file="${TMP_DIR}/rotate-flag.yaml"
err_file="${TMP_DIR}/rotate-flag.err"
MOCK_BOOTSTRAP_EXISTS=1 run_script \
  --monitor-id rotate-flag-monitor \
  --bakery-deployment bakery-api \
  --rotate \
  --non-interactive \
  > "${out_file}" 2> "${err_file}"
assert_contains "    bakery.rackerlabs.com/monitor-id: 'rotate-flag-monitor'" "${out_file}"
assert_line_count "1" "exec -i deploy/bakery-api" "${TEST_KUBECTL_LOG}"
assert_contains "ALLOW_ROTATE=true" "${TEST_KUBECTL_LOG}"

echo "[PASS] Monitor bootstrap helper checks passed"
