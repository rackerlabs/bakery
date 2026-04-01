#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"
HOOK_MODE="${1:-}"

print_section() {
  printf '\n[%s]\n' "$1"
}

print_success() {
  printf '[ok] %s\n' "$1"
}

print_error() {
  printf '[error] %s\n' "$1" >&2
}

select_python() {
  if command -v python3.11 >/dev/null 2>&1; then
    printf 'python3.11\n'
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    printf 'python3\n'
    return
  fi
  print_error "Python 3.11+ is required"
  exit 1
}

PYTHON_BIN="$(select_python)"

if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
  print_error "Python 3.11+ is required"
  exit 1
fi

cd "$PROJECT_ROOT"

if [ "$HOOK_MODE" != "--hook-run" ]; then
  printf 'Bakery local test suite\n'
  printf 'Project root: %s\n' "$PROJECT_ROOT"
fi

if [ ! -d "$VENV_DIR" ]; then
  print_section "Creating virtual environment"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
  print_success "Created $VENV_DIR"
else
  print_section "Using virtual environment"
  print_success "Found $VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

print_section "Installing development dependencies"
python -m pip install --quiet --upgrade pip setuptools wheel
python -m pip install --quiet -e ".[dev]"
print_success "Development dependencies are installed"

print_section "Running repository hygiene checks"
pre-commit run --all-files
print_success "pre-commit checks passed"

print_section "Running mypy"
mypy bakery shared
print_success "mypy passed"

print_section "Running unit tests"
pytest -m "not integration" tests/ -q
print_success "Unit tests passed"

print_section "All checks passed"
print_success "Bakery is ready to push"
