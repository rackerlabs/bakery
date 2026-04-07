import { formatBytes, formatCpuMillicores } from "./format";

type InventoryRow = Record<string, unknown>;

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export function asInventoryRows(value: unknown): InventoryRow[] {
  return Array.isArray(value)
    ? value.filter((item): item is InventoryRow => Boolean(item) && typeof item === "object" && !Array.isArray(item))
    : [];
}

function asString(value: unknown, fallback = "-"): string {
  const normalized = String(value ?? "").trim();
  return normalized || fallback;
}

function asNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function joinList(value: unknown): string {
  if (!Array.isArray(value)) {
    return asString(value);
  }
  return value.length > 0 ? value.map((item) => asString(item)).join(", ") : "-";
}

function markdownTable(headers: string[], rows: string[][]): string {
  if (rows.length === 0) {
    return "_No rows returned._";
  }
  const headerRow = `| ${headers.join(" | ")} |`;
  const dividerRow = `| ${headers.map(() => "---").join(" | ")} |`;
  const body = rows.map((row) => `| ${row.join(" | ")} |`).join("\n");
  return `${headerRow}\n${dividerRow}\n${body}`;
}

function cleanMarkdownCell(value: unknown): string {
  return asString(value).replace(/\|/g, "\\|").replace(/\n/g, " ");
}

export function clusterInventoryHighlights(result: Record<string, unknown>): string[] {
  const report = asRecord(result.report);
  const configuredHighlights = Array.isArray(report.highlights)
    ? report.highlights.map((item) => asString(item, "")).filter(Boolean)
    : [];
  if (configuredHighlights.length > 0) {
    return configuredHighlights;
  }

  const summary = asRecord(result.cluster_summary);
  return [
    `${summary.ready_node_count ?? result.ready_node_count ?? 0} of ${summary.node_count ?? result.node_count ?? 0} nodes ready`,
    `${summary.persistent_volume_count ?? result.persistent_volume_count ?? 0} persistent volumes across ${summary.storage_class_count ?? result.storage_class_count ?? 0} storage classes`,
    `${summary.pod_count ?? result.pod_count ?? 0} pods, ${summary.deployment_count ?? result.deployment_count ?? 0} deployments, ${summary.statefulset_count ?? result.statefulset_count ?? 0} statefulsets in ${asString(result.namespace, "default")}`,
  ].filter(Boolean);
}

