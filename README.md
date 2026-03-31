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

Bakery ships a standalone Helm chart in [`helm/`](helm/), and the canonical installer entrypoint is
the repo-root OCI installer:

```bash
./bin/install-bakery.sh
```

Run it from the repository root. The older wrapper paths under `install/` and `helm/bin/` have
been removed.

By default it installs `oci://ghcr.io/rackerlabs/charts/bakery` and uses the repo's
[`helm/Chart.yaml`](helm/Chart.yaml) version unless you override `BAKERY_CHART_REF` /
`--bakery-chart-ref` or `BAKERY_CHART_VERSION` / `--bakery-chart-version`.

See [docs/DEPLOY.md](docs/DEPLOY.md) for standalone installation and
[docs/REMOTE_BAKERY_DEPLOYMENT_GUIDE.md](docs/REMOTE_BAKERY_DEPLOYMENT_GUIDE.md) for the remote
PoundCake integration flow.
