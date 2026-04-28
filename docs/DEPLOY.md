# Deployment

Bakery is deployed as a standalone service from this repo. PoundCake no longer installs or owns
Bakery resources.

## Canonical Paths

- Bakery repo root installer: [`bin/install-bakery.sh`](../bin/install-bakery.sh)
- Default Bakery override directory: `/etc/genestack/helm-configs/bakery/`
- Shared chart version file: `/etc/genestack/helm-chart-versions.yaml`
- Standalone PoundCake repo: [rackerlabs/poundcake](https://github.com/rackerlabs/poundcake)

Recommended override layout:

- `00-pull-secret-overrides.yaml`
- `10-main-overrides.yaml`

`bin/install-bakery.sh` automatically loads every `*.yaml` and `*.yml` file from
`/etc/genestack/helm-configs/bakery/` in filename order when that directory exists. Set
`BAKERY_OVERRIDES_DIR` or pass `--bakery-overrides-dir` to use a different directory. Backup
files like `10-main-overrides.yaml.bak-20260408` are ignored because they do not end in `.yaml`
or `.yml`.

Before rollout, add or update the `bakery` entry in `/etc/genestack/helm-chart-versions.yaml`.

## Prerequisites

- a Kubernetes cluster with the MariaDB operator installed
- a namespace for the Bakery release
- one provider secret for the active Bakery mixer
- a Bakery auth secret that includes a monitor encryption key for PoundCake monitor registration

The secret names should live in your override YAML, not only on the installer command line. For
example:

- `bakery.auth.existingSecret`
- `bakery.rackspaceCore.existingSecret`
- `bakery.servicenow.existingSecret`
- `bakery.jira.existingSecret`
- `bakery.github.existingSecret`
- `bakery.pagerduty.existingSecret`
- `bakery.teams.existingSecret`
- `bakery.discord.existingSecret`

Example Rackspace Core secret:

```bash
kubectl -n bakery create secret generic bakery-rackspace-core \
  --from-literal=rackspace-core-url='<rackspace-core-url>' \
  --from-literal=rackspace-core-username='<rackspace-core-username>' \
  --from-literal=rackspace-core-password='<rackspace-core-password>'
```

Example Bakery auth secret:

```bash
kubectl -n bakery create secret generic bakery-hmac \
  --from-literal=active-key-id=active \
  --from-literal=active-key="$(openssl rand -base64 32)" \
  --from-literal=monitor-encryption-key="$(openssl rand -base64 32)"
```

`monitor-encryption-key` is required when Bakery stores PoundCake bootstrap credentials and
per-monitor HMAC secrets.

If you want to use the Bakery operator UI or `bakeryctl`, also configure operator auth. The local
bootstrap mode uses:

```bash
kubectl -n bakery create secret generic bakery-operator-auth \
  --from-literal=username='<operator-username>' \
  --from-literal=password='<operator-password>'
```

Then wire the matching `BAKERY_OPERATOR_AUTH_*` env vars through your chart overrides or secret
mapping. OIDC and service-token flows are also supported by the operator auth endpoints.

Bakery now exposes Helm values for operator auth under `bakery.operatorAuth.*`. Local bootstrap auth
can be enabled with:

```yaml
bakery:
  operatorAuth:
    local:
      enabled: true
      existingSecret: bakery-operator-auth
```

Auth0 and Azure AD flows follow the same shared/ui/cli split already used in PoundCake:
`bakery.operatorAuth.auth0.*` and `bakery.operatorAuth.azureAd.*`.

### Required Secret Checklist

Keep secret values out of Helm values files and public documentation. The override files should
name the Kubernetes secrets, and the secrets should contain these keys:

- `bakery.auth.existingSecret`: `active-key-id`, `active-key`, `monitor-encryption-key`
- `bakery.rackspaceCore.existingSecret`: `rackspace-core-url`, `rackspace-core-username`,
  `rackspace-core-password`
- `bakery.operatorAuth.local.existingSecret`: `username`, `password`

The auth secret may also include `next-key-id` and `next-key` during HMAC rotation. Provider
secrets for ServiceNow, Jira, GitHub, PagerDuty, Teams, and Discord use the key names shown in
`helm/values.yaml` under each provider's `secretKeys` block.

## UI Install Modes

The Bakery chart always deploys these three workloads together:

- `bakery-release`
- `bakery-release-ui`
- `bakery-release-worker`

You do not install the UI separately. Pick the exposure mode that fits your environment.

### Same-Host UI

This is the simplest install shape. The UI is served from `/` on the same hostname as the API and
uses relative `/api/v1/*` calls.

`10-main-overrides.yaml`

```yaml
fullnameOverride: bakery-release

bakery:
  auth:
    existingSecret: bakery-hmac
  config:
    activeProvider: rackspace_core
    ticketingDryRun: true
  gateway:
    enabled: true
    gatewayName: flex-gateway
    gatewayNamespace: envoy-gateway
    listener:
      name: bakery-https
      hostname: bakery.example.com
      port: 443
      protocol: HTTPS
      tlsSecretName: bakery-gw-tls-secret
      allowedNamespaces: All
      updateIfExists: true
    hostnames:
      - bakery.example.com
  rackspaceCore:
    existingSecret: bakery-rackspace-core
    verifySsl: false
```

In same-host mode, leave `bakery.ui.publicUrl`, `bakery.ui.apiBaseUrl`, and `bakery.ui.gateway.*`
unset. The API `HTTPRoute` continues to serve the UI backend at `/`.

### Split-Host UI

Use this mode when the UI must live on its own hostname or gateway route while the API remains on a
separate Bakery hostname.

`10-main-overrides.yaml`

```yaml
fullnameOverride: bakery-release

bakery:
  auth:
    existingSecret: bakery-hmac
  config:
    activeProvider: rackspace_core
    ticketingDryRun: true
  gateway:
    enabled: true
    gatewayName: flex-gateway
    gatewayNamespace: envoy-gateway
    listener:
      name: bakery-https
      hostname: bakery.example.com
      port: 443
      protocol: HTTPS
      tlsSecretName: bakery-gw-tls-secret
      allowedNamespaces: All
      updateIfExists: true
    hostnames:
      - bakery.example.com
  ui:
    publicUrl: https://bakery-ui.example.net
    apiBaseUrl: https://bakery.example.com
    gateway:
      enabled: true
      gatewayName: bakery-ui-gateway
      gatewayNamespace: envoy-gateway
      listener:
        name: bakery-ui-https
        tlsSecretName: bakery-ui-gw-tls-secret
      hostnames:
        - bakery-ui.example.net
  rackspaceCore:
    existingSecret: bakery-rackspace-core
    verifySsl: false
```

The split UI gateway is Helm-managed against an existing Gateway. The chart patches the named UI
listener idempotently and creates the UI `HTTPRoute`, but the `bakery-ui-gateway` Gateway itself
must already exist in the cluster.

When `bakery.ui.gateway.listener.hostname` is unset, the chart uses the first
`bakery.ui.gateway.hostnames` entry. The UI listener `port`, `protocol`, `allowedNamespaces`, and
`updateIfExists` settings default to the same values as the main Bakery gateway path.

In split-host mode:

- `bakery.ui.publicUrl` becomes the UI browser URL
- `bakery.ui.apiBaseUrl` becomes the API origin for UI calls and auth return flows
- the API route stops serving the UI backend at `/`
- the UI runtime config is rendered into `/runtime/config.js`

The UI and API may be on completely different Gateways. In that shape, keep the API Gateway values
under `bakery.gateway.*`, keep the UI Gateway values under `bakery.ui.gateway.*`, set
`bakery.ui.publicUrl` to the UI origin, and set `bakery.ui.apiBaseUrl` to the API origin. Do not
move the UI route onto the API hostname just to make login work; the API enables credentialed CORS
from the configured UI origin.

For browser login, prefer keeping API calls first-party to the UI origin. If the UI and API
hostnames are on different registrable domains, route the UI hostname's `/api` path to the Bakery
API service through the UI Gateway and set `bakery.ui.apiBaseUrl` to the UI origin. When
`bakery.ui.apiBaseUrl` matches `bakery.ui.publicUrl`, the chart adds this `/api` rule to the UI
`HTTPRoute` ahead of the `/` UI backend rule. The public API hostname can remain available through
`bakery.gateway.*`; the browser just avoids relying on third-party cookies.

Put pull secrets in `00-pull-secret-overrides.yaml` when private GHCR pulls are required.

## Install

Run the canonical installer from the repository root. Bakery installs from the published OCI chart
by default.

The simplest path is just:

```bash
./bin/install-bakery.sh
```

If `/etc/genestack/helm-configs/bakery` exists, the installer loads it automatically. To use a
different environment-specific values directory, point the installer at it:

```bash
BAKERY_OVERRIDES_DIR=/path/to/bakery-overrides ./bin/install-bakery.sh
```

The normal release path is updating the `bakery` entry in
`/etc/genestack/helm-chart-versions.yaml`. To override it explicitly for one run:

```bash
BAKERY_CHART_VERSION="0.1.10" ./bin/install-bakery.sh
```

Override the OCI chart reference when needed:

```bash
BAKERY_CHART_REF="oci://ghcr.io/rackerlabs/charts/bakery" ./bin/install-bakery.sh
```

Or pass the override directory explicitly:

```bash
./bin/install-bakery.sh --bakery-overrides-dir /path/to/bakery-overrides
```

If you need one extra ad hoc values file on top of the auto-loaded directory, append it with `-f`.

The older wrapper paths under `install/` and `helm/bin/` are no longer supported.

## Verification

Wait for rollout:

```bash
kubectl -n bakery rollout status deploy/bakery-release --timeout=300s
kubectl -n bakery rollout status deploy/bakery-release-ui --timeout=300s
kubectl -n bakery rollout status deploy/bakery-release-worker --timeout=300s
```

Confirm release state:

```bash
helm ls -n bakery
kubectl -n bakery get deploy,pods,svc,httproute
curl -fsS https://bakery.example.com/api/v1/health
```

Confirm the UI route you chose:

```bash
curl -fsS https://bakery.example.com/ | grep -q "Bakery Console"
curl -fsS https://bakery-ui.example.net/ | grep -q "Bakery Console"
curl -fsS https://bakery-ui.example.net/runtime/config.js
```

Use the same-host URL when you kept `bakery.ui.gateway.enabled=false`. Use the split-host URL and
runtime-config check when you enabled `bakery.ui.gateway.enabled=true`.

Confirm the operator control-plane APIs:

```bash
curl -fsS https://bakery.example.com/docs > /dev/null
curl -fsS https://bakery.example.com/redoc > /dev/null
curl -fsS https://bakery.example.com/openapi.json > /dev/null
curl -fsS https://bakery.example.com/metrics > /dev/null
curl -fsS https://bakery.example.com/api/v1/settings
curl -fsS https://bakery.example.com/api/v1/auth/providers
```

If `auth_providers` is empty while operator auth is enabled, check that
`bakery.operatorAuth.local.existingSecret` exists in the Bakery namespace and contains both
`username` and `password`. The chart references those keys as optional secret refs so the pod can
start even when the secret is missing, but local password login will not be offered until both keys
resolve to non-empty values.

If PoundCake is already connected, verify monitor registration and heartbeat activity:

```bash
kubectl -n bakery logs deploy/bakery-release-worker --tail=100
kubectl -n bakery exec bakery-release-mariadb-0 -- \
  mariadb -uroot -p"$(kubectl -n bakery get secret bakery-release-mariadb-root -o jsonpath='{.data.password}' | base64 -d)" \
  -N -e "USE bakery; SELECT monitor_id, status, last_checkin_at, route_sync_required FROM monitors;"
```

If operator auth is enabled, you can also verify the new read surfaces with:

```bash
bakeryctl --url https://bakery.example.com auth whoami
bakeryctl --url https://bakery.example.com reports overview
bakeryctl --url https://bakery.example.com monitors list
bakeryctl --url https://bakery.example.com jobs list
```

Open `https://bakery-ui.example.net/`, sign in through the configured operator auth flow, and
confirm the browser lands back on the UI domain with the Bakery Console loaded while API requests
continue to target `https://bakery.example.com/api/v1/*`.

Recommended UI smoke checks:

1. Overview loads with live refresh enabled.
2. Monitors shows current monitor health and a detail rail.
3. Collection Jobs lets you queue by monitor name instead of UUID.
4. A `cluster_inventory` result renders node, storage, and workload sections.
5. Backlog shows dry-run or error classification, and eligible tickets expose operator actions.

The full operator-console walkthrough is documented in [OPERATOR_CONSOLE.md](OPERATOR_CONSOLE.md).

## Live Provider Validation

Keep `bakery.config.ticketingDryRun: true` for normal deployments. For live provider validation,
temporarily set it to `false`, redeploy Bakery, run the validation, then set it back to `true` and
redeploy again.

Recommended live validation sequence:

1. Verify PoundCake is registered in Bakery and heartbeats are healthy.
2. Run the PoundCake PVC-expand validation flow and confirm Bakery creates the expected provider
   ticket.
3. Scale the PoundCake API deployment to zero, wait longer than 5 missed 30-second heartbeats,
   and confirm Bakery creates the monitor-unreachable outage ticket.
4. Scale PoundCake back up and confirm Bakery records recovery.
5. Return `ticketingDryRun` to `true` and redeploy Bakery.

The exact remote PoundCake bootstrap, monitor verification, and live validation flow is documented
in [REMOTE_BAKERY_DEPLOYMENT_GUIDE.md](REMOTE_BAKERY_DEPLOYMENT_GUIDE.md).
