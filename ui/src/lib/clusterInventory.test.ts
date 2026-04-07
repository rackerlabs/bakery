import { describe, expect, it } from "vitest";

import { buildClusterInventoryMarkdown, clusterInventoryHighlights } from "./clusterInventory";

const result = {
  collected_at: "2026-04-06T21:30:00Z",
  namespace: "rackspace",
  cluster_summary: {
    node_count: 2,
    ready_node_count: 2,
    storage_class_count: 1,
    persistent_volume_count: 3,
    persistent_volume_claim_count: 2,
    pod_count: 4,
    deployment_count: 2,
    statefulset_count: 1,
    service_count: 2,
    capacity: {
      cpu_millicores: 8000,
      memory_bytes: 34359738368,
      ephemeral_storage_bytes: 536870912000,
    },
    allocatable: {
      cpu_millicores: 7600,
      memory_bytes: 30064771072,
      ephemeral_storage_bytes: 500000000000,
    },
  },
  nodes: [
    {
      name: "worker-1",
      ready: true,
      roles: ["worker"],
      kubelet_version: "v1.31.0",
      allocatable_cpu: "3800m",
      allocatable_memory: "14Gi",
    },
  ],
  storage_classes: [{ name: "fast", provisioner: "csi.example", volume_binding_mode: "WaitForFirstConsumer" }],
  persistent_volumes: [{ name: "pv-1", phase: "Bound", storage_class_name: "fast", capacity: "100Gi", claim_ref: "rackspace/pvc-1" }],
  persistent_volume_claims: [{ name: "pvc-1", namespace: "rackspace", phase: "Bound", storage_class_name: "fast", requested_storage: "100Gi" }],
  pods: [{ name: "api-1", phase: "Running", node_name: "worker-1", restart_count: 0, pod_ip: "10.0.0.10" }],
  deployments: [{ name: "api", ready_replicas: 2, available_replicas: 2, replicas: 2 }],
  statefulsets: [{ name: "db", ready_replicas: 1, replicas: 1, service_name: "db" }],
  services: [{ name: "api", type: "ClusterIP", cluster_ip: "10.0.0.1", ports: ["80/TCP"] }],
};

describe("cluster inventory report helpers", () => {
  it("builds human-readable highlights", () => {
    expect(clusterInventoryHighlights(result)).toContain("2 of 2 nodes ready");
  });

  it("builds a markdown report from the inventory result", () => {
    const markdown = buildClusterInventoryMarkdown(result);

    expect(markdown).toContain("# Cluster Inventory Report");
    expect(markdown).toContain("## Nodes");
    expect(markdown).toContain("worker-1");
    expect(markdown).toContain("## Persistent Volumes");
    expect(markdown).toContain("## Services");
  });
});
