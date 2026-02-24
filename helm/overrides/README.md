# Helm Overrides

This directory stores example override files for Helm installs.

Canonical image keys for overrides:
- `poundcakeImage.repository` / `poundcakeImage.tag`
- `uiImage.repository` / `uiImage.tag`
- `bakery.image.repository` / `bakery.image.tag`

Base example source in-repo:
- `helm/base-overrides/poundcake-helm-overrides-examples.yaml`
  (copy/merge into `/srv/config/poundcake/poundcake-helm-overrides.yaml`)

Service selection in overrides now uses explicit booleans:
- `poundcake.enabled` (PoundCake + StackStorm resources)
- `bakery.enabled` (Bakery resources)

Wrapper target mapping:
- `./install/install-poundcake-helm.sh --target poundcake` => `poundcake.enabled=true`, `bakery.enabled=false`
- `./install/install-poundcake-helm.sh --target bakery` => `poundcake.enabled=false`, `bakery.enabled=true`
- `./install/install-poundcake-helm.sh --target both` => both enabled

## Enable HA

1. Copy the HA example to the Genestack PoundCake overrides path:

```bash
sudo mkdir -p /srv/config/poundcake
sudo cp helm/overrides/ha-overrides.yaml /srv/config/poundcake/poundcake-helm-overrides.yaml
```

2. Run the Helm installer:

```bash
./install/install-poundcake-helm.sh
```

The installer will automatically include:

- `/opt/platform-config/base-helm-configs/poundcake/poundcake-helm-overrides.yaml`
- `/etc/platform-config/helm-configs/global_overrides/*.yaml`
- `/srv/config/poundcake/*.yaml`
- kustomize post-renderer from `/etc/platform-config/kustomize` (when present)

## Verify

```bash
kubectl -n rackspace get deploy poundcake poundcake-chef poundcake-timer poundcake-dishwasher
kubectl -n rackspace get svc poundcake
```

## Enable Envoy Gateway Route/Listener (Kronos)

Use the provided Kronos Gateway override to create/update:
- Gateway listener on `HTTPS`/`443`
- HTTPRoute for `poundcake.api.example-environment.example-domain.net`

1. Review and adjust gateway object names/namespace and TLS secret:

```bash
cat helm/overrides/gateway-example-environment-overrides.yaml
```

2. Copy into the active Genestack PoundCake override path:

```bash
sudo mkdir -p /srv/config/poundcake
sudo cp helm/overrides/gateway-example-environment-overrides.yaml /srv/config/poundcake/poundcake-helm-overrides.yaml
```

3. Install/upgrade:

```bash
./install/install-poundcake-helm.sh
```
