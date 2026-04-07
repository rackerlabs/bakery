import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ClusterInventoryReport } from "./ClusterInventoryReport";

const result = {
  collected_at: "2026-04-06T21:30:00Z",
  namespace: "rackspace",
  cluster_summary: {
    node_count: 2,
    ready_node_count: 1,
    capacity: {
      cpu_millicores: 8000,
      memory_bytes: 34359738368,
    },
    allocatable: {
      cpu_millicores: 7600,
      memory_bytes: 30064771072,
    },
  },
  nodes: [
    {
      name: "worker-1",
      ready: true,
      roles: ["worker"],
      schedulable: true,
      kubelet_version: "v1.31.0",
      container_runtime_version: "containerd://2.0",
      allocatable_cpu: "3800m",
      allocatable_memory: "14Gi",
      labels: { "topology.kubernetes.io/zone": "zone-a" },
      annotations: {},
      addresses: [],
      taints: [],
    },
    {
      name: "worker-2",
      ready: false,
      roles: ["worker"],
      schedulable: false,
      kubelet_version: "v1.31.0",
      container_runtime_version: "containerd://2.0",
      allocatable_cpu: "3800m",
      allocatable_memory: "14Gi",
      labels: { "topology.kubernetes.io/zone": "zone-b" },
      annotations: { drained: "true" },
      addresses: [],
      taints: [],
    },
  ],
  storage_classes: [],
  persistent_volumes: [],
  persistent_volume_claims: [],
  pods: [],
  deployments: [],
  statefulsets: [],
  services: [],
};

describe("ClusterInventoryReport", () => {
  it("renders summary content and filters node inventory", async () => {
    const user = userEvent.setup();
    render(<ClusterInventoryReport result={result} />);

    expect(screen.getByText(/inventory report/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /export markdown/i })).toBeInTheDocument();
    expect(screen.getAllByText("worker-1").length).toBeGreaterThan(0);
    expect(screen.getAllByText("worker-2").length).toBeGreaterThan(0);

    await user.type(screen.getByPlaceholderText(/search nodes/i), "worker-2");

    expect(screen.queryByText("worker-1")).not.toBeInTheDocument();
    expect(screen.getAllByText("worker-2").length).toBeGreaterThan(0);
  });
});
