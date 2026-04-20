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

## Operator Console

The Helm chart always deploys the Bakery UI alongside the API and worker. There is no separate UI
installer or second chart.

Supported UI exposure modes:

- same-host mode: Bakery serves the UI from `/` on the API hostname through `bakery.gateway.*`
- split-host mode: Bakery serves the UI from its own hostname through `bakery.ui.gateway.*` while
  API requests continue to target `bakery.ui.apiBaseUrl`

The console now includes:

- an Overview page with live health cards, active jobs, stale monitor counts, and collector
  activity
- monitor inventory, monitor detail, route inventory, provider analytics, and operations analytics
- monitor-name-based collection job queueing with collector-specific forms and live job detail
- cluster inventory reports with nodes, labels, annotations, storage topology, workload snapshots,
  Markdown export, and raw JSON export
- backlog drilldowns with dry-run classification plus operator close and resync actions for
  eligible tickets
- default live refresh with 15-second overview polling, 5-second detail polling, and automatic
  pause when the browser tab is hidden

See [docs/OPERATOR_CONSOLE.md](docs/OPERATOR_CONSOLE.md) for the full operator-console walkthrough,
[docs/DEPLOY.md](docs/DEPLOY.md) for standalone installation and UI routing, and
[docs/REMOTE_BAKERY_DEPLOYMENT_GUIDE.md](docs/REMOTE_BAKERY_DEPLOYMENT_GUIDE.md) for the remote
PoundCake integration flow.

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

The installer automatically loads every `.yaml` and `.yml` file from `/srv/config/bakery` in
filename order when that directory exists. Use `BAKERY_OVERRIDES_DIR` /
`--bakery-overrides-dir` to point at a different directory, or set
`BAKERY_OVERRIDES_DIR=""` to disable directory auto-loading. Put auth secret names, provider
secret names, pull secrets, and UI routing there rather than only on the command line.

See [docs/DEPLOY.md](docs/DEPLOY.md) for standalone installation and
[docs/REMOTE_BAKERY_DEPLOYMENT_GUIDE.md](docs/REMOTE_BAKERY_DEPLOYMENT_GUIDE.md) for the remote
PoundCake integration flow.
