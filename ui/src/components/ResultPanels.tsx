import type { CollectionJob } from "../contracts";
import { formatDateTime, formatCount } from "../lib/format";
import { JsonPanel } from "./JsonPanel";
import { StatusBadge } from "./StatusBadge";

function renderRows(rows: Array<Record<string, unknown>>, emptyMessage: string) {
  if (rows.length === 0) {
    return <div className="empty-state compact">{emptyMessage}</div>;
  }
  const columns = Object.keys(rows[0]);
  return (
    <div className="mini-table-shell">
      <table className="mini-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column.replace(/_/g, " ")}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {columns.map((column) => (
                <td key={column}>{String(row[column] ?? "-")}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DiagnosticsResult({ result }: { result: Record<string, unknown> }) {
  const health = (result.health ?? {}) as Record<string, unknown>;
  const components = (health.components ?? {}) as Record<string, { status?: string; message?: string }>;
  const bakeryMonitorState =
    (result.bakery_monitor_state as Record<string, unknown> | null | undefined) ?? null;

  return (
    <div className="result-stack">
      <div className="metric-row">
        <article className="inline-metric">
          <span>Collector</span>
          <strong>{String(result.collector_type ?? "monitor_diagnostics")}</strong>
        </article>
        <article className="inline-metric">
          <span>Monitor</span>
          <strong>{String(result.monitor_id ?? "-")}</strong>
        </article>
        <article className="inline-metric">
          <span>Version</span>
          <strong>{String(result.app_version ?? "-")}</strong>
        </article>
        <article className="inline-metric">
          <span>Collected</span>
          <strong>{formatDateTime(String(result.collected_at ?? ""))}</strong>
        </article>
      </div>

      <section className="detail-card">
        <div className="panel-header">
          <h3>Health snapshot</h3>
          <StatusBadge status={String(health.status ?? "unknown")} />
        </div>
        <div className="component-grid">
          {Object.entries(components).map(([name, component]) => (
            <article className="component-card" key={name}>
              <div className="component-card-header">
                <strong>{name}</strong>
                <StatusBadge status={String(component.status ?? "unknown")} />
              </div>
              <p>{component.message || "No detail provided."}</p>
            </article>
          ))}
        </div>
      </section>

      {bakeryMonitorState ? (
        <section className="detail-card">
          <h3>Bakery monitor state</h3>
          {renderRows([bakeryMonitorState], "No monitor state recorded.")}
        </section>
      ) : null}
    </div>
  );
}

function ClusterInventoryResult({ result }: { result: Record<string, unknown> }) {
  const pods = Array.isArray(result.pods) ? (result.pods as Array<Record<string, unknown>>) : [];
  const deployments = Array.isArray(result.deployments)
    ? (result.deployments as Array<Record<string, unknown>>)
    : [];
  const statefulsets = Array.isArray(result.statefulsets)
    ? (result.statefulsets as Array<Record<string, unknown>>)
    : [];
  const services = Array.isArray(result.services)
    ? (result.services as Array<Record<string, unknown>>)
    : [];

  return (
    <div className="result-stack">
      <div className="metric-row">
        <article className="inline-metric">
          <span>Namespace</span>
          <strong>{String(result.namespace ?? "default")}</strong>
        </article>
        <article className="inline-metric">
          <span>Pods</span>
          <strong>{formatCount(Number(result.pod_count ?? 0))}</strong>
        </article>
        <article className="inline-metric">
          <span>Deployments</span>
          <strong>{formatCount(Number(result.deployment_count ?? 0))}</strong>
        </article>
        <article className="inline-metric">
          <span>Services</span>
          <strong>{formatCount(Number(result.service_count ?? 0))}</strong>
        </article>
      </div>
      <section className="detail-card">
        <h3>Pods</h3>
        {renderRows(pods, "No pods returned.")}
      </section>
      <section className="detail-card">
        <h3>Deployments</h3>
        {renderRows(deployments, "No deployments returned.")}
      </section>
      <section className="detail-card">
        <h3>StatefulSets</h3>
        {renderRows(statefulsets, "No statefulsets returned.")}
      </section>
      <section className="detail-card">
        <h3>Services</h3>
        {renderRows(services, "No services returned.")}
      </section>
    </div>
  );
}

function TicketContextResult({ result }: { result: Record<string, unknown> }) {
  const orders = Array.isArray(result.orders) ? (result.orders as Array<Record<string, unknown>>) : [];
  const communications = Array.isArray(result.communications)
    ? (result.communications as Array<Record<string, unknown>>)
    : [];
  const dishes = Array.isArray(result.dishes) ? (result.dishes as Array<Record<string, unknown>>) : [];

  return (
    <div className="result-stack">
      <div className="metric-row">
        <article className="inline-metric">
          <span>Orders</span>
          <strong>{formatCount(orders.length)}</strong>
        </article>
        <article className="inline-metric">
          <span>Communications</span>
          <strong>{formatCount(communications.length)}</strong>
        </article>
        <article className="inline-metric">
          <span>Dishes</span>
          <strong>{formatCount(dishes.length)}</strong>
        </article>
        <article className="inline-metric">
          <span>Collected</span>
          <strong>{formatDateTime(String(result.collected_at ?? ""))}</strong>
        </article>
      </div>
      <section className="detail-card">
        <h3>Orders</h3>
        {renderRows(orders, "No matching orders returned.")}
      </section>
      <section className="detail-card">
        <h3>Communications</h3>
        {renderRows(communications, "No matching communications returned.")}
      </section>
      <section className="detail-card">
        <h3>Dishes</h3>
        {renderRows(dishes, "No matching dishes returned.")}
      </section>
    </div>
  );
}

export function CollectionJobResultPanel({ job }: { job: CollectionJob }) {
  const result = job.result ?? {};

  return (
    <div className="result-layout">
      {job.status === "succeeded" ? (
        <>
          {job.collector_type === "monitor_diagnostics" ? <DiagnosticsResult result={result} /> : null}
          {job.collector_type === "cluster_inventory" ? <ClusterInventoryResult result={result} /> : null}
          {job.collector_type === "ticket_context" ? <TicketContextResult result={result} /> : null}
        </>
      ) : null}
      <JsonPanel
        title="Raw result"
        value={job.result ?? { status: job.status, error: job.error }}
        filename={`bakery-job-${job.job_id}.json`}
      />
    </div>
  );
}
