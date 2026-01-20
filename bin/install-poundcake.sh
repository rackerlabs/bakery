#!/bin/bash
# shellcheck disable=SC2124,SC2145,SC2294

# Configuration
NAMESPACE="${POUNDCAKE_NAMESPACE:-poundcake}"
RELEASE_NAME="${POUNDCAKE_RELEASE_NAME:-poundcake}"
CHART_REPO="oci://ghcr.io/aedan/charts/poundcake"
GLOBAL_OVERRIDES_DIR="/etc/platform-config/helm-configs/global_overrides"
SERVICE_CONFIG_DIR="/srv/config/poundcake"
BASE_OVERRIDES="/opt/platform-config/base-helm-configs/poundcake/poundcake-helm-overrides.yaml"

# Read poundcake version from helm-chart-versions.yaml
VERSION_FILE="/srv/config/chart-versions.yaml"
if [ -f "$VERSION_FILE" ]; then
    # Extract poundcake version using grep and sed
    POUNDCAKE_VERSION=$(grep 'poundcake:' "$VERSION_FILE" | sed 's/.*poundcake: *//')
fi

# Use environment variable as fallback, or default to "latest"
POUNDCAKE_VERSION="${POUNDCAKE_VERSION:-${POUNDCAKE_CHART_VERSION:-0.1.10}}"

echo "Installing PoundCake version: ${POUNDCAKE_VERSION}"

HELM_CMD="helm upgrade --install ${RELEASE_NAME} ${CHART_REPO} \
  --version ${POUNDCAKE_VERSION} \
  --namespace=${NAMESPACE} \
  --create-namespace \
  --timeout 120m"

# Add post-renderer if available AND overlay exists
if [ -f "/etc/platform-config/kustomize/kustomize.sh" ] && [ -d "/etc/platform-config/kustomize/poundcake/overlay" ]; then
    HELM_CMD+=" --post-renderer /etc/platform-config/kustomize/kustomize.sh"
    HELM_CMD+=" --post-renderer-args poundcake/overlay"
fi

# Add base overrides if they exist
if [ -f "${BASE_OVERRIDES}" ]; then
    HELM_CMD+=" -f ${BASE_OVERRIDES}"
fi

for dir in "$GLOBAL_OVERRIDES_DIR" "$SERVICE_CONFIG_DIR"; do
    if compgen -G "${dir}/*.yaml" > /dev/null; then
        for yaml_file in "${dir}"/*.yaml; do
            HELM_CMD+=" -f ${yaml_file}"
        done
    fi
done

HELM_CMD+=" $@"

echo "Executing Helm command:"
echo "${HELM_CMD}"
eval "${HELM_CMD}"
