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
  rackspaceCore:
    existingSecret: bakery-rackspace-core
    verifySsl: false
```

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
BAKERY_CHART_VERSION="0.1.2" ./bin/install-bakery.sh --bakery-auth-secret-name bakery-hmac
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
kubectl -n bakery rollout status deploy/bakery-poundcake-bakery-worker --timeout=300s
```

Confirm release state:

```bash
helm ls -n bakery
kubectl -n bakery get deploy,pods,svc,httproute
curl -fsS https://bakery.example.com/api/v1/health
```

If PoundCake is already connected, verify monitor registration and heartbeat activity:

```bash
kubectl -n bakery logs deploy/bakery-poundcake-bakery-worker --tail=100
kubectl -n bakery exec bakery-poundcake-bakery-mariadb-0 -- \
  mariadb -uroot -p"$(kubectl -n bakery get secret bakery-poundcake-bakery-mariadb-root -o jsonpath='{.data.password}' | base64 -d)" \
  -N -e "USE bakery; SELECT monitor_id, status, last_checkin_at, route_sync_required FROM monitors;"
```

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
