# Bakery

Bakery is the standalone communication integration service extracted from PoundCake. It accepts
provider-agnostic communication requests, persists async operation state in MariaDB, and translates
those requests into provider-native payloads for systems like Rackspace Core, ServiceNow, Jira,
GitHub, PagerDuty, Teams, and Discord.

## What Bakery Owns

- `/api/v1/communications*` for the current provider-agnostic API
- `/api/v1/tickets*` for the legacy compatibility surface
- HMAC-authenticated service-to-service access
- the async worker, retry, and dead-letter flow
- the standalone Docker image, Helm chart, installer, and release pipeline

## Local Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

```bash
make run-api
make run-worker
make db-init
```

## Testing

```bash
pre-commit run --all-files
mypy bakery shared
pytest -m "not integration" tests/ -v --cov=bakery --cov=shared --cov-report=xml
helm lint ./helm
helm unittest ./helm --file 'tests/unittest/*_test.yaml'
```

## Artifacts

- Docker image: `ghcr.io/rackerlabs/bakery`
- Helm chart: `bakery`

## Install

The repo-managed entrypoints are:

```bash
./install/install-bakery-helm.sh
./helm/bin/install-bakery.sh
```

See [docs/DEPLOY.md](docs/DEPLOY.md) for standalone installation and
[docs/REMOTE_BAKERY_DEPLOYMENT_GUIDE.md](docs/REMOTE_BAKERY_DEPLOYMENT_GUIDE.md) for the remote
PoundCake integration flow.