export function buildClusterInventoryMarkdown(result: Record<string, unknown>): string {
  const summary = asRecord(result.cluster_summary);
  const nodes = asInventoryRows(result.nodes);
  const storageClasses = asInventoryRows(result.storage_classes);
  const persistentVolumes = asInventoryRows(result.persistent_volumes);
  const persistentVolumeClaims = asInventoryRows(result.persistent_volume_claims);
  const pods = asInventoryRows(result.pods);
  const deployments = asInventoryRows(result.deployments);
  const statefulsets = asInventoryRows(result.statefulsets);
  const services = asInventoryRows(result.services);
  const namespace = asString(result.namespace, "default");
  const capacity = asRecord(summary.capacity);
  const allocatable = asRecord(summary.allocatable);

  const sections = [
    "# Cluster Inventory Report",
    "",
    `Generated: ${asString(result.collected_at, "Unknown")}`,
    `Namespace workload snapshot: ${namespace}`,
    "",
    "## Highlights",
    ...clusterInventoryHighlights(result).map((item) => `- ${item}`),
    "",
    "## Cluster Summary",
    `- Nodes: ${summary.node_count ?? result.node_count ?? 0} total / ${summary.ready_node_count ?? result.ready_node_count ?? 0} ready`,
    `- Storage: ${summary.storage_class_count ?? result.storage_class_count ?? 0} storage classes, ${summary.persistent_volume_count ?? result.persistent_volume_count ?? 0} persistent volumes, ${summary.persistent_volume_claim_count ?? result.persistent_volume_claim_count ?? 0} persistent volume claims`,
    `- Workloads: ${summary.pod_count ?? result.pod_count ?? 0} pods, ${summary.deployment_count ?? result.deployment_count ?? 0} deployments, ${summary.statefulset_count ?? result.statefulset_count ?? 0} statefulsets, ${summary.service_count ?? result.service_count ?? 0} services`,
    `- Capacity: ${formatCpuMillicores(asNumber(capacity.cpu_millicores))} CPU, ${formatBytes(asNumber(capacity.memory_bytes))} memory, ${formatBytes(asNumber(capacity.ephemeral_storage_bytes))} ephemeral storage`,
    `- Allocatable: ${formatCpuMillicores(asNumber(allocatable.cpu_millicores))} CPU, ${formatBytes(asNumber(allocatable.memory_bytes))} memory, ${formatBytes(asNumber(allocatable.ephemeral_storage_bytes))} ephemeral storage`,
    "",
    "## Nodes",
    markdownTable(
      ["Name", "Ready", "Roles", "Kubelet", "CPU allocatable", "Memory allocatable"],
      nodes.map((node) => [
        cleanMarkdownCell(node.name),
        cleanMarkdownCell(node.ready ? "yes" : "no"),
        cleanMarkdownCell(joinList(node.roles)),
        cleanMarkdownCell(node.kubelet_version),
        cleanMarkdownCell(node.allocatable_cpu),
        cleanMarkdownCell(node.allocatable_memory),
      ]),
    ),
    "",
    "## Storage Classes",
    markdownTable(
      ["Name", "Provisioner", "Binding mode", "Expansion", "Reclaim"],
      storageClasses.map((item) => [
        cleanMarkdownCell(item.name),
        cleanMarkdownCell(item.provisioner),
        cleanMarkdownCell(item.volume_binding_mode),
        cleanMarkdownCell(item.allow_volume_expansion ? "yes" : "no"),
        cleanMarkdownCell(item.reclaim_policy),
      ]),
    ),
    "",
    "## Persistent Volumes",
    markdownTable(
      ["Name", "Phase", "Storage class", "Capacity", "Claim"],
      persistentVolumes.map((item) => [
        cleanMarkdownCell(item.name),
        cleanMarkdownCell(item.phase),
        cleanMarkdownCell(item.storage_class_name),
        cleanMarkdownCell(item.capacity),
        cleanMarkdownCell(item.claim_ref),
      ]),
    ),
    "",
    "## Persistent Volume Claims",
    markdownTable(
      ["Name", "Namespace", "Phase", "Storage class", "Requested"],
      persistentVolumeClaims.map((item) => [
        cleanMarkdownCell(item.name),
        cleanMarkdownCell(item.namespace),
        cleanMarkdownCell(item.phase),
        cleanMarkdownCell(item.storage_class_name),
        cleanMarkdownCell(item.requested_storage),
      ]),
    ),
    "",
    "## Pods",
    markdownTable(
      ["Name", "Phase", "Node", "Restarts", "Pod IP"],
      pods.map((item) => [
        cleanMarkdownCell(item.name),
        cleanMarkdownCell(item.phase),
        cleanMarkdownCell(item.node_name),
        cleanMarkdownCell(item.restart_count),
        cleanMarkdownCell(item.pod_ip),
      ]),
    ),
    "",
    "## Deployments",
    markdownTable(
      ["Name", "Ready", "Available", "Desired"],
      deployments.map((item) => [
        cleanMarkdownCell(item.name),
        cleanMarkdownCell(item.ready_replicas),
        cleanMarkdownCell(item.available_replicas),
        cleanMarkdownCell(item.replicas),
      ]),
    ),
    "",
    "## StatefulSets",
    markdownTable(
      ["Name", "Ready", "Desired", "Service"],
      statefulsets.map((item) => [
        cleanMarkdownCell(item.name),
        cleanMarkdownCell(item.ready_replicas),
        cleanMarkdownCell(item.replicas),
        cleanMarkdownCell(item.service_name),
      ]),
    ),
    "",
    "## Services",
    markdownTable(
      ["Name", "Type", "Cluster IP", "Ports"],
      services.map((item) => [
        cleanMarkdownCell(item.name),
        cleanMarkdownCell(item.type),
        cleanMarkdownCell(item.cluster_ip),
        cleanMarkdownCell(joinList(item.ports)),
      ]),
    ),
    "",
  ];
  return sections.join("\n");
}
