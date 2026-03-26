# Deployment

Bakery is deployed as a standalone service from this repo. The chart keeps the nested
`bakery.*` values structure so existing Bakery-specific overrides can move over with minimal
renaming.

## Prerequisites

- a Kubernetes cluster with the MariaDB operator installed
- a namespace for the Bakery release
- one provider secret for the active Bakery mixer
- an HMAC secret if you want protected service-to-service access

## Install

You can pre-create secrets yourself or let the installer create them when credentials are supplied
as flags. The canonical installer lives at [`bin/install-bakery.sh`](../bin/install-bakery.sh) and
installs the published OCI chart `oci://ghcr.io/rackerlabs/charts/bakery` by default.

Example Rackspace Core secret:

```bash
kubectl -n bakery create secret generic bakery-rackspace-core \
  --from-literal=rackspace-core-url='<rackspace-core-url>' \
  --from-literal=rackspace-core-username='<rackspace-core-username>' \
  --from-literal=rackspace-core-password='<rackspace-core-password>'
```

Optional HMAC auth secret:

```bash
kubectl -n bakery create secret generic bakery-hmac \
  --from-literal=active-key-id=active \
  --from-literal=active-key="$(openssl rand -base64 32)"
```

Install Bakery with the OCI installer:

```bash
export BAKERY_NAMESPACE="bakery"
./bin/install-bakery.sh \
  --bakery-active-provider rackspace_core \
  --bakery-auth-secret-name bakery-hmac
```

Install Bakery while having the installer create the Rackspace Core secret:

```bash
./bin/install-bakery.sh \
  --bakery-active-provider rackspace_core \
  --bakery-rackspace-url <rackspace-core-url> \
  --bakery-rackspace-username <rackspace-core-username> \
  --bakery-rackspace-password '<rackspace-core-password>'
```

Override the OCI chart version when needed:

```bash
BAKERY_CHART_VERSION="0.1.0" ./bin/install-bakery.sh --bakery-auth-secret-name bakery-hmac
```

## Gateway Publication

To expose Bakery for remote PoundCake clients, set the Gateway API values in your override file:

```yaml
bakery:
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

## Verification

```bash
helm list -n bakery
kubectl -n bakery get deploy,job,svc
curl -fsS https://bakery.example.com/api/v1/health
```

If you are wiring PoundCake to a remote Bakery instance, continue with
[REMOTE_BAKERY_DEPLOYMENT_GUIDE.md](REMOTE_BAKERY_DEPLOYMENT_GUIDE.md).
