# Remote PoundCake Integration

This is the supported split deployment flow:

1. from the Bakery repo root, install Bakery with `./bin/install-bakery.sh`
2. publish Bakery at an HTTPS URL
3. create the Bakery admin auth secret with a monitor encryption key
4. issue a bootstrap credential for the PoundCake monitor ID
5. redeploy PoundCake with `bakery.client.*` remote mode enabled

## Bakery Side

Create the Bakery-side admin auth secret:

```bash
export BAKERY_ADMIN_HMAC_KEY="$(openssl rand -base64 32)"
export BAKERY_MONITOR_ENCRYPTION_KEY="$(openssl rand -base64 32)"
```

Create the Bakery-side secret:

```bash
kubectl -n bakery create secret generic bakery-hmac \
  --from-literal=active-key-id=active \
  --from-literal=active-key="${BAKERY_ADMIN_HMAC_KEY}" \
  --from-literal=monitor-encryption-key="${BAKERY_MONITOR_ENCRYPTION_KEY}" \
  --dry-run=client -o yaml | kubectl apply -f -
```

From the Bakery repo root, install Bakery with that auth secret and publish it through Gateway
API:

```yaml
bakery:
  auth:
    existingSecret: bakery-hmac
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
    hostnames:
      - bakery.example.com
```

```bash
./bin/install-bakery.sh --bakery-auth-secret-name bakery-hmac
```

The older wrapper paths under `install/` and `helm/bin/` are no longer supported.

Verify Bakery before touching PoundCake:

```bash
curl -fsS https://bakery.example.com/api/v1/health
kubectl -n bakery get httproute
```

Issue a bootstrap credential for the auto-derived PoundCake monitor ID, which uses the Helm
release shape `<namespace>/<release>`:

```bash
export POUNDCAKE_MONITOR_ID="example-namespace/example-release"
curl -fsS -X PUT "https://bakery.example.com/api/v1/admin/monitors/${POUNDCAKE_MONITOR_ID}/bootstrap-credential" \
  -H "Authorization: HMAC <bakery-admin-key-id>:<signature>" \
  -H "X-Timestamp: <unix-timestamp>"
```

Store the returned `key_id` and `secret`. PoundCake uses that bootstrap credential once to
register, receives a Bakery-managed `monitor_uuid`, and then rotates onto a per-monitor HMAC
secret for normal communication traffic and heartbeats.

## PoundCake Side

Create the PoundCake bootstrap secret in the PoundCake namespace:

```bash
kubectl -n rackspace create secret generic bakery-monitor-bootstrap \
  --from-literal=bootstrap-key-id="<bootstrap key_id from Bakery>" \
  --from-literal=bootstrap-key="<bootstrap secret from Bakery>" \
  --from-literal=monitor-encryption-key="$(openssl rand -base64 32)" \
  --dry-run=client -o yaml | kubectl apply -f -
```

Set PoundCake to remote Bakery mode in its values:

```yaml
bakery:
  client:
    enabled: true
    enforceRemoteBaseUrl: true
    baseUrl: https://bakery.example.com
    auth:
      existingSecret: bakery-monitor-bootstrap
```

After PoundCake is redeployed, verify its running values and environment reflect the remote Bakery
URL, bootstrap secret, and auto-derived `POUNDCAKE_BAKERY_MONITOR_ID`.
