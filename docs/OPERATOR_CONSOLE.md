# Operator Console

Bakery ships a React/Vite operator console that is deployed by the main Helm chart as the
`bakery-poundcake-bakery-ui` workload. You do not install the UI separately.

## Access Modes

- same-host mode: keep `bakery.ui.gateway.enabled=false` and expose the UI from `/` on the main
  Bakery hostname
- split-host mode: set `bakery.ui.publicUrl`, `bakery.ui.apiBaseUrl`, and `bakery.ui.gateway.*`
  so the UI gets its own hostname, managed listener, and `HTTPRoute`

In split-host mode, the chart manages the named UI listener idempotently and creates the UI
`HTTPRoute`. The backing Gateway itself must already exist in the cluster.

The UI reads deploy-time runtime config from `/runtime/config.js`:

- `publicUrl`: the browser-facing UI URL
- `apiBaseUrl`: the Bakery API origin the UI should call

See [DEPLOY.md](DEPLOY.md) for standalone install examples and
[REMOTE_BAKERY_DEPLOYMENT_GUIDE.md](REMOTE_BAKERY_DEPLOYMENT_GUIDE.md) for the remote PoundCake
flow.

## Auth And Roles

The UI uses the same operator auth flow as the API.

- `reader`: can sign in and use the reporting surfaces
- `operator`: can read, queue collection jobs, and manage eligible backlog items
- `admin`: can do everything an operator can do plus manage RBAC bindings and bootstrap credentials

Backlog management actions in the UI are gated by the `manage_backlog` permission.

## Navigation

The console is organized into these main pages:

- `Overview`: live monitor health, queue pressure, recent failures, and collector activity
- `Monitors`: searchable monitor inventory plus a detail rail with recent events, routes, jobs, and
  latest successful collection results
- `Monitor Events`: registration, route sync, unreachable, and recovery history
- `Routes`: current execution catalog as synced from PoundCake monitors
- `Providers`: provider-level route, ticket, and failure counts
- `Operations`: queued, failed, and dead-letter operational pressure by provider/action/status
- `Backlog`: open Bakery tickets with dry-run/error classification and operator actions
- `Collection Jobs`: queue, status, results, and requeue flow for the Bakery collector system

## Live Refresh

Live refresh is enabled by default.

- overview and list pages poll every 15 seconds
- selected detail panes and collection job state poll every 5 seconds
- polling pauses automatically when the browser tab is hidden
- operators can pause and resume refresh from the header control

## Collection Jobs

The Collection Jobs page is built around monitor names instead of raw UUID entry.

- the monitor picker is searchable by monitor ID, environment, cluster, namespace, release, and
  UUID
- new jobs auto-select after queueing so the detail rail starts updating immediately
- job detail explains `queued`, `leased`, `succeeded`, `failed`, and `timed_out` states
- failed jobs surface the error and the selected monitor's freshness context
- successful jobs render collector-specific result views plus raw JSON
- completed jobs can be requeued from the detail rail

Supported built-in collectors:

- `monitor_diagnostics`: lightweight PoundCake monitor context and heartbeat state
- `cluster_inventory`: cluster-wide nodes and storage plus namespace-scoped workload inventory
- `ticket_context`: related ticket, communication, and order context for backlog and incident work

Collector forms expose typed fields for the common parameters and keep an advanced JSON override
editor for expert use.

## Cluster Inventory Reports

`cluster_inventory` now produces a human-readable report as part of the stored collection job
result.

The report includes:

- cluster summary cards
- full node inventory with roles, labels, annotations, taints, versions, addresses, capacity, and
  allocatable resources
- storage classes, persistent volumes, and persistent volume claims
- namespace workload snapshots for pods, deployments, statefulsets, and services
- generated highlights for quick triage

The same report component is reused in collection job detail and monitor detail for the latest
successful inventory result.

Exports:

- Markdown report export
- raw JSON result export

Older historical inventory jobs without the new report fields still render with partial content.

## Backlog Management

The Backlog page is no longer read-only. It now classifies tickets and exposes narrow operator
actions for the first management pass.

- dry-run tickets are marked clearly and explain that they will never close in a provider because
  no external ticket exists
- local Bakery error tickets are marked as needing attention
- eligible dry-run or errored tickets can be closed from the UI with operator resolution notes
- eligible provider-backed error tickets can be resynced with the `find` action
- recent operation history for the selected ticket is shown in the detail rail

Healthy provider-backed open tickets remain read-only in this first pass.

## Suggested Smoke Test

After deploying a new Bakery release, open the UI and verify:

1. the Overview page loads and the header shows live refresh enabled
2. a monitor status change appears without a manual page reload
3. a collection job can be queued by monitor name and reaches a terminal state in the detail rail
4. a `cluster_inventory` job shows node, storage, and workload sections and exports Markdown
5. a dry-run backlog ticket can be selected and, for operator/admin roles, closed from the detail
   rail
