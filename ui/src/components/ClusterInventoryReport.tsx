import { useMemo, useState } from "react";

import { buildClusterInventoryMarkdown, clusterInventoryHighlights, asInventoryRows } from "../lib/clusterInventory";
import { formatBytes, formatCount, formatCpuMillicores, formatDateTime } from "../lib/format";

type InventoryRow = Record<string, unknown>;

type Column = {
  key: string;
  label: string;
  render?: (row: InventoryRow) => string;
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function stringifyValue(value: unknown, fallback = "-"): string {
  if (value === null || value === undefined) {
    return fallback;
  }
  if (Array.isArray(value)) {
    return value.length > 0 ? value.map((item) => stringifyValue(item, "")).filter(Boolean).join(", ") : fallback;
  }
  if (typeof value === "object") {
    const entries = Object.entries(asRecord(value));
    return entries.length > 0
      ? entries.map(([key, item]) => `${key}=${stringifyValue(item, "")}`).join(", ")
      : fallback;
  }
  const normalized = String(value).trim();
  return normalized || fallback;
}

function asNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function downloadTextFile(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function InventoryTable({
  title,
  subtitle,
  columns,
  rows,
  emptyMessage,
}: {
  title: string;
  subtitle?: string;
  columns: Column[];
  rows: InventoryRow[];
  emptyMessage: string;
}) {
  return (
    <section className="detail-card">
      <div className="section-header">
        <div>
          <h3>{title}</h3>
          {subtitle ? <p className="subtle-copy">{subtitle}</p> : null}
        </div>
      </div>
      {rows.length === 0 ? (
        <div className="empty-state compact">{emptyMessage}</div>
      ) : (
        <div className="mini-table-shell">
          <table className="mini-table">
            <thead>
              <tr>
                {columns.map((column) => (
                  <th key={column.key}>{column.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={`${title}-${index}`}>
                  {columns.map((column) => (
                    <td key={column.key}>{column.render ? column.render(row) : stringifyValue(row[column.key])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function MetadataDetails({
  title,
  rows,
  emptyMessage,
}: {
  title: string;
  rows: InventoryRow[];
  emptyMessage: string;
}) {
  if (rows.length === 0) {
    return (
      <section className="detail-card">
        <div className="section-header">
          <div>
            <h3>{title}</h3>
          </div>
        </div>
        <div className="empty-state compact">{emptyMessage}</div>
      </section>
    );
  }

  return (
    <section className="detail-card">
      <div className="section-header">
        <div>
          <h3>{title}</h3>
          <p className="subtle-copy">Labels, annotations, addresses, and taints stay easy to inspect without opening raw JSON.</p>
        </div>
      </div>
      <div className="metadata-grid">
        {rows.map((row, index) => {
          const labels = asRecord(row.labels);
          const annotations = asRecord(row.annotations);
          const addresses = Array.isArray(row.addresses) ? row.addresses : [];
          const taints = Array.isArray(row.taints) ? row.taints : [];
          return (
            <details className="metadata-card" key={`${title}-${index}`}>
              <summary>
                <strong>{stringifyValue(row.name)}</strong>
                <span>
                  {Object.keys(labels).length} labels · {Object.keys(annotations).length} annotations
                </span>
              </summary>
              <div className="metadata-sections">
                <div>
                  <h4>Labels</h4>
                  <pre>{JSON.stringify(labels, null, 2)}</pre>
                </div>
                <div>
                  <h4>Annotations</h4>
                  <pre>{JSON.stringify(annotations, null, 2)}</pre>
                </div>
                <div>
                  <h4>Addresses</h4>
                  <pre>{JSON.stringify(addresses, null, 2)}</pre>
                </div>
                <div>
                  <h4>Taints</h4>
                  <pre>{JSON.stringify(taints, null, 2)}</pre>
                </div>
              </div>
            </details>
          );
        })}
      </div>
    </section>
  );
}

export function ClusterInventoryReport({ result }: { result: Record<string, unknown> }) {
  const [nodeSearch, setNodeSearch] = useState("");
  const summary = asRecord(result.cluster_summary);
  const nodes = asInventoryRows(result.nodes);
  const storageClasses = asInventoryRows(result.storage_classes);
  const persistentVolumes = asInventoryRows(result.persistent_volumes);
  const persistentVolumeClaims = asInventoryRows(result.persistent_volume_claims);
  const pods = asInventoryRows(result.pods);
  const deployments = asInventoryRows(result.deployments);
  const statefulsets = asInventoryRows(result.statefulsets);
  const services = asInventoryRows(result.services);
  const highlights = clusterInventoryHighlights(result);

  const filteredNodes = useMemo(() => {
    const needle = nodeSearch.trim().toLowerCase();
    if (!needle) {
      return nodes;
    }
    return nodes.filter((node) =>
      JSON.stringify({
        name: node.name,
        roles: node.roles,
        labels: node.labels,
        annotations: node.annotations,
      })
        .toLowerCase()
        .includes(needle),
    );
  }, [nodeSearch, nodes]);

  return (
    <div className="result-stack">
      <div className="metric-row">
        <article className="inline-metric">
          <span>Collected</span>
          <strong>{formatDateTime(stringifyValue(result.collected_at, ""))}</strong>
        </article>
        <article className="inline-metric">
          <span>Namespace snapshot</span>
          <strong>{stringifyValue(result.namespace, "default")}</strong>
        </article>
        <article className="inline-metric">
          <span>Nodes</span>
          <strong>{formatCount(Number(summary.node_count ?? result.node_count ?? nodes.length))}</strong>
        </article>
        <article className="inline-metric">
          <span>Ready nodes</span>
          <strong>{formatCount(Number(summary.ready_node_count ?? result.ready_node_count ?? 0))}</strong>
        </article>
        <article className="inline-metric">
          <span>Allocatable CPU</span>
          <strong>{formatCpuMillicores(asNumber(asRecord(summary.allocatable).cpu_millicores))}</strong>
        </article>
        <article className="inline-metric">
          <span>Allocatable memory</span>
          <strong>{formatBytes(asNumber(asRecord(summary.allocatable).memory_bytes))}</strong>
        </article>
      </div>

      <section className="detail-card">
        <div className="panel-header">
          <div>
            <h3>Inventory report</h3>
            <p className="subtle-copy">
              Cluster-wide node and storage inventory with a namespace-scoped workload snapshot.
            </p>
          </div>
          <div className="panel-actions">
            <button
              type="button"
              className="ghost-button"
              onClick={() =>
                downloadTextFile(
                  `bakery-cluster-inventory-${stringifyValue(result.namespace, "default")}.md`,
                  buildClusterInventoryMarkdown(result),
                  "text/markdown",
                )
              }
            >
              Export Markdown
            </button>
          </div>
        </div>
        <div className="inventory-highlight-grid">
          {highlights.map((highlight) => (
            <div className="inventory-highlight" key={highlight}>
              {highlight}
            </div>
          ))}
        </div>
      </section>

      <label className="inventory-search">
        <span>Search node inventory</span>
        <input value={nodeSearch} onChange={(event) => setNodeSearch(event.target.value)} placeholder="Search nodes, roles, labels, annotations" />
      </label>

      <InventoryTable
        title="Nodes"
        subtitle="Search by node name, roles, labels, or annotations."
        columns={[
          { key: "name", label: "Name" },
          {
            key: "ready",
            label: "Ready",
            render: (row) => (row.ready ? "Yes" : "No"),
          },
          {
            key: "roles",
            label: "Roles",
            render: (row) => stringifyValue(row.roles),
          },
          {
            key: "schedulable",
            label: "Schedulable",
            render: (row) => (row.schedulable ? "Yes" : "No"),
          },
          { key: "kubelet_version", label: "Kubelet" },
          { key: "container_runtime_version", label: "Runtime" },
          { key: "allocatable_cpu", label: "CPU allocatable" },
          { key: "allocatable_memory", label: "Memory allocatable" },
        ]}
        rows={filteredNodes}
        emptyMessage="No nodes matched the current search."
      />

      <MetadataDetails
        title="Node metadata drilldown"
        rows={filteredNodes}
        emptyMessage="No node metadata matched the current search."
      />

      <InventoryTable
        title="Storage classes"
        columns={[
          { key: "name", label: "Name" },
          { key: "provisioner", label: "Provisioner" },
          { key: "volume_binding_mode", label: "Binding mode" },
          {
            key: "allow_volume_expansion",
            label: "Expansion",
            render: (row) => (row.allow_volume_expansion ? "Yes" : "No"),
          },
          { key: "reclaim_policy", label: "Reclaim" },
        ]}
        rows={storageClasses}
        emptyMessage="No storage classes returned."
      />

      <InventoryTable
        title="Persistent volumes"
        columns={[
          { key: "name", label: "Name" },
          { key: "phase", label: "Phase" },
          { key: "storage_class_name", label: "Storage class" },
          { key: "capacity", label: "Capacity" },
          { key: "claim_ref", label: "Claim" },
        ]}
        rows={persistentVolumes}
        emptyMessage="No persistent volumes returned."
      />

      <InventoryTable
        title="Persistent volume claims"
        columns={[
          { key: "name", label: "Name" },
          { key: "namespace", label: "Namespace" },
          { key: "phase", label: "Phase" },
          { key: "storage_class_name", label: "Storage class" },
          { key: "requested_storage", label: "Requested" },
        ]}
        rows={persistentVolumeClaims}
        emptyMessage="No persistent volume claims returned."
      />

      <InventoryTable
        title="Pods"
        columns={[
          { key: "name", label: "Name" },
          { key: "phase", label: "Phase" },
          { key: "node_name", label: "Node" },
          { key: "restart_count", label: "Restarts" },
          { key: "pod_ip", label: "Pod IP" },
        ]}
        rows={pods}
        emptyMessage="No pods returned."
      />

      <InventoryTable
        title="Deployments"
        columns={[
          { key: "name", label: "Name" },
          { key: "ready_replicas", label: "Ready" },
          { key: "available_replicas", label: "Available" },
          { key: "replicas", label: "Desired" },
        ]}
        rows={deployments}
        emptyMessage="No deployments returned."
      />

      <InventoryTable
        title="StatefulSets"
        columns={[
          { key: "name", label: "Name" },
          { key: "ready_replicas", label: "Ready" },
          { key: "replicas", label: "Desired" },
          { key: "service_name", label: "Service" },
        ]}
        rows={statefulsets}
        emptyMessage="No statefulsets returned."
      />

      <InventoryTable
        title="Services"
        columns={[
          { key: "name", label: "Name" },
          { key: "type", label: "Type" },
          { key: "cluster_ip", label: "Cluster IP" },
          {
            key: "ports",
            label: "Ports",
            render: (row) => stringifyValue(row.ports),
          },
        ]}
        rows={services}
        emptyMessage="No services returned."
      />

      <section className="detail-card">
        <div className="section-header">
          <div>
            <h3>Environment health cues</h3>
            <p className="subtle-copy">Small operational hints pulled from the inventory snapshot.</p>
          </div>
        </div>
        <div className="callout-stack">
          <div className={`inline-alert ${Number(summary.ready_node_count ?? 0) < Number(summary.node_count ?? 0) ? "warning" : "info"}`}>
            <strong>Node readiness</strong>
            <span>
              {formatCount(Number(summary.ready_node_count ?? 0))} of {formatCount(Number(summary.node_count ?? 0))} nodes reported Ready.
            </span>
          </div>
          <div className="inline-alert info">
            <strong>Workload scope</strong>
            <span>
              Workload and PVC sections are scoped to {stringifyValue(result.namespace, "default")} while nodes, storage classes, and persistent volumes are cluster-wide.
            </span>
          </div>
          <div className="inline-alert info">
            <strong>Collected resource mix</strong>
            <span>
              {formatCount(pods.length)} pods, {formatCount(deployments.length)} deployments, {formatCount(statefulsets.length)} statefulsets, and {formatCount(services.length)} services were captured.
            </span>
          </div>
        </div>
      </section>
    </div>
  );
}
