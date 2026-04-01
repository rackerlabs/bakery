# Bakery

Bakery is the standalone communication integration service extracted from PoundCake. It accepts
provider-agnostic communication requests, persists async operation state in MariaDB, and translates
those requests into provider-native payloads for systems like Rackspace Core, ServiceNow, Jira,
GitHub, PagerDuty, Teams, and Discord.

## What Bakery Owns

- `/api/v1/communications*` for the current provider-agnostic API
- `/api/v1/tickets*` for the legacy compatibility surface
- `/api/v1/reports*`, `/api/v1/collection-jobs*`, and `/api/v1/auth*` for operator workflows
- HMAC-authenticated service-to-service access
- DB-backed operator auth, RBAC, reporting, and collection job state
- the `bakeryctl` CLI and the React/Vite operator UI under [`ui/`](ui/)
- the async worker, retry, and dead-letter flow
- the standalone Docker images, Helm chart, installer, and release pipeline

## Local Development

```bash
python3 -m venv .venv
source .venv/bin/activate
make dev-install
```

`make dev-install` installs Bakery's development dependencies plus the local `pre-commit` and
`pre-push` hooks. The `pre-push` hook runs [`bin/testall.sh`](bin/testall.sh), which mirrors the
repo's local push gate by running `pre-commit`, `mypy`, and unit tests before `git push` completes.

```bash
make run-api
make run-worker
make db-init
```

Operator surfaces:

```bash
bakeryctl --help
cd ui && npm install && npm run dev
```

## Testing

```bash
make testall
helm lint ./helm
helm unittest ./helm --file 'tests/unittest/*_test.yaml'
```

For ad hoc runs, `make testall` uses [`bin/testall.sh`](bin/testall.sh), the same script used by
the local `pre-push` hook.

## Artifacts

- Docker images: `ghcr.io/rackerlabs/bakery`, `ghcr.io/rackerlabs/bakery-ui`
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
