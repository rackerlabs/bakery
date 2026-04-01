# Remote PoundCake Integration

This is the supported split deployment flow for running Bakery and PoundCake from separate repos.

Use this sequence:

1. deploy Bakery from this repo
2. publish Bakery at an HTTPS URL
3. create the Bakery auth secret with a monitor encryption key
4. mint a bootstrap credential for the PoundCake monitor ID
5. deploy PoundCake from its standalone repo with `bakery.client.*` remote mode enabled
6. verify monitor registration, heartbeats, and live ticket paths

## Canonical Operator Paths

- Bakery repo root: `/opt/bakery`
- PoundCake repo root: `/opt/poundcake`
- Bakery overrides: `/srv/config/bakery/`
- PoundCake overrides: `/srv/config/poundcake/`
- Shared chart versions file: `/srv/config/chart-versions.yaml`

If your environment tracks desired chart versions in `/srv/config/chart-versions.yaml`,
make sure both `bakery` and `poundcake` entries are updated before rollout.

## Bakery Side

Create the Bakery auth secret with the normal HMAC key and the monitor encryption key:

```bash
kubectl -n bakery create secret generic bakery-hmac \
  --from-literal=active-key-id=active \
  --from-literal=active-key="$(openssl rand -base64 32)" \
  --from-literal=monitor-encryption-key="$(openssl rand -base64 32)" \
  --dry-run=client -o yaml | kubectl apply -f -
```

Create the active provider secret, for example Rackspace Core:

```bash
kubectl -n bakery create secret generic bakery-rackspace-core \
  --from-literal=rackspace-core-url='<rackspace-core-url>' \
  --from-literal=rackspace-core-username='<rackspace-core-username>' \
  --from-literal=rackspace-core-password='<rackspace-core-password>' \
  --dry-run=client -o yaml | kubectl apply -f -
```

Minimum Bakery override shape:

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

Install Bakery from the Bakery repo root:

```bash
cd /opt/bakery
BAKERY_NAMESPACE=bakery \
BAKERY_RELEASE_NAME=bakery \
BAKERY_AUTH_SECRET_NAME=bakery-hmac \
./bin/install-bakery.sh \
  -f /srv/config/bakery/00-pull-secret-overrides.yaml \
  -f /srv/config/bakery/10-main-overrides.yaml
```

Verify Bakery before touching PoundCake:

```bash
kubectl -n bakery rollout status deploy/bakery-poundcake-bakery --timeout=300s
kubectl -n bakery rollout status deploy/bakery-poundcake-bakery-ui --timeout=300s
kubectl -n bakery rollout status deploy/bakery-poundcake-bakery-worker --timeout=300s
curl -fsS https://bakery.example.com/ | grep -q "Bakery Console"
curl -fsS https://bakery.example.com/api/v1/health
curl -fsS https://bakery.example.com/docs > /dev/null
curl -fsS https://bakery.example.com/redoc > /dev/null
curl -fsS https://bakery.example.com/openapi.json > /dev/null
curl -fsS https://bakery.example.com/metrics > /dev/null
```

## Bootstrap Credential

PoundCake’s monitor ID is auto-derived as `<namespace>/<release>`. Mint a bootstrap credential for
that ID from Bakery’s admin API:

```bash
export POUNDCAKE_MONITOR_ID="example-namespace/example-release"
curl -fsS -X PUT "https://bakery.example.com/api/v1/admin/monitors/${POUNDCAKE_MONITOR_ID}/bootstrap-credential" \
  -H "Authorization: HMAC <bakery-admin-key-id>:<signature>" \
  -H "X-Timestamp: <unix-timestamp>"
```

Store the returned `key_id` and `secret`. PoundCake uses them once to register and then rotates to
its Bakery-issued per-monitor secret for all normal communication traffic and heartbeats.

## PoundCake Side

Create the PoundCake-side bootstrap secret in the PoundCake namespace:

```bash
kubectl -n rackspace create secret generic bakery-monitor-bootstrap \
  --from-literal=bootstrap-key-id="<bootstrap key_id from Bakery>" \
  --from-literal=bootstrap-key="<bootstrap secret from Bakery>" \
  --from-literal=monitor-encryption-key="$(openssl rand -base64 32)" \
  --dry-run=client -o yaml | kubectl apply -f -
```

