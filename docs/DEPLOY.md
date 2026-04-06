# Deployment

Bakery is deployed as a standalone service from this repo. PoundCake no longer installs or owns
Bakery resources.

## Canonical Paths

- Bakery repo root installer: [`bin/install-bakery.sh`](../bin/install-bakery.sh)
- Bakery override directory on Genestack-style hosts: `/srv/config/bakery/`
- Shared chart version file on Genestack-style hosts: `/srv/config/chart-versions.yaml`
- Standalone PoundCake repo: [rackerlabs/poundcake](https://github.com/rackerlabs/poundcake)

Recommended override layout:

- `00-pull-secret-overrides.yaml`
- `10-main-overrides.yaml`

If your environment tracks deployed chart versions in `/srv/config/chart-versions.yaml`,
add or update a `bakery` entry before rollout.

## Prerequisites

- a Kubernetes cluster with the MariaDB operator installed
- a namespace for the Bakery release
- one provider secret for the active Bakery mixer
- a Bakery auth secret that includes a monitor encryption key for PoundCake monitor registration

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

## Minimum Override Shape

`10-main-overrides.yaml`

```yaml
fullnameOverride: bakery-poundcake-bakery

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
      hostnames:
        - bakery-ui.example.net
  rackspaceCore:
    existingSecret: bakery-rackspace-core
    verifySsl: false
```

The split UI gateway is attach-only. The chart creates the UI `HTTPRoute`, but the
`bakery-ui-gateway` Gateway and listener must already exist in the cluster.

Put pull secrets in `00-pull-secret-overrides.yaml` when private GHCR pulls are required.

## Install

Run the canonical installer from the repository root. Bakery installs from the published OCI chart
by default.

```bash
./bin/install-bakery.sh \
  --bakery-active-provider rackspace_core \
  --bakery-auth-secret-name bakery-hmac
```

Override the OCI chart version when needed:

```bash
BAKERY_CHART_VERSION="0.1.7" ./bin/install-bakery.sh --bakery-auth-secret-name bakery-hmac
```

Override the OCI chart reference when needed:

```bash
BAKERY_CHART_REF="oci://ghcr.io/rackerlabs/charts/bakery" ./bin/install-bakery.sh \
  --bakery-auth-secret-name bakery-hmac
```

The older wrapper paths under `install/` and `helm/bin/` are no longer supported.

## Verification

Wait for rollout:

```bash
kubectl -n bakery rollout status deploy/bakery-poundcake-bakery --timeout=300s
kubectl -n bakery rollout status deploy/bakery-poundcake-bakery-ui --timeout=300s
kubectl -n bakery rollout status deploy/bakery-poundcake-bakery-worker --timeout=300s
```

Confirm release state:

```bash
helm ls -n bakery
kubectl -n bakery get deploy,pods,svc,httproute
curl -fsS https://bakery-ui.example.net/ | grep -q "Bakery Console"
curl -fsS https://bakery.example.com/api/v1/health
```

Confirm the operator control-plane APIs:

```bash
curl -fsS https://bakery.example.com/docs > /dev/null
curl -fsS https://bakery.example.com/redoc > /dev/null
curl -fsS https://bakery.example.com/openapi.json > /dev/null
curl -fsS https://bakery.example.com/metrics > /dev/null
curl -fsS https://bakery.example.com/api/v1/settings
curl -fsS https://bakery.example.com/api/v1/auth/providers
```

If PoundCake is already connected, verify monitor registration and heartbeat activity:

```bash
kubectl -n bakery logs deploy/bakery-poundcake-bakery-worker --tail=100
kubectl -n bakery exec bakery-poundcake-bakery-mariadb-0 -- \
  mariadb -uroot -p"$(kubectl -n bakery get secret bakery-poundcake-bakery-mariadb-root -o jsonpath='{.data.password}' | base64 -d)" \
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
