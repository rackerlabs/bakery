# Remote PoundCake Integration

This is the supported split deployment flow:

1. install Bakery from this repo
2. publish Bakery at an HTTPS URL
3. create the same Bakery HMAC secret in both environments
4. redeploy PoundCake with `bakery.client.*` remote mode enabled

## Bakery Side

Create one shared HMAC key:

```bash
export SHARED_BAKERY_HMAC_KEY="$(openssl rand -base64 32)"
```

Create the Bakery-side secret with that exact key:

```bash
kubectl -n bakery create secret generic bakery-hmac \
  --from-literal=active-key-id=active \
  --from-literal=active-key="${SHARED_BAKERY_HMAC_KEY}" \
  --dry-run=client -o yaml | kubectl apply -f -
```

Install Bakery with that auth secret and publish it through Gateway API:

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

Verify Bakery before touching PoundCake:

```bash
curl -fsS https://bakery.example.com/api/v1/health
kubectl -n bakery get httproute
```

## PoundCake Side

Create the same HMAC secret in the PoundCake namespace:

```bash
kubectl -n rackspace create secret generic bakery-hmac \
  --from-literal=active-key-id=active \
  --from-literal=active-key="${SHARED_BAKERY_HMAC_KEY}" \
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
      existingSecret: bakery-hmac
```

After PoundCake is redeployed, verify its running values and environment reflect the remote Bakery
URL and shared HMAC secret.