Point PoundCake at remote Bakery in
`/srv/config/poundcake/10-main-overrides.yaml`:

```yaml
bakery:
  config:
    activeProvider: rackspace_core
  client:
    enabled: true
    enforceRemoteBaseUrl: true
    baseUrl: https://bakery.example.com
    auth:
      existingSecret: bakery-monitor-bootstrap
```

Install PoundCake from the PoundCake repo root:

```bash
cd /opt/poundcake
./install/install-poundcake-helm.sh
```

## Verify Monitor Wiring

Confirm PoundCake is using remote Bakery:

```bash
kubectl -n rackspace exec deploy/poundcake-api -- printenv | grep '^POUNDCAKE_BAKERY_'
curl -fsS https://poundcake.example.com/api/v1/health
```

Expected runtime shape:

- `POUNDCAKE_BAKERY_ENABLED=true`
- `POUNDCAKE_BAKERY_BASE_URL=https://bakery.example.com`
- `POUNDCAKE_BAKERY_MONITOR_ID=<namespace>/<release>`
- `POUNDCAKE_BAKERY_BOOTSTRAP_HMAC_KEY_ID=<bootstrap key id>`

Confirm Bakery sees the monitor and current heartbeat:

```bash
kubectl -n bakery exec bakery-poundcake-bakery-mariadb-0 -- \
  mariadb -uroot -p"$(kubectl -n bakery get secret bakery-poundcake-bakery-mariadb-root -o jsonpath='{.data.password}' | base64 -d)" \
  -N -e "USE bakery; SELECT monitor_id, monitor_uuid, status, last_checkin_at, route_sync_required FROM monitors;"
```

Confirm PoundCake persisted its local monitor state:

```bash
kubectl -n rackspace exec deploy/poundcake-mariadb -- \
  mariadb -u"$(kubectl -n rackspace get secret poundcake-secrets -o jsonpath='{.data.DB_USER}' | base64 -d)" \
  -p"$(kubectl -n rackspace get secret poundcake-secrets -o jsonpath='{.data.DB_PASSWORD}' | base64 -d)" \
  "$(kubectl -n rackspace get secret poundcake-secrets -o jsonpath='{.data.DB_NAME}' | base64 -d)" \
  -N -e "SELECT monitor_id, monitor_uuid, last_heartbeat_status, last_heartbeat_at FROM bakery_monitor_state;"
```

## Live Validation

Leave Bakery in dry-run for normal rollout. For live provider validation only:

1. set `bakery.config.ticketingDryRun: false`
2. redeploy Bakery
3. run the validation below
4. set `bakery.config.ticketingDryRun: true`
5. redeploy Bakery again

Recommended validation sequence:

1. Run the PoundCake PVC-expand validation flow.
   Note:
   The validation recipe and its target PVC name are runtime data. Before testing, confirm the
   recipe’s StackStorm execution overrides still point at the PVC name you intend to use, or create
   the expected PVC target in the cluster.
2. Send a firing webhook to PoundCake with the `poundcake-admin` `internal-api-key`.
3. Wait for firing remediation to complete, then send the matching resolved webhook with the same
   fingerprint.
4. Verify PoundCake order timeline shows successful Bakery create and close operations and capture
   the external provider ticket number.
5. Scale `deploy/poundcake-api` to zero, wait longer than 5 missed 30-second heartbeats, and
   verify Bakery marks the monitor unreachable and opens the outage communication.
6. Scale `deploy/poundcake-api` back to one replica and verify heartbeats resume and Bakery records
   recovery.

The PoundCake-side deployment details for the same split flow are documented in the standalone
PoundCake repo:

- [poundcake/docs/DEPLOY.md](https://github.com/rackerlabs/poundcake/blob/main/docs/DEPLOY.md)
- [poundcake/docs/REMOTE_BAKERY_DEPLOYMENT_GUIDE.md](https://github.com/rackerlabs/poundcake/blob/main/docs/REMOTE_BAKERY_DEPLOYMENT_GUIDE.md)
