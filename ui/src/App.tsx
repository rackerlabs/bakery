import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { type FormEvent, useEffect, useMemo, useState } from "react";
import {
  Link,
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useSearchParams,
} from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ApiError, api } from "./api";
import { CollectionJobResultPanel } from "./components/ResultPanels";
import { OperatorTable } from "./components/OperatorTable";
import { SearchableMonitorPicker } from "./components/SearchableMonitorPicker";
import { StatusBadge } from "./components/StatusBadge";
import { buildAuthHref, buildLoginReturnTarget } from "./config";
import type {
  AuthMeResponse,
  BacklogRow,
  CollectionCollector,
  CollectionJob,
  FilterOptions,
  MonitorDetail,
  MonitorEventRow,
  MonitorFilterOption,
  MonitorRow,
  OperationAnalyticsRow,
  Overview,
  ProviderAnalyticsRow,
  ReportFilters,
  RouteRow,
  SettingsResponse,
} from "./contracts";
import { backlogActionState, backlogReasonLabel, backlogReasonMessage } from "./lib/backlog";
import { buildCollectorParameters, getCollectorByType, JOB_STATUS_COPY } from "./lib/collectors";
import {
  formatCount,
  formatDateTime,
  formatDurationFrom,
  formatDurationMs,
  formatRelativeTime,
  humanizeIdentifier,
} from "./lib/format";

const STALE_MONITOR_THRESHOLD_MS = 15 * 60 * 1000;
const PAGE_POLL_INTERVAL_MS = 15_000;
const DETAIL_POLL_INTERVAL_MS = 5_000;
const CHART_COLORS = ["#e6723d", "#2d7f6f", "#bf5f82", "#4d6fc5", "#d6a441", "#865fb6"];

type ConsoleFilters = {
  monitorUuid?: string;
  environmentLabel?: string;
  providerType?: string;
  accountNumber?: string;
};

type NavItem = {
  to: string;
  label: string;
  kicker: string;
};

const NAV_ITEMS: NavItem[] = [
  { to: "/overview", label: "Overview", kicker: "Live health" },
  { to: "/monitors", label: "Monitors", kicker: "Inventory + detail" },
  { to: "/events", label: "Monitor Events", kicker: "Registration + liveness" },
  { to: "/routes", label: "Routes", kicker: "Execution catalog" },
  { to: "/providers", label: "Providers", kicker: "Ticket analytics" },
  { to: "/operations", label: "Operations", kicker: "Queue pressure" },
  { to: "/backlog", label: "Backlog", kicker: "Open work + context" },
  { to: "/jobs", label: "Collection Jobs", kicker: "Queue + results" },
];

function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

function isUnauthorized(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

function optionalParam(value: string | null): string | undefined {
  const trimmed = value?.trim() ?? "";
  return trimmed ? trimmed : undefined;
}

function useDocumentVisible(): boolean {
  const [visible, setVisible] = useState(
    typeof document === "undefined" ? true : document.visibilityState !== "hidden",
  );

  useEffect(() => {
    const handleVisibilityChange = () => {
      setVisible(document.visibilityState !== "hidden");
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, []);

  return visible;
}

function isMonitorStale(monitor: { status: string; last_checkin_at: string | null }): boolean {
  if (monitor.status === "unreachable") {
    return true;
  }
  if (!monitor.last_checkin_at) {
    return true;
  }
  const lastCheckIn = new Date(monitor.last_checkin_at).getTime();
  if (Number.isNaN(lastCheckIn)) {
    return false;
  }
  return Date.now() - lastCheckIn > STALE_MONITOR_THRESHOLD_MS;
}

function trimText(value: string | null | undefined, maxLength = 96): string {
  const normalized = String(value ?? "").trim();
  if (!normalized) {
    return "No detail provided.";
  }
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, maxLength - 1)}…`;
}

function summarizeObject(value: Record<string, unknown> | null | undefined): string {
  if (!value || Object.keys(value).length === 0) {
    return "No payload";
  }
  return trimText(JSON.stringify(value));
}

function collectorLabel(collectors: CollectionCollector[], collectorType: string): string {
  return getCollectorByType(collectors, collectorType)?.label ?? humanizeIdentifier(collectorType);
}

function monitorDescriptor(monitor: MonitorFilterOption | MonitorRow | null | undefined): string {
  if (!monitor) {
    return "No monitor selected";
  }
  const parts = [monitor.environment_label, monitor.cluster_name, monitor.namespace].filter(Boolean);
  return parts.length > 0 ? parts.join(" / ") : "No environment metadata";
}

function hasPermission(me: AuthMeResponse | null, permission: string): boolean {
  return Boolean(me?.permissions.includes(permission) || me?.is_superuser);
}

function mergeFilters(filters: ConsoleFilters, extra: Partial<ReportFilters> = {}): ReportFilters {
  return {
    monitorUuid: filters.monitorUuid,
    environmentLabel: filters.environmentLabel,
    providerType: filters.providerType,
    accountNumber: filters.accountNumber,
    ...extra,
  };
}

function monitorLookup(options: FilterOptions | undefined): Map<string, MonitorFilterOption> {
  return new Map((options?.monitors ?? []).map((monitor) => [monitor.monitor_uuid, monitor]));
}

function findRelatedTicketContextJobs(jobs: CollectionJob[], ticket: BacklogRow): CollectionJob[] {
  return jobs.filter((job) => {
    if (job.collector_type !== "ticket_context" || job.status !== "succeeded") {
      return false;
    }
    const bakeryTicketId = String(job.parameters.bakery_ticket_id ?? "");
    const orderId = String(job.parameters.order_id ?? "");
    if (bakeryTicketId && bakeryTicketId === ticket.ticket_id) {
      return true;
    }
    if (ticket.provider_ticket_id && orderId && orderId === ticket.provider_ticket_id) {
      return true;
    }
    const communications = Array.isArray(job.result?.communications)
      ? (job.result?.communications as Array<Record<string, unknown>>)
      : [];
    return communications.some((communication) =>
      [communication.ticket_id, communication.bakery_ticket_id]
        .filter(Boolean)
        .map((value) => String(value))
        .includes(ticket.ticket_id),
    );
  });
}

function LoadingScreen({ label }: { label: string }) {
  return (
    <div className="loading-shell">
      <div className="loading-card">
        <p className="eyebrow">Bakery Operator Console</p>
        <h1>{label}</h1>
        <p className="subtle-copy">Synchronizing Bakery state, monitor health, and collection data.</p>
      </div>
    </div>
  );
}

function ErrorScreen({
  title,
  message,
  retryLabel,
  onRetry,
}: {
  title: string;
  message: string;
  retryLabel?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="loading-shell">
      <div className="loading-card error-card">
        <p className="eyebrow">Bakery Operator Console</p>
        <h1>{title}</h1>
        <p className="subtle-copy">{message}</p>
        {onRetry ? (
          <button type="button" onClick={onRetry}>
            {retryLabel ?? "Try again"}
          </button>
        ) : null}
      </div>
    </div>
  );
}

function InlineError({ title, message }: { title: string; message: string }) {
  return (
    <div className="inline-alert danger">
      <strong>{title}</strong>
      <span>{message}</span>
    </div>
  );
}

function EmptyPanel({
  title,
  message,
  action,
}: {
  title: string;
  message: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="detail-empty">
      <h3>{title}</h3>
      <p>{message}</p>
      {action}
    </div>
  );
}

function MetricCard({
  label,
  value,
  tone = "default",
  detail,
}: {
  label: string;
  value: string;
  tone?: "default" | "healthy" | "warning" | "danger";
  detail?: string;
}) {
  return (
    <article className={`metric-card tone-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      {detail ? <p>{detail}</p> : null}
    </article>
  );
}

function QueueHealthCard({
  title,
  description,
  count,
  status,
}: {
  title: string;
  description: string;
  count: number;
  status: string;
}) {
  return (
    <article className="queue-health-card">
      <div className="queue-health-header">
        <h3>{title}</h3>
        <StatusBadge status={status} />
      </div>
      <strong>{formatCount(count)}</strong>
      <p>{description}</p>
    </article>
  );
}

function LoginScreen({
  settings,
  error,
  onLogin,
  pending,
}: {
  settings: SettingsResponse;
  error: string | null;
  onLogin: (provider: string, username: string, password: string) => Promise<void>;
  pending: boolean;
}) {
  const passwordProviders = settings.auth_providers.filter((provider) => provider.password_login);
  const [provider, setProvider] = useState(passwordProviders[0]?.name ?? "local");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    await onLogin(provider, username, password);
  }

  return (
    <div className="login-shell">
      <div className="login-card">
        <div className="login-copy">
          <p className="eyebrow">Bakery Operator Console</p>
          <h1>Operate the queue, not the guesswork.</h1>
          <p className="lead">
            See monitor health, route inventory, backlog pressure, and collection job results in
            one live console built for humans instead of UUID archaeology.
          </p>
          <div className="login-feature-grid">
            <div className="login-feature">
              <strong>Monitors with context</strong>
              <span>Human-friendly labels, health, routes, and latest collector results.</span>
            </div>
            <div className="login-feature">
              <strong>Collection jobs that explain themselves</strong>
              <span>Queue state, lease timing, failures, and structured results without reloads.</span>
            </div>
            <div className="login-feature">
              <strong>Backlog that links to evidence</strong>
              <span>Open work paired with ticket-context collection output and route analytics.</span>
            </div>
          </div>
        </div>

        <div className="login-panel">
          <h2>Sign in</h2>
          <p className="subtle-copy">Use the operator account you already use for Bakery administration.</p>
          {error ? <InlineError title="Sign-in failed" message={error} /> : null}
          {passwordProviders.length > 0 ? (
            <form className="login-form" onSubmit={submit}>
              <label>
                Provider
                <select value={provider} onChange={(event) => setProvider(event.target.value)}>
                  {passwordProviders.map((item) => (
                    <option key={item.name} value={item.name}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Username
                <input
                  autoComplete="username"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                />
              </label>
              <label>
                Password
                <input
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
              </label>
              <button type="submit" disabled={pending}>
                {pending ? "Signing in…" : "Sign in"}
              </button>
            </form>
          ) : null}
          <div className="provider-strip">
            {settings.auth_providers
              .filter((item) => item.browser_login)
              .map((item) => (
                <a
                  key={item.name}
                  className="provider-link"
                  href={buildAuthHref("/api/v1/auth/oidc/login", {
                    provider: item.name,
                    next: buildLoginReturnTarget(),
                  })}
                >
                  Continue with {item.label}
                </a>
              ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function OverviewPage({
  filters,
  slowPollMs,
  fastPollMs,
  collectors,
  onOpenJob,
}: {
  filters: ConsoleFilters;
  slowPollMs: number | false;
  fastPollMs: number | false;
  collectors: CollectionCollector[];
  onOpenJob: (jobId: string) => void;
}) {
  const navigate = useNavigate();
  const overviewQuery = useQuery({
    queryKey: ["overview", filters],
    queryFn: () => api.overview(mergeFilters(filters)),
    refetchInterval: slowPollMs,
  });
  const monitorsQuery = useQuery({
    queryKey: ["monitors", filters, "overview"],
    queryFn: () => api.monitors(mergeFilters(filters, { limit: 250 })),
    refetchInterval: slowPollMs,
  });
  const providersQuery = useQuery({
    queryKey: ["providers", filters, "overview"],
    queryFn: () => api.providers(mergeFilters(filters)),
    refetchInterval: slowPollMs,
  });
  const jobsQuery = useQuery({
    queryKey: ["jobs", filters, "overview"],
    queryFn: () => api.jobs({ monitorUuid: filters.monitorUuid, limit: 60 }),
    refetchInterval: fastPollMs,
  });

  const overview = overviewQuery.data;
  const monitors = monitorsQuery.data ?? [];
  const providers = providersQuery.data ?? [];
  const jobs = jobsQuery.data ?? [];
  const staleMonitorCount = monitors.filter((monitor) => isMonitorStale(monitor)).length;
  const activeJobs = jobs.filter((job) => job.status === "queued" || job.status === "leased").slice(0, 6);
  const recentFailures = jobs
    .filter((job) => job.status === "failed" || job.status === "timed_out")
    .slice(0, 5);

  const monitorHealthData = [
    { name: "Healthy", value: monitors.filter((monitor) => monitor.status === "healthy").length },
    { name: "Unreachable", value: monitors.filter((monitor) => monitor.status === "unreachable").length },
    {
      name: "Needs attention",
      value: monitors.filter((monitor) => monitor.status !== "healthy" && monitor.status !== "unreachable")
        .length,
    },
  ].filter((item) => item.value > 0);

  const collectorActivity = Array.from(
    jobs.reduce((accumulator, job) => {
      const key = collectorLabel(collectors, job.collector_type);
      accumulator.set(key, (accumulator.get(key) ?? 0) + 1);
      return accumulator;
    }, new Map<string, number>()),
  )
    .map(([collector, count]) => ({ collector, count }))
    .sort((left, right) => right.count - left.count);

  const providerLoad = providers.map((provider) => ({
    provider: provider.provider_type,
    routes: provider.route_count,
    openTickets: provider.open_ticket_count,
  }));

  if (overviewQuery.isLoading && monitorsQuery.isLoading) {
    return <LoadingScreen label="Loading the live operations picture" />;
  }

  if (overviewQuery.isError) {
    return (
      <ErrorScreen
        title="Overview data is unavailable"
        message={getErrorMessage(overviewQuery.error)}
        onRetry={() => void overviewQuery.refetch()}
      />
    );
  }

  return (
    <div className="page-stack">
      <section className="page-hero">
        <div>
          <p className="eyebrow">Live operations</p>
          <h1>Bakery at a glance</h1>
          <p className="subtle-copy">
            Start here when you need to answer three questions quickly: are monitors healthy, is the
            queue moving, and where should we look next?
          </p>
        </div>
        <div className="hero-actions">
          <button type="button" className="ghost-button" onClick={() => navigate("/jobs")}>
            Queue a collection job
          </button>
          <button type="button" className="ghost-button" onClick={() => navigate("/monitors")}>
            Open monitor drilldowns
          </button>
        </div>
      </section>

      <section className="metric-grid">
        <MetricCard
          label="Healthy monitors"
          value={`${formatCount(overview?.monitors_healthy ?? 0)} / ${formatCount(overview?.monitors_total ?? 0)}`}
          tone={overview && overview.monitors_unreachable > 0 ? "warning" : "healthy"}
          detail={`${formatCount(staleMonitorCount)} stale or unreachable`}
        />
        <MetricCard
          label="Open tickets"
          value={formatCount(overview?.open_tickets ?? 0)}
          tone={(overview?.open_tickets ?? 0) > 0 ? "warning" : "default"}
          detail="Active Bakery backlog across all providers"
        />
        <MetricCard
          label="Queued operations"
          value={formatCount(overview?.queued_operations ?? 0)}
          detail={`${formatCount(overview?.failed_operations ?? 0)} failed, ${formatCount(
            overview?.dead_letter_operations ?? 0,
          )} dead letter`}
          tone={(overview?.failed_operations ?? 0) > 0 ? "warning" : "default"}
        />
        <MetricCard
          label="Collection queue"
          value={formatCount((overview?.queued_collection_jobs ?? 0) + (overview?.leased_collection_jobs ?? 0))}
          detail={`${formatCount(overview?.leased_collection_jobs ?? 0)} active, ${formatCount(
            overview?.timed_out_collection_jobs ?? 0,
          )} timed out`}
          tone={(overview?.timed_out_collection_jobs ?? 0) > 0 ? "danger" : "default"}
        />
      </section>

      <section className="operator-layout two-up">
        <div className="card section-card">
          <div className="section-header">
            <div>
              <h2>Active collection jobs</h2>
              <p className="subtle-copy">Anything queued or leased shows up here immediately.</p>
            </div>
            <Link className="text-link" to="/jobs">
              Open jobs
            </Link>
          </div>
          {jobsQuery.isError ? (
            <InlineError title="Jobs feed unavailable" message={getErrorMessage(jobsQuery.error)} />
          ) : activeJobs.length === 0 ? (
            <EmptyPanel title="No active jobs" message="The collection queue is currently empty." />
          ) : (
            <div className="job-strip">
              {activeJobs.map((job) => (
                <button
                  key={job.job_id}
                  type="button"
                  className="job-chip"
                  onClick={() => onOpenJob(job.job_id)}
                >
                  <div className="job-chip-top">
                    <strong>{collectorLabel(collectors, job.collector_type)}</strong>
                    <StatusBadge status={job.status} />
                  </div>
                  <span>{job.monitor_id}</span>
                  <small>Queued {formatRelativeTime(job.created_at)}</small>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="card section-card">
          <div className="section-header">
            <div>
              <h2>Recent failures</h2>
              <p className="subtle-copy">Failed or timed-out collection jobs that need explanation or requeue.</p>
            </div>
            <Link className="text-link" to="/jobs">
              Investigate
            </Link>
          </div>
          {recentFailures.length === 0 ? (
            <EmptyPanel title="No recent job failures" message="The recent collection job feed looks clean." />
          ) : (
            <div className="event-list">
              {recentFailures.map((job) => (
                <button
                  key={job.job_id}
                  type="button"
                  className="event-row"
                  onClick={() => onOpenJob(job.job_id)}
                >
                  <div className="event-row-main">
                    <strong>{collectorLabel(collectors, job.collector_type)}</strong>
                    <StatusBadge status={job.status} />
                  </div>
                  <span>
                    {job.monitor_id} · {trimText(job.error, 120)}
                  </span>
                  <small>{formatRelativeTime(job.updated_at)}</small>
                </button>
              ))}
            </div>
          )}
        </div>
      </section>

      <section className="operator-layout two-up">
        <div className="card section-card chart-card">
          <div className="section-header">
            <div>
              <h2>Monitor health distribution</h2>
              <p className="subtle-copy">Stale monitors often explain why collection jobs never move.</p>
            </div>
            <Link className="text-link" to="/monitors">
              Review monitors
            </Link>
          </div>
          {monitorHealthData.length === 0 ? (
            <EmptyPanel title="No monitor data" message="Register a monitor to populate health analytics." />
          ) : (
            <div className="chart-shell">
              <ResponsiveContainer width="100%" height={280}>
                <PieChart>
                  <Pie data={monitorHealthData} dataKey="value" nameKey="name" outerRadius={98}>
                    {monitorHealthData.map((entry, index) => (
                      <Cell key={entry.name} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        <div className="card section-card chart-card">
          <div className="section-header">
            <div>
              <h2>Collector activity</h2>
              <p className="subtle-copy">Recent queue volume by collector type, regardless of final outcome.</p>
            </div>
            <Link className="text-link" to="/jobs">
              Open queue
            </Link>
          </div>
          {collectorActivity.length === 0 ? (
            <EmptyPanel title="No recent activity" message="Queue a collection job to start building trendlines." />
          ) : (
            <div className="chart-shell">
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={collectorActivity}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(17, 24, 39, 0.08)" />
                  <XAxis dataKey="collector" tickLine={false} axisLine={false} />
                  <YAxis allowDecimals={false} tickLine={false} axisLine={false} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#e6723d" radius={[10, 10, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </section>

      <section className="operator-layout two-up">
        <div className="card section-card chart-card">
          <div className="section-header">
            <div>
              <h2>Provider load</h2>
              <p className="subtle-copy">See where routing footprint and open-ticket pressure overlap.</p>
            </div>
            <Link className="text-link" to="/providers">
              Provider analytics
            </Link>
          </div>
          {providerLoad.length === 0 ? (
            <EmptyPanel title="No provider analytics" message="Route inventory will populate this view automatically." />
          ) : (
            <div className="chart-shell">
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={providerLoad}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(17, 24, 39, 0.08)" />
                  <XAxis dataKey="provider" tickLine={false} axisLine={false} />
                  <YAxis allowDecimals={false} tickLine={false} axisLine={false} />
                  <Tooltip />
                  <Bar dataKey="routes" fill="#2d7f6f" radius={[10, 10, 0, 0]} />
                  <Bar dataKey="openTickets" fill="#bf5f82" radius={[10, 10, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        <div className="card section-card">
          <div className="section-header">
            <div>
              <h2>Queue health cues</h2>
              <p className="subtle-copy">Shortcuts for the most common operator questions.</p>
            </div>
          </div>
          <div className="queue-health-grid">
            <QueueHealthCard
              title="Stale monitors"
              description="Check liveness and latest diagnostics before queueing more jobs."
              count={staleMonitorCount}
              status={staleMonitorCount > 0 ? "warning" : "healthy"}
            />
            <QueueHealthCard
              title="Unreachable monitors"
              description="These monitors will not claim jobs until PoundCake heartbeats resume."
              count={overview?.monitors_unreachable ?? 0}
              status={(overview?.monitors_unreachable ?? 0) > 0 ? "failed" : "healthy"}
            />
            <QueueHealthCard
              title="Timed-out jobs"
              description="Collection leases expired before PoundCake completed the work."
              count={overview?.timed_out_collection_jobs ?? 0}
              status={(overview?.timed_out_collection_jobs ?? 0) > 0 ? "timed_out" : "healthy"}
            />
            <QueueHealthCard
              title="Open backlog"
              description="Use ticket-context collection to explain these tickets faster."
              count={overview?.open_tickets ?? 0}
              status={(overview?.open_tickets ?? 0) > 0 ? "queued" : "healthy"}
            />
          </div>
        </div>
      </section>
    </div>
  );
}

function MonitorDetailPanel({
  detail,
  collectors,
  onOpenJob,
}: {
  detail: MonitorDetail;
  collectors: CollectionCollector[];
  onOpenJob: (jobId: string) => void;
}) {
  return (
    <div className="detail-stack">
      <section className="detail-card">
        <div className="section-header">
          <div>
            <h2>{detail.monitor.monitor_id}</h2>
            <p className="subtle-copy">{monitorDescriptor(detail.monitor)}</p>
          </div>
          <StatusBadge status={detail.monitor.status} />
        </div>
        <div className="mini-metric-grid">
          <MetricCard label="Routes" value={formatCount(detail.monitor.route_count)} />
          <MetricCard
            label="Outage routes"
            value={formatCount(detail.monitor.outage_route_count)}
            tone={detail.monitor.outage_route_count > 0 ? "warning" : "default"}
          />
          <MetricCard
            label="Last check-in"
            value={formatRelativeTime(detail.monitor.last_checkin_at)}
            tone={isMonitorStale(detail.monitor) ? "warning" : "healthy"}
          />
          <MetricCard
            label="Route sync"
            value={detail.monitor.route_sync_required ? "Required" : "Current"}
            tone={detail.monitor.route_sync_required ? "warning" : "healthy"}
          />
        </div>
      </section>

      <section className="detail-card">
        <div className="section-header">
          <div>
            <h3>Latest successful collector results</h3>
            <p className="subtle-copy">What the most recent successful collections already know about this monitor.</p>
          </div>
        </div>
        {detail.latest_successful_jobs.length === 0 ? (
          <EmptyPanel
            title="No successful collection results yet"
            message="Run diagnostics, cluster inventory, or ticket-context collection to populate this area."
          />
        ) : (
          <div className="result-stack">
            {detail.latest_successful_jobs.map((job) => (
              <article key={job.job_id} className="embedded-result">
                <div className="section-header">
                  <div>
                    <h4>{collectorLabel(collectors, job.collector_type)}</h4>
                    <p className="subtle-copy">
                      Completed {formatDateTime(job.completed_at)} · requested by {job.requested_by || "unknown"}
                    </p>
                  </div>
                  <button type="button" className="ghost-button" onClick={() => onOpenJob(job.job_id)}>
                    Open job
                  </button>
                </div>
                <CollectionJobResultPanel job={job} />
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="detail-card">
        <div className="section-header">
          <div>
            <h3>Recent jobs</h3>
            <p className="subtle-copy">Recent queue activity for this monitor, with quick links into the jobs workspace.</p>
          </div>
        </div>
        {detail.recent_jobs.length === 0 ? (
          <EmptyPanel title="No recent jobs" message="Queue a collection job to start building a local history." />
        ) : (
          <div className="event-list">
            {detail.recent_jobs.slice(0, 8).map((job) => (
              <button key={job.job_id} type="button" className="event-row" onClick={() => onOpenJob(job.job_id)}>
                <div className="event-row-main">
                  <strong>{collectorLabel(collectors, job.collector_type)}</strong>
                  <StatusBadge status={job.status} />
                </div>
                <span>{JOB_STATUS_COPY[job.status] ?? "Collection job update."}</span>
                <small>{formatRelativeTime(job.updated_at)}</small>
              </button>
            ))}
          </div>
        )}
      </section>

      <section className="detail-card">
        <div className="section-header">
          <div>
            <h3>Recent events</h3>
            <p className="subtle-copy">Registration, sync, and reachability events emitted by Bakery for this monitor.</p>
          </div>
        </div>
        {detail.recent_events.length === 0 ? (
          <EmptyPanel title="No monitor events" message="Bakery has not recorded recent state transitions for this monitor." />
        ) : (
          <div className="event-list">
            {detail.recent_events.map((event) => (
              <div key={`${event.monitor_uuid}-${event.created_at}-${event.event_type}`} className="event-row static">
                <div className="event-row-main">
                  <strong>{humanizeIdentifier(event.event_type)}</strong>
                  <span>{formatRelativeTime(event.created_at)}</span>
                </div>
                <small>{summarizeObject(event.payload)}</small>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="detail-card">
        <div className="section-header">
          <div>
            <h3>Recent routes</h3>
            <p className="subtle-copy">The execution routes this monitor is currently advertising.</p>
          </div>
        </div>
        {detail.recent_routes.length === 0 ? (
          <EmptyPanel title="No routes found" message="This monitor has not synced any route inventory yet." />
        ) : (
          <div className="mini-table-shell">
            <table className="mini-table">
              <thead>
                <tr>
                  <th>Label</th>
                  <th>Provider</th>
                  <th>Target</th>
                  <th>Flags</th>
                </tr>
              </thead>
              <tbody>
                {detail.recent_routes.slice(0, 10).map((route) => (
                  <tr key={`${route.monitor_uuid}-${route.route_id}`}>
                    <td>{route.label}</td>
                    <td>{route.provider_type}</td>
                    <td>{route.destination_target}</td>
                    <td>
                      {route.enabled ? "enabled" : "disabled"}
                      {route.outage_enabled ? " · outage" : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function MonitorsPage({
  filters,
  slowPollMs,
  fastPollMs,
  selectedMonitorUuid,
  setSelectedMonitorUuid,
  collectors,
  onOpenJob,
}: {
  filters: ConsoleFilters;
  slowPollMs: number | false;
  fastPollMs: number | false;
  selectedMonitorUuid?: string;
  setSelectedMonitorUuid: (monitorUuid?: string) => void;
  collectors: CollectionCollector[];
  onOpenJob: (jobId: string) => void;
}) {
  const query = useQuery({
    queryKey: ["monitors", filters],
    queryFn: () => api.monitors(mergeFilters(filters, { limit: 250 })),
    refetchInterval: slowPollMs,
  });
  const detailQuery = useQuery({
    queryKey: ["monitorDetail", selectedMonitorUuid],
    queryFn: () => api.monitorDetail(selectedMonitorUuid!),
    enabled: Boolean(selectedMonitorUuid),
    refetchInterval: fastPollMs,
  });
  const monitors = query.data ?? [];

  useEffect(() => {
    if (!selectedMonitorUuid && monitors.length > 0) {
      setSelectedMonitorUuid(monitors[0].monitor_uuid);
    }
  }, [monitors, selectedMonitorUuid, setSelectedMonitorUuid]);

  const columns = useMemo<ColumnDef<MonitorRow>[]>(
    () => [
      {
        header: "Monitor",
        accessorKey: "monitor_id",
        cell: ({ row }) => (
          <div className="table-primary">
            <strong>{row.original.monitor_id}</strong>
            <span>{monitorDescriptor(row.original)}</span>
          </div>
        ),
      },
      {
        header: "Status",
        accessorKey: "status",
        cell: ({ row }) => <StatusBadge status={row.original.status} />,
      },
      {
        header: "Routes",
        id: "routes",
        cell: ({ row }) => (
          <div className="table-primary">
            <strong>{formatCount(row.original.route_count)}</strong>
            <span>{formatCount(row.original.outage_route_count)} outage routes</span>
          </div>
        ),
      },
      {
        header: "Route sync",
        id: "sync",
        cell: ({ row }) =>
          row.original.route_sync_required ? (
            <StatusBadge status="route_sync_required" />
          ) : (
            <span className="plain-badge">current</span>
          ),
      },
      {
        header: "Last check-in",
        accessorKey: "last_checkin_at",
        cell: ({ row }) => (
          <div className="table-primary">
            <strong>{formatRelativeTime(row.original.last_checkin_at)}</strong>
            <span>{formatDateTime(row.original.last_checkin_at)}</span>
          </div>
        ),
      },
    ],
    [],
  );

  if (query.isLoading) {
    return <LoadingScreen label="Loading monitor inventory" />;
  }

  if (query.isError) {
    return (
      <ErrorScreen
        title="Monitor inventory is unavailable"
        message={getErrorMessage(query.error)}
        onRetry={() => void query.refetch()}
      />
    );
  }

  return (
    <div className="page-stack">
      <section className="page-hero">
        <div>
          <p className="eyebrow">Monitor drilldowns</p>
          <h1>Monitor health with useful detail</h1>
          <p className="subtle-copy">
            Pick any monitor and Bakery will show the routes, recent events, queued work, and latest
            successful collection results in one split view.
          </p>
        </div>
      </section>

      <div className="workspace-grid">
        <section className="card section-card">
          <div className="section-header">
            <div>
              <h2>Monitors</h2>
              <p className="subtle-copy">{formatCount(monitors.length)} matching monitors</p>
            </div>
          </div>
          <OperatorTable
            data={monitors}
            columns={columns}
            getRowId={(row) => row.monitor_uuid}
            selectedRowId={selectedMonitorUuid}
            onSelectRow={(row) => setSelectedMonitorUuid(row.monitor_uuid)}
            emptyState="No monitors matched the current filters."
          />
        </section>

        <aside className="detail-rail">
          {detailQuery.isLoading ? (
            <LoadingScreen label="Loading monitor detail" />
          ) : detailQuery.isError ? (
            <InlineError title="Monitor detail unavailable" message={getErrorMessage(detailQuery.error)} />
          ) : detailQuery.data ? (
            <MonitorDetailPanel
              detail={detailQuery.data}
              collectors={collectors}
              onOpenJob={onOpenJob}
            />
          ) : (
            <EmptyPanel
              title="Select a monitor"
              message="The detail rail will show recent events, routes, and successful collector results."
            />
          )}
        </aside>
      </div>
    </div>
  );
}

function MonitorEventsPage({
  filters,
  slowPollMs,
  monitorOptions,
}: {
  filters: ConsoleFilters;
  slowPollMs: number | false;
  monitorOptions: FilterOptions | undefined;
}) {
  const query = useQuery({
    queryKey: ["monitorEvents", filters],
    queryFn: () => api.monitorEvents(mergeFilters(filters, { limit: 250 })),
    refetchInterval: slowPollMs,
  });
  const lookup = useMemo(() => monitorLookup(monitorOptions), [monitorOptions]);
  const columns = useMemo<ColumnDef<MonitorEventRow>[]>(
    () => [
      {
        header: "When",
        accessorKey: "created_at",
        cell: ({ row }) => (
          <div className="table-primary">
            <strong>{formatRelativeTime(row.original.created_at)}</strong>
            <span>{formatDateTime(row.original.created_at)}</span>
          </div>
        ),
      },
      {
        header: "Monitor",
        accessorKey: "monitor_uuid",
        cell: ({ row }) => {
          const monitor = lookup.get(row.original.monitor_uuid);
          return (
            <div className="table-primary">
              <strong>{monitor?.monitor_id ?? row.original.monitor_uuid}</strong>
              <span>{monitor ? monitorDescriptor(monitor) : row.original.monitor_uuid}</span>
            </div>
          );
        },
      },
      {
        header: "Event",
        accessorKey: "event_type",
        cell: ({ row }) => humanizeIdentifier(row.original.event_type),
      },
      {
        header: "Payload",
        accessorKey: "payload",
        cell: ({ row }) => summarizeObject(row.original.payload),
      },
    ],
    [lookup],
  );

  if (query.isLoading) {
    return <LoadingScreen label="Loading monitor events" />;
  }

  if (query.isError) {
    return (
      <ErrorScreen
        title="Monitor events are unavailable"
        message={getErrorMessage(query.error)}
        onRetry={() => void query.refetch()}
      />
    );
  }

  return (
    <div className="page-stack">
      <section className="page-hero">
        <div>
          <p className="eyebrow">Event stream</p>
          <h1>Monitor registration and liveness events</h1>
          <p className="subtle-copy">
            This is the fast way to answer “did PoundCake actually sync?” before you blame the queue.
          </p>
        </div>
      </section>
      <section className="card section-card">
        <OperatorTable
          data={query.data ?? []}
          columns={columns}
          getRowId={(row) => `${row.monitor_uuid}-${row.created_at}-${row.event_type}`}
          emptyState="No monitor events matched the current filters."
        />
      </section>
    </div>
  );
}

function RoutesPage({
  filters,
  slowPollMs,
}: {
  filters: ConsoleFilters;
  slowPollMs: number | false;
}) {
  const query = useQuery({
    queryKey: ["routes", filters],
    queryFn: () => api.routes(mergeFilters(filters, { limit: 500 })),
    refetchInterval: slowPollMs,
  });
  const columns = useMemo<ColumnDef<RouteRow>[]>(
    () => [
      {
        header: "Route",
        accessorKey: "label",
        cell: ({ row }) => (
          <div className="table-primary">
            <strong>{row.original.label}</strong>
            <span>
              {row.original.scope} · {row.original.owner_key} · {row.original.route_id}
            </span>
          </div>
        ),
      },
      {
        header: "Monitor",
        accessorKey: "monitor_id",
        cell: ({ row }) => (
          <div className="table-primary">
            <strong>{row.original.monitor_id}</strong>
            <span>{row.original.environment_label || "No environment label"}</span>
          </div>
        ),
      },
      {
        header: "Provider",
        accessorKey: "provider_type",
      },
      {
        header: "Execution",
        accessorKey: "execution_target",
      },
      {
        header: "Destination",
        accessorKey: "destination_target",
      },
      {
        header: "Flags",
        id: "flags",
        cell: ({ row }) => (
          <div className="table-primary">
            <strong>{row.original.enabled ? "enabled" : "disabled"}</strong>
            <span>{row.original.outage_enabled ? "Outage routing on" : "Outage routing off"}</span>
          </div>
        ),
      },
    ],
    [],
  );

  if (query.isLoading) {
    return <LoadingScreen label="Loading route inventory" />;
  }

  if (query.isError) {
    return (
      <ErrorScreen
        title="Route inventory is unavailable"
        message={getErrorMessage(query.error)}
        onRetry={() => void query.refetch()}
      />
    );
  }

  return (
    <div className="page-stack">
      <section className="page-hero">
        <div>
          <p className="eyebrow">Route catalog</p>
          <h1>Execution routes advertised by PoundCake</h1>
          <p className="subtle-copy">
            Useful when a monitor looks healthy but work still heads somewhere unexpected.
          </p>
        </div>
      </section>
      <section className="card section-card">
        <OperatorTable
          data={query.data ?? []}
          columns={columns}
          getRowId={(row) => `${row.monitor_uuid}-${row.route_id}-${row.position}`}
          emptyState="No routes matched the current filters."
        />
      </section>
    </div>
  );
}

function ProvidersPage({
  filters,
  slowPollMs,
}: {
  filters: ConsoleFilters;
  slowPollMs: number | false;
}) {
  const query = useQuery({
    queryKey: ["providers", filters],
    queryFn: () => api.providers(mergeFilters(filters)),
    refetchInterval: slowPollMs,
  });
  const columns = useMemo<ColumnDef<ProviderAnalyticsRow>[]>(
    () => [
      { header: "Provider", accessorKey: "provider_type" },
      { header: "Routes", accessorKey: "route_count" },
      { header: "Tickets", accessorKey: "ticket_count" },
      { header: "Open", accessorKey: "open_ticket_count" },
      { header: "Failed ops", accessorKey: "failed_operation_count" },
      { header: "Dead letters", accessorKey: "dead_letter_count" },
    ],
    [],
  );

  const chartData = (query.data ?? []).map((row) => ({
    provider: row.provider_type,
    routes: row.route_count,
    failed: row.failed_operation_count,
    deadLetter: row.dead_letter_count,
  }));

  if (query.isLoading) {
    return <LoadingScreen label="Loading provider analytics" />;
  }

  if (query.isError) {
    return (
      <ErrorScreen
        title="Provider analytics are unavailable"
        message={getErrorMessage(query.error)}
        onRetry={() => void query.refetch()}
      />
    );
  }

  return (
    <div className="page-stack">
      <section className="page-hero">
        <div>
          <p className="eyebrow">Provider analytics</p>
          <h1>Where Bakery is routing ticket work</h1>
          <p className="subtle-copy">
            Compare footprint, open tickets, and failure concentration across providers without leaving the console.
          </p>
        </div>
      </section>

      <section className="operator-layout two-up">
        <div className="card section-card chart-card">
          <div className="section-header">
            <div>
              <h2>Provider pressure</h2>
              <p className="subtle-copy">Route volume beside failures and dead letters.</p>
            </div>
          </div>
          {chartData.length === 0 ? (
            <EmptyPanel title="No provider activity" message="Route inventory will populate this page automatically." />
          ) : (
            <div className="chart-shell">
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(17, 24, 39, 0.08)" />
                  <XAxis dataKey="provider" tickLine={false} axisLine={false} />
                  <YAxis allowDecimals={false} tickLine={false} axisLine={false} />
                  <Tooltip />
                  <Bar dataKey="routes" fill="#2d7f6f" radius={[10, 10, 0, 0]} />
                  <Bar dataKey="failed" fill="#bf5f82" radius={[10, 10, 0, 0]} />
                  <Bar dataKey="deadLetter" fill="#d6a441" radius={[10, 10, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        <div className="card section-card">
          <div className="section-header">
            <div>
              <h2>Provider table</h2>
              <p className="subtle-copy">Dense counts for audits, triage, and incident reviews.</p>
            </div>
          </div>
          <OperatorTable
            data={query.data ?? []}
            columns={columns}
            getRowId={(row) => row.provider_type}
            emptyState="No provider analytics matched the current filters."
          />
        </div>
      </section>
    </div>
  );
}

function OperationsPage({
  filters,
  slowPollMs,
}: {
  filters: ConsoleFilters;
  slowPollMs: number | false;
}) {
  const query = useQuery({
    queryKey: ["operations", filters],
    queryFn: () => api.operations(mergeFilters(filters)),
    refetchInterval: slowPollMs,
  });

  const chartData = Array.from(
    (query.data ?? []).reduce((accumulator, row) => {
      const existing = accumulator.get(row.action) ?? {
        action: row.action,
        queued: 0,
        failed: 0,
        succeeded: 0,
        dead_letter: 0,
        running: 0,
      };
      if (row.status in existing) {
        existing[row.status as keyof typeof existing] = row.count as never;
      }
      accumulator.set(row.action, existing);
      return accumulator;
    }, new Map<string, { action: string; queued: number; failed: number; succeeded: number; dead_letter: number; running: number }>()),
  ).map(([, value]) => value);

  const columns = useMemo<ColumnDef<OperationAnalyticsRow>[]>(
    () => [
      { header: "Provider", accessorKey: "provider_type" },
      { header: "Action", accessorKey: "action" },
      {
        header: "Status",
        accessorKey: "status",
        cell: ({ row }) => <StatusBadge status={row.original.status} />,
      },
      { header: "Count", accessorKey: "count" },
    ],
    [],
  );

  if (query.isLoading) {
    return <LoadingScreen label="Loading operation analytics" />;
  }

  if (query.isError) {
    return (
      <ErrorScreen
        title="Operation analytics are unavailable"
        message={getErrorMessage(query.error)}
        onRetry={() => void query.refetch()}
      />
    );
  }

  return (
    <div className="page-stack">
      <section className="page-hero">
        <div>
          <p className="eyebrow">Queue analytics</p>
          <h1>Bakery operation pressure and outcomes</h1>
          <p className="subtle-copy">
            Use this when you need to tell whether the problem is collector execution, route sync, or downstream provider work.
          </p>
        </div>
      </section>

      <section className="operator-layout two-up">
        <div className="card section-card chart-card">
          <div className="section-header">
            <div>
              <h2>Operation status by action</h2>
              <p className="subtle-copy">Failures and dead letters stand out faster in a stacked view.</p>
            </div>
          </div>
          {chartData.length === 0 ? (
            <EmptyPanel title="No operation analytics" message="Operation records will appear as Bakery processes work." />
          ) : (
            <div className="chart-shell">
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(17, 24, 39, 0.08)" />
                  <XAxis dataKey="action" tickLine={false} axisLine={false} />
                  <YAxis allowDecimals={false} tickLine={false} axisLine={false} />
                  <Tooltip />
                  <Bar dataKey="queued" stackId="a" fill="#4d6fc5" />
                  <Bar dataKey="running" stackId="a" fill="#2d7f6f" />
                  <Bar dataKey="succeeded" stackId="a" fill="#7bb661" />
                  <Bar dataKey="failed" stackId="a" fill="#bf5f82" />
                  <Bar dataKey="dead_letter" stackId="a" fill="#d6a441" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        <div className="card section-card">
          <div className="section-header">
            <div>
              <h2>Operation table</h2>
              <p className="subtle-copy">Complete action/status counts with filter support.</p>
            </div>
          </div>
          <OperatorTable
            data={query.data ?? []}
            columns={columns}
            getRowId={(row) => `${row.provider_type}-${row.action}-${row.status}`}
            emptyState="No operations matched the current filters."
          />
        </div>
      </section>
    </div>
  );
}

function BacklogPage({
  filters,
  slowPollMs,
  fastPollMs,
  selectedTicketId,
  setSelectedTicketId,
  canManageBacklog,
}: {
  filters: ConsoleFilters;
  slowPollMs: number | false;
  fastPollMs: number | false;
  selectedTicketId?: string;
  setSelectedTicketId: (ticketId?: string) => void;
  canManageBacklog: boolean;
}) {
  const queryClient = useQueryClient();
  const [closeNotes, setCloseNotes] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const backlogQuery = useQuery({
    queryKey: ["backlog", filters],
    queryFn: () => api.backlog(mergeFilters(filters, { limit: 250 })),
    refetchInterval: slowPollMs,
  });
  const selectedTicket = useMemo(
    () => (backlogQuery.data ?? []).find((ticket) => ticket.ticket_id === selectedTicketId),
    [backlogQuery.data, selectedTicketId],
  );
  const ticketContextQuery = useQuery({
    queryKey: ["jobs", "ticket-context", selectedTicket?.monitor_uuid, selectedTicket?.ticket_id],
    queryFn: () =>
      api.jobs({
        monitorUuid: selectedTicket?.monitor_uuid ?? undefined,
        collectorType: "ticket_context",
        limit: 50,
      }),
    enabled: Boolean(selectedTicket?.monitor_uuid),
    refetchInterval: fastPollMs,
  });
  const ticketDetailQuery = useQuery({
    queryKey: ["operator-ticket", selectedTicketId],
    queryFn: () => api.operatorTicket(selectedTicketId as string),
    enabled: Boolean(selectedTicketId) && canManageBacklog,
    refetchInterval: fastPollMs,
  });
  const ticketOperationsQuery = useQuery({
    queryKey: ["operator-ticket-operations", selectedTicketId],
    queryFn: () => api.operatorTicketOperations(selectedTicketId as string, 25),
    enabled: Boolean(selectedTicketId) && canManageBacklog,
    refetchInterval: fastPollMs,
  });
  const closeTicketMutation = useMutation({
    mutationFn: (ticket: BacklogRow) =>
      api.operatorCloseTicket(ticket.ticket_id, {
        resolution_notes: closeNotes.trim() || undefined,
        state: "closed",
        source: "bakery-ui",
        context: {
          actor: "operator_console",
          backlog_reason: ticket.backlog_reason,
        },
      }),
    onSuccess: async () => {
      setActionError(null);
      setCloseNotes("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["backlog"] }),
        queryClient.invalidateQueries({ queryKey: ["operator-ticket"] }),
        queryClient.invalidateQueries({ queryKey: ["operator-ticket-operations"] }),
        queryClient.invalidateQueries({ queryKey: ["monitor-detail"] }),
      ]);
    },
    onError: (error) => {
      setActionError(getErrorMessage(error));
    },
  });
  const resyncTicketMutation = useMutation({
    mutationFn: (ticketId: string) => api.operatorFindTicket(ticketId),
    onSuccess: async () => {
      setActionError(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["backlog"] }),
        queryClient.invalidateQueries({ queryKey: ["operator-ticket"] }),
        queryClient.invalidateQueries({ queryKey: ["operator-ticket-operations"] }),
      ]);
    },
    onError: (error) => {
      setActionError(getErrorMessage(error));
    },
  });

  useEffect(() => {
    if (!backlogQuery.data || backlogQuery.data.length === 0) {
      return;
    }
    if (!selectedTicketId) {
      setSelectedTicketId(backlogQuery.data[0].ticket_id);
      return;
    }
    if (!backlogQuery.data.some((ticket) => ticket.ticket_id === selectedTicketId)) {
      setSelectedTicketId(backlogQuery.data[0].ticket_id);
    }
  }, [backlogQuery.data, selectedTicketId, setSelectedTicketId]);

  useEffect(() => {
    setCloseNotes("");
    setActionError(null);
  }, [selectedTicketId]);

  const relatedJobs = selectedTicket ? findRelatedTicketContextJobs(ticketContextQuery.data ?? [], selectedTicket) : [];
  const actionState = selectedTicket ? backlogActionState(selectedTicket) : null;
  const latestOperations = ticketOperationsQuery.data?.operations ?? [];

  const columns = useMemo<ColumnDef<BacklogRow>[]>(
    () => [
      {
        header: "Ticket",
        accessorKey: "ticket_id",
        cell: ({ row }) => (
          <div className="table-primary">
            <strong>{row.original.ticket_id}</strong>
            <span>{row.original.provider_ticket_id || "No provider ticket ID"}</span>
          </div>
        ),
      },
      { header: "Provider", accessorKey: "provider_type" },
      {
        header: "Monitor",
        accessorKey: "monitor_id",
        cell: ({ row }) => row.original.monitor_id || row.original.monitor_uuid || "Unbound",
      },
      {
        header: "State",
        accessorKey: "state",
        cell: ({ row }) => <StatusBadge status={row.original.state} />,
      },
      {
        header: "Reason",
        accessorKey: "backlog_reason",
        cell: ({ row }) => <span className="plain-badge">{backlogReasonLabel(row.original.backlog_reason)}</span>,
      },
      {
        header: "Latest error",
        accessorKey: "latest_error",
        cell: ({ row }) => trimText(row.original.latest_error),
      },
      {
        header: "Updated",
        accessorKey: "updated_at",
        cell: ({ row }) => formatRelativeTime(row.original.updated_at),
      },
    ],
    [],
  );

  if (backlogQuery.isLoading) {
    return <LoadingScreen label="Loading the Bakery backlog" />;
  }

  if (backlogQuery.isError) {
    return (
      <ErrorScreen
        title="Backlog data is unavailable"
        message={getErrorMessage(backlogQuery.error)}
        onRetry={() => void backlogQuery.refetch()}
      />
    );
  }

  return (
    <div className="page-stack">
      <section className="page-hero">
        <div>
          <p className="eyebrow">Backlog drilldowns</p>
          <h1>Open work with attached evidence</h1>
          <p className="subtle-copy">
            Tickets are more useful when the latest ticket-context collection and monitor state are right beside them.
          </p>
        </div>
      </section>

      <div className="workspace-grid">
        <section className="card section-card">
          <div className="section-header">
            <div>
              <h2>Backlog</h2>
              <p className="subtle-copy">{formatCount((backlogQuery.data ?? []).length)} matching tickets</p>
            </div>
          </div>
          <OperatorTable
            data={backlogQuery.data ?? []}
            columns={columns}
            getRowId={(row) => row.ticket_id}
            selectedRowId={selectedTicketId}
            onSelectRow={(row) => setSelectedTicketId(row.ticket_id)}
            emptyState="No backlog entries matched the current filters."
          />
        </section>

        <aside className="detail-rail">
          {selectedTicket ? (
            <div className="detail-stack">
              <section className="detail-card">
                <div className="section-header">
                  <div>
                    <h2>{selectedTicket.ticket_id}</h2>
                    <p className="subtle-copy">
                      {selectedTicket.provider_type} · {selectedTicket.monitor_id || selectedTicket.monitor_uuid || "No monitor binding"}
                    </p>
                  </div>
                  <StatusBadge status={selectedTicket.state} />
                </div>
                <div className="mini-metric-grid">
                  <MetricCard label="Updated" value={formatRelativeTime(selectedTicket.updated_at)} />
                  <MetricCard label="Created" value={formatDateTime(selectedTicket.created_at)} />
                  <MetricCard
                    label="Provider ticket"
                    value={selectedTicket.provider_ticket_id || "None"}
                    tone={selectedTicket.provider_ticket_id ? "default" : "warning"}
                  />
                  <MetricCard
                    label="Backlog reason"
                    value={backlogReasonLabel(selectedTicket.backlog_reason)}
                    tone={selectedTicket.is_dry_run ? "warning" : selectedTicket.backlog_reason === "error" ? "danger" : "default"}
                  />
                </div>
                <div className="callout-stack">
                  <div className={`inline-alert ${selectedTicket.is_dry_run ? "warning" : selectedTicket.backlog_reason === "error" ? "danger" : "info"}`}>
                    <strong>{selectedTicket.is_dry_run ? "Dry-run ticket" : "Backlog guidance"}</strong>
                    <span>{backlogReasonMessage(selectedTicket)}</span>
                  </div>
                  {selectedTicket.latest_error ? (
                    <InlineError title="Latest ticket error" message={selectedTicket.latest_error} />
                  ) : (
                    <div className="inline-alert info">
                      <strong>No current ticket error</strong>
                      <span>Use related ticket-context collection to inspect surrounding PoundCake workflow data.</span>
                    </div>
                  )}
                </div>
              </section>

              <section className="detail-card">
                <div className="section-header">
                  <div>
                    <h3>Ticket management</h3>
                    <p className="subtle-copy">Operator actions are intentionally narrow in this first pass: dry-run and error tickets only.</p>
                  </div>
                </div>
                {!canManageBacklog ? (
                  <EmptyPanel
                    title="No management permission"
                    message="Your operator role can inspect backlog detail here, but only users with manage_backlog permission can resync or close tickets."
                  />
                ) : (
                  <div className="callout-stack">
                    {ticketDetailQuery.isError ? (
                      <InlineError title="Ticket detail unavailable" message={getErrorMessage(ticketDetailQuery.error)} />
                    ) : ticketDetailQuery.data ? (
                      <div className="inline-alert info">
                        <strong>Current Bakery ticket state</strong>
                        <span>
                          {ticketDetailQuery.data.state} via {ticketDetailQuery.data.data_source}
                          {ticketDetailQuery.data.last_sync_at ? ` · last sync ${formatRelativeTime(ticketDetailQuery.data.last_sync_at)}` : ""}
                        </span>
                      </div>
                    ) : null}
                    {actionError ? <InlineError title="Ticket action failed" message={actionError} /> : null}
                    {actionState?.canClose ? (
                      <label>
                        Resolution notes
                        <textarea
                          rows={4}
                          value={closeNotes}
                          onChange={(event) => setCloseNotes(event.target.value)}
                          placeholder={
                            selectedTicket.is_dry_run
                              ? "Document why this synthetic dry-run ticket is safe to retire."
                              : "Add closure context for operators reviewing this Bakery backlog item."
                          }
                        />
                      </label>
                    ) : null}
                    <div className="detail-actions">
                      <button
                        type="button"
                        className="ghost-button"
                        disabled={!actionState?.canResync || resyncTicketMutation.isPending}
                        onClick={() => {
                          setActionError(null);
                          void resyncTicketMutation.mutateAsync(selectedTicket.ticket_id);
                        }}
                      >
                        {resyncTicketMutation.isPending ? "Resyncing…" : "Resync provider state"}
                      </button>
                      <button
                        type="button"
                        disabled={!actionState?.canClose || closeTicketMutation.isPending}
                        onClick={() => {
                          setActionError(null);
                          void closeTicketMutation.mutateAsync(selectedTicket);
                        }}
                      >
                        {closeTicketMutation.isPending
                          ? "Closing…"
                          : selectedTicket.is_dry_run
                            ? "Close dry-run ticket"
                            : "Close ticket"}
                      </button>
                    </div>
                    {actionState?.isReadOnly ? (
                      <div className="inline-alert info">
                        <strong>Read-only backlog item</strong>
                        <span>Healthy provider-backed tickets remain read-only in this first management pass.</span>
                      </div>
                    ) : null}
                  </div>
                )}
              </section>

              <section className="detail-card">
                <div className="section-header">
                  <div>
                    <h3>Recent ticket operations</h3>
                    <p className="subtle-copy">The newest Bakery-side ticket actions and sync attempts for this backlog item.</p>
                  </div>
                </div>
                {!canManageBacklog ? (
                  <EmptyPanel
                    title="Operations hidden"
                    message="Ticket operation history is available to operators with manage_backlog permission."
                  />
                ) : ticketOperationsQuery.isLoading ? (
                  <LoadingScreen label="Loading ticket operations" />
                ) : ticketOperationsQuery.isError ? (
                  <InlineError title="Ticket operations unavailable" message={getErrorMessage(ticketOperationsQuery.error)} />
                ) : latestOperations.length === 0 ? (
                  <EmptyPanel title="No ticket operations yet" message="Bakery has not recorded any action history for this backlog item." />
                ) : (
                  <div className="event-list">
                    {latestOperations.map((operation) => (
                      <article className="event-row static" key={operation.operation_id}>
                        <div className="event-row-main">
                          <div className="table-primary">
                            <strong>{humanizeIdentifier(operation.action)}</strong>
                            <span>{formatDateTime(operation.created_at)}</span>
                          </div>
                          <StatusBadge status={operation.status} />
                        </div>
                        <small>
                          Attempts {operation.attempt_count}/{operation.max_attempts}
                          {operation.completed_at ? ` · completed ${formatRelativeTime(operation.completed_at)}` : ""}
                        </small>
                        {operation.last_error ? <span>{operation.last_error}</span> : null}
                      </article>
                    ))}
                  </div>
                )}
              </section>

              <section className="detail-card">
                <div className="section-header">
                  <div>
                    <h3>Related ticket-context results</h3>
                    <p className="subtle-copy">
                      Matching successful collection results for this backlog item, if any exist.
                    </p>
                  </div>
                </div>
                {ticketContextQuery.isLoading ? (
                  <LoadingScreen label="Loading related collection results" />
                ) : relatedJobs.length === 0 ? (
                  <EmptyPanel
                    title="No related ticket-context results"
                    message="Queue a ticket-context job for this monitor and include the Bakery ticket ID or provider order ID."
                  />
                ) : (
                  <div className="result-stack">
                    {relatedJobs.map((job) => (
                      <article key={job.job_id} className="embedded-result">
                        <div className="section-header">
                          <div>
                            <h4>{formatDateTime(job.completed_at)}</h4>
                            <p className="subtle-copy">{job.reason || "Queued without an explicit reason."}</p>
                          </div>
                          <StatusBadge status={job.status} />
                        </div>
                        <CollectionJobResultPanel job={job} />
                      </article>
                    ))}
                  </div>
                )}
              </section>
            </div>
          ) : (
            <EmptyPanel
              title="Select a backlog item"
              message="The detail rail will show current ticket state and any related ticket-context collection results."
            />
          )}
        </aside>
      </div>
    </div>
  );
}

function CollectionJobDetail({
  job,
  monitor,
  collectors,
  onRequeue,
  requeuePending,
}: {
  job: CollectionJob;
  monitor: MonitorFilterOption | undefined;
  collectors: CollectionCollector[];
  onRequeue: () => void;
  requeuePending: boolean;
}) {
  const leaseMs = job.lease_expires_at ? new Date(job.lease_expires_at).getTime() - Date.now() : null;
  const queueAge = formatDurationFrom(job.created_at, job.started_at || undefined);
  const runDuration = job.started_at
    ? formatDurationFrom(job.started_at, job.completed_at || undefined)
    : "Not started";
  const isTerminal = job.status === "succeeded" || job.status === "failed" || job.status === "timed_out";

  return (
    <div className="detail-stack">
      <section className="detail-card">
        <div className="section-header">
          <div>
            <h2>{collectorLabel(collectors, job.collector_type)}</h2>
            <p className="subtle-copy">
              {job.monitor_id} · queued {formatRelativeTime(job.created_at)}
            </p>
          </div>
          <StatusBadge status={job.status} />
        </div>

        <div className="mini-metric-grid">
          <MetricCard label="Queue age" value={queueAge} />
          <MetricCard label="Run duration" value={runDuration} />
          <MetricCard
            label="Lease countdown"
            value={
              job.status === "leased" && leaseMs !== null
                ? formatDurationMs(Math.max(leaseMs, 0))
                : job.lease_expires_at
                  ? formatDateTime(job.lease_expires_at)
                  : "Not leased"
            }
            tone={job.status === "leased" && leaseMs !== null && leaseMs < 60_000 ? "warning" : "default"}
          />
          <MetricCard
            label="Monitor freshness"
            value={monitor ? formatRelativeTime(monitor.last_checkin_at) : "Unknown"}
            tone={monitor && isMonitorStale(monitor) ? "warning" : "healthy"}
            detail={monitor ? monitorDescriptor(monitor) : "No monitor metadata available"}
          />
        </div>

        {job.reason ? (
          <div className="inline-alert info">
            <strong>Reason</strong>
            <span>{job.reason}</span>
          </div>
        ) : null}

        <div className="inline-alert info">
          <strong>What this status means</strong>
          <span>{JOB_STATUS_COPY[job.status] ?? "The collector reported a status update."}</span>
        </div>

        {monitor && isMonitorStale(monitor) ? (
          <div className="inline-alert warning">
            <strong>This monitor looks stale</strong>
            <span>
              The last Bakery heartbeat is {formatRelativeTime(monitor.last_checkin_at)}. Jobs may queue or time out until PoundCake heartbeats recover.
            </span>
          </div>
        ) : null}

        {job.error ? <InlineError title="Collector failure" message={job.error} /> : null}

        <div className="detail-actions">
          <button type="button" className="ghost-button" onClick={onRequeue} disabled={requeuePending}>
            {requeuePending ? "Requeueing…" : isTerminal ? "Requeue job" : "Duplicate job"}
          </button>
        </div>
      </section>

      <section className="detail-card">
        <div className="section-header">
          <div>
            <h3>Parameters and result</h3>
            <p className="subtle-copy">Structured output stays in Bakery and shows up here when the job completes.</p>
          </div>
        </div>
        <CollectionJobResultPanel job={job} />
      </section>
    </div>
  );
}

function JobsPage({
  filters,
  slowPollMs,
  fastPollMs,
  monitorOptions,
  collectors,
  selectedJobId,
  setSelectedJobId,
  setGlobalMonitorUuid,
}: {
  filters: ConsoleFilters;
  slowPollMs: number | false;
  fastPollMs: number | false;
  monitorOptions: FilterOptions | undefined;
  collectors: CollectionCollector[];
  selectedJobId?: string;
  setSelectedJobId: (jobId?: string) => void;
  setGlobalMonitorUuid: (monitorUuid?: string) => void;
}) {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const monitorMap = useMemo(() => monitorLookup(monitorOptions), [monitorOptions]);
  const initialCollector = collectors[0]?.collector_type ?? "monitor_diagnostics";
  const [monitorUuid, setMonitorUuid] = useState(filters.monitorUuid ?? "");
  const [collectorType, setCollectorType] = useState(searchParams.get("collectorView") || initialCollector);
  const [reason, setReason] = useState("");
  const [advancedJson, setAdvancedJson] = useState("");
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const selectedCollector = getCollectorByType(collectors, collectorType) ?? collectors[0];

  useEffect(() => {
    if (filters.monitorUuid && !monitorUuid) {
      setMonitorUuid(filters.monitorUuid);
    }
  }, [filters.monitorUuid, monitorUuid]);

  useEffect(() => {
    if (!selectedCollector) {
      return;
    }
    const defaults = Object.fromEntries(
      selectedCollector.parameters.map((field) => [
        field.name,
        field.default_value === null || field.default_value === undefined ? "" : String(field.default_value),
      ]),
    );
    setFieldValues(defaults);
    setAdvancedJson(
      Object.keys(selectedCollector.example_parameters).length > 0
        ? JSON.stringify(selectedCollector.example_parameters, null, 2)
        : "",
    );
  }, [selectedCollector?.collector_type]);

  useEffect(() => {
    const current = searchParams.get("collectorView");
    if (collectorType && current !== collectorType) {
      const next = new URLSearchParams(searchParams);
      next.set("collectorView", collectorType);
      setSearchParams(next, { replace: true });
    }
  }, [collectorType, searchParams, setSearchParams]);

  const jobStatus = optionalParam(searchParams.get("jobStatus"));
  const jobCollectorFilter = optionalParam(searchParams.get("collectorFilter"));
  const jobsQuery = useQuery({
    queryKey: ["jobs", filters, jobStatus, jobCollectorFilter],
    queryFn: () =>
      api.jobs({
        monitorUuid: filters.monitorUuid,
        status: jobStatus,
        collectorType: jobCollectorFilter,
        limit: 200,
      }),
    refetchInterval: fastPollMs,
  });
  const selectedJobQuery = useQuery({
    queryKey: ["job", selectedJobId],
    queryFn: () => api.job(selectedJobId!),
    enabled: Boolean(selectedJobId),
    refetchInterval: fastPollMs,
  });

  useEffect(() => {
    if (!selectedJobId && jobsQuery.data && jobsQuery.data.length > 0) {
      setSelectedJobId(jobsQuery.data[0].job_id);
    }
  }, [jobsQuery.data, selectedJobId, setSelectedJobId]);

  const queueMutation = useMutation({
    mutationFn: async () => {
      if (!selectedCollector) {
        throw new Error("Collector metadata is still loading");
      }
      if (!monitorUuid) {
        throw new Error("Monitor is required");
      }
      return api.queueJob({
        monitor_uuid: monitorUuid,
        collector_type: selectedCollector.collector_type,
        reason: reason.trim() || undefined,
        parameters: buildCollectorParameters(selectedCollector, fieldValues, advancedJson),
      });
    },
    onSuccess: async (job) => {
      setFormError(null);
      setSelectedJobId(job.job_id);
      setGlobalMonitorUuid(job.monitor_uuid);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["jobs"] }),
        queryClient.invalidateQueries({ queryKey: ["job", job.job_id] }),
        queryClient.invalidateQueries({ queryKey: ["monitorDetail", job.monitor_uuid] }),
        queryClient.invalidateQueries({ queryKey: ["overview"] }),
      ]);
    },
    onError: (error) => {
      setFormError(getErrorMessage(error));
    },
  });

  const requeueMutation = useMutation({
    mutationFn: async (jobId: string) => api.requeueJob(jobId),
    onSuccess: async (job) => {
      setSelectedJobId(job.job_id);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["jobs"] }),
        queryClient.invalidateQueries({ queryKey: ["job"] }),
        queryClient.invalidateQueries({ queryKey: ["monitorDetail", job.monitor_uuid] }),
        queryClient.invalidateQueries({ queryKey: ["overview"] }),
      ]);
    },
  });

  const selectedJob = selectedJobQuery.data ?? jobsQuery.data?.find((job) => job.job_id === selectedJobId);
  const selectedMonitor = monitorMap.get(monitorUuid);
  const selectedJobMonitor = selectedJob ? monitorMap.get(selectedJob.monitor_uuid) : undefined;

  const columns = useMemo<ColumnDef<CollectionJob>[]>(
    () => [
      {
        header: "Queued",
        accessorKey: "created_at",
        cell: ({ row }) => (
          <div className="table-primary">
            <strong>{formatRelativeTime(row.original.created_at)}</strong>
            <span>{formatDateTime(row.original.created_at)}</span>
          </div>
        ),
      },
      {
        header: "Collector",
        accessorKey: "collector_type",
        cell: ({ row }) => collectorLabel(collectors, row.original.collector_type),
      },
      {
        header: "Monitor",
        accessorKey: "monitor_id",
      },
      {
        header: "Status",
        accessorKey: "status",
        cell: ({ row }) => <StatusBadge status={row.original.status} />,
      },
      {
        header: "Progress",
        id: "progress",
        cell: ({ row }) => (
          <div className="table-primary">
            <strong>{row.original.started_at ? formatDurationFrom(row.original.started_at, row.original.completed_at || undefined) : formatDurationFrom(row.original.created_at, row.original.started_at || undefined)}</strong>
            <span>{JOB_STATUS_COPY[row.original.status] ?? "Collection job update."}</span>
          </div>
        ),
      },
      {
        header: "Requested by",
        accessorKey: "requested_by",
        cell: ({ row }) => row.original.requested_by || "unknown",
      },
    ],
    [collectors],
  );

  async function submitJob(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    await queueMutation.mutateAsync();
  }

  function updateJobFilter(key: "jobStatus" | "collectorFilter", value?: string) {
    const next = new URLSearchParams(searchParams);
    if (value) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    setSearchParams(next, { replace: true });
  }

  if (!selectedCollector && collectors.length === 0) {
    return <LoadingScreen label="Loading collector metadata" />;
  }

  return (
    <div className="page-stack">
      <section className="page-hero">
        <div>
          <p className="eyebrow">Collection jobs</p>
          <h1>Queue work with context and live results</h1>
          <p className="subtle-copy">
            Pick a monitor by name, not UUID, queue the right collector, and watch the state move without refreshing the page.
          </p>
        </div>
      </section>

      <div className="jobs-layout">
        <section className="card section-card sticky-card">
          <div className="section-header">
            <div>
              <h2>Queue a collection job</h2>
              <p className="subtle-copy">Collector-specific fields for normal use, raw JSON override for expert mode.</p>
            </div>
          </div>
          <form className="job-form" onSubmit={submitJob}>
            <label>
              Monitor
              <SearchableMonitorPicker
                monitors={monitorOptions?.monitors ?? []}
                value={monitorUuid}
                onChange={(value) => setMonitorUuid(value)}
              />
            </label>
            {selectedMonitor ? (
              <div className={`inline-alert ${isMonitorStale(selectedMonitor) ? "warning" : "info"}`}>
                <strong>{selectedMonitor.monitor_id}</strong>
                <span>
                  {monitorDescriptor(selectedMonitor)} · last check-in {formatRelativeTime(selectedMonitor.last_checkin_at)}
                </span>
              </div>
            ) : null}
            <label>
              Collector
              <select value={collectorType} onChange={(event) => setCollectorType(event.target.value)}>
                {collectors.map((collector) => (
                  <option key={collector.collector_type} value={collector.collector_type}>
                    {collector.label}
                  </option>
                ))}
              </select>
            </label>
            {selectedCollector ? (
              <div className="inline-alert info">
                <strong>{selectedCollector.label}</strong>
                <span>{selectedCollector.description}</span>
              </div>
            ) : null}

            {selectedCollector?.parameters.map((field) => (
              <label key={field.name}>
                {field.label}
                <input
                  type={field.field_type === "number" ? "number" : "text"}
                  value={fieldValues[field.name] ?? ""}
                  placeholder={field.placeholder ?? undefined}
                  onChange={(event) =>
                    setFieldValues((current) => ({
                      ...current,
                      [field.name]: event.target.value,
                    }))
                  }
                />
                <small className="field-hint">{field.description}</small>
              </label>
            ))}

            <label>
              Why are we running this?
              <textarea
                rows={3}
                value={reason}
                placeholder="Example: validate monitor health before requeueing ticket work"
                onChange={(event) => setReason(event.target.value)}
              />
            </label>

            <label>
              Advanced JSON override
              <textarea
                rows={8}
                value={advancedJson}
                placeholder='{"namespace":"example-namespace","limit":25}'
                onChange={(event) => setAdvancedJson(event.target.value)}
              />
              <small className="field-hint">
                Optional. This merges on top of the collector defaults and form fields.
              </small>
            </label>

            {formError ? <InlineError title="Unable to queue job" message={formError} /> : null}

            <button type="submit" disabled={queueMutation.isPending}>
              {queueMutation.isPending ? "Queueing…" : "Queue collection job"}
            </button>
          </form>
        </section>

        <section className="card section-card">
          <div className="section-header">
            <div>
              <h2>Recent jobs</h2>
              <p className="subtle-copy">Live updates every 5 seconds while the tab is visible.</p>
            </div>
            <div className="table-filter-row">
              <select
                value={jobStatus ?? ""}
                onChange={(event) => updateJobFilter("jobStatus", optionalParam(event.target.value))}
              >
                <option value="">All statuses</option>
                <option value="queued">Queued</option>
                <option value="leased">Leased</option>
                <option value="succeeded">Succeeded</option>
                <option value="failed">Failed</option>
                <option value="timed_out">Timed out</option>
              </select>
              <select
                value={jobCollectorFilter ?? ""}
                onChange={(event) => updateJobFilter("collectorFilter", optionalParam(event.target.value))}
              >
                <option value="">All collectors</option>
                {collectors.map((collector) => (
                  <option key={collector.collector_type} value={collector.collector_type}>
                    {collector.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          {jobsQuery.isError ? (
            <InlineError title="Jobs feed unavailable" message={getErrorMessage(jobsQuery.error)} />
          ) : (
            <OperatorTable
              data={jobsQuery.data ?? []}
              columns={columns}
              getRowId={(row) => row.job_id}
              selectedRowId={selectedJobId}
              onSelectRow={(row) => setSelectedJobId(row.job_id)}
              emptyState="No collection jobs matched the current filters."
            />
          )}
        </section>

        <aside className="detail-rail">
          {selectedJobQuery.isLoading && selectedJobId ? (
            <LoadingScreen label="Loading job detail" />
          ) : selectedJobQuery.isError ? (
            <InlineError title="Job detail unavailable" message={getErrorMessage(selectedJobQuery.error)} />
          ) : selectedJob ? (
            <CollectionJobDetail
              job={selectedJob}
              monitor={selectedJobMonitor}
              collectors={collectors}
              onRequeue={() => void requeueMutation.mutate(selectedJob.job_id)}
              requeuePending={requeueMutation.isPending}
            />
          ) : (
            <EmptyPanel
              title="Select a collection job"
              message="The detail rail will show queue timing, monitor freshness, collector errors, and structured results."
            />
          )}
        </aside>
      </div>
    </div>
  );
}

function ConsoleShell({
  settings,
  me,
  onLogout,
}: {
  settings: SettingsResponse;
  me: AuthMeResponse | null;
  onLogout: () => Promise<void>;
}) {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const visibility = useDocumentVisible();
  const [liveRefresh, setLiveRefresh] = useState(true);
  const filters: ConsoleFilters = {
    monitorUuid: optionalParam(searchParams.get("monitor")),
    environmentLabel: optionalParam(searchParams.get("environment")),
    providerType: optionalParam(searchParams.get("provider")),
    accountNumber: optionalParam(searchParams.get("account")),
  };
  const selectedMonitorUuid = optionalParam(searchParams.get("monitorDetail"));
  const selectedTicketId = optionalParam(searchParams.get("ticketDetail"));
  const selectedJobId = optionalParam(searchParams.get("job"));

  const filterOptionsQuery = useQuery({
    queryKey: ["filterOptions"],
    queryFn: api.filterOptions,
    staleTime: 60_000,
  });
  const collectorsQuery = useQuery({
    queryKey: ["collectors"],
    queryFn: api.collectors,
    staleTime: 60_000,
  });

  const collectors = collectorsQuery.data ?? [];
  const activePolling = liveRefresh && visibility;
  const slowPollMs = activePolling ? PAGE_POLL_INTERVAL_MS : false;
  const fastPollMs = activePolling ? DETAIL_POLL_INTERVAL_MS : false;
  const currentNav = NAV_ITEMS.find((item) => location.pathname.startsWith(item.to)) ?? NAV_ITEMS[0];
  const canManageBacklog = hasPermission(me, "manage_backlog");

  function updateSearchParam(key: string, value?: string) {
    const next = new URLSearchParams(searchParams);
    if (value) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    setSearchParams(next, { replace: true });
  }

  function clearFilters() {
    const next = new URLSearchParams(searchParams);
    ["monitor", "environment", "provider", "account"].forEach((key) => next.delete(key));
    setSearchParams(next, { replace: true });
  }

  function openJob(jobId: string) {
    const next = new URLSearchParams(searchParams);
    next.set("job", jobId);
    setSearchParams(next, { replace: true });
    navigate("/jobs");
  }

  const currentMonitor = filterOptionsQuery.data?.monitors.find(
    (monitor) => monitor.monitor_uuid === filters.monitorUuid,
  );

  return (
    <div className="console-shell">
      <aside className="console-sidebar">
        <div className="sidebar-brand">
          <p className="eyebrow">Bakery</p>
          <h1>Operator Console</h1>
          <p className="subtle-copy">
            A live view of monitor health, route inventory, backlog pressure, and collection evidence.
          </p>
        </div>

        <nav className="sidebar-nav" aria-label="Primary">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
            >
              <strong>{item.label}</strong>
              <span>{item.kicker}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-card">
          <strong>{me?.display_name || me?.username || "Open console"}</strong>
          <span>{me ? `${me.role} via ${me.provider}` : "Auth disabled"}</span>
          <small>Bakery {settings.version}</small>
          {settings.auth_enabled ? (
            <button type="button" className="ghost-button" onClick={() => void onLogout()}>
              Sign out
            </button>
          ) : null}
        </div>
      </aside>

      <main className="console-main">
        <header className="console-header">
          <div>
            <p className="eyebrow">{currentNav.kicker}</p>
            <h2>{currentNav.label}</h2>
            <p className="subtle-copy">
              {filters.monitorUuid
                ? `Filtering on ${currentMonitor?.monitor_id || filters.monitorUuid} with shared console filters.`
                : "Use the shared filters below to carry context across every page."}
            </p>
          </div>
          <div className="refresh-panel">
            <div className={`refresh-state ${activePolling ? "live" : "paused"}`}>
              <strong>{activePolling ? "Live refresh on" : "Refresh paused"}</strong>
              <span>{visibility ? "5s detail / 15s overview polling" : "Tab hidden, polling paused automatically"}</span>
            </div>
            <button type="button" className="ghost-button" onClick={() => setLiveRefresh((current) => !current)}>
              {liveRefresh ? "Pause live refresh" : "Resume live refresh"}
            </button>
          </div>
        </header>

        <section className="filter-bar">
          <div className="filter-bar-main">
            <label className="filter-field filter-field-wide">
              <span>Monitor</span>
              <SearchableMonitorPicker
                monitors={filterOptionsQuery.data?.monitors ?? []}
                value={filters.monitorUuid ?? ""}
                onChange={(value) => updateSearchParam("monitor", value || undefined)}
              />
            </label>

            <label className="filter-field">
              <span>Environment</span>
              <select
                value={filters.environmentLabel ?? ""}
                onChange={(event) => updateSearchParam("environment", optionalParam(event.target.value))}
              >
                <option value="">All environments</option>
                {(filterOptionsQuery.data?.environment_labels ?? []).map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>

            <label className="filter-field">
              <span>Provider</span>
              <select
                value={filters.providerType ?? ""}
                onChange={(event) => updateSearchParam("provider", optionalParam(event.target.value))}
              >
                <option value="">All providers</option>
                {(filterOptionsQuery.data?.provider_types ?? []).map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>

            <label className="filter-field">
              <span>Account</span>
              <select
                value={filters.accountNumber ?? ""}
                onChange={(event) => updateSearchParam("account", optionalParam(event.target.value))}
              >
                <option value="">All accounts</option>
                {(filterOptionsQuery.data?.account_numbers ?? []).map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="filter-actions">
            <button type="button" className="ghost-button" onClick={clearFilters}>
              Clear filters
            </button>
          </div>
        </section>

        {filterOptionsQuery.isError ? (
          <InlineError title="Filter metadata unavailable" message={getErrorMessage(filterOptionsQuery.error)} />
        ) : null}
        {collectorsQuery.isError ? (
          <InlineError title="Collector metadata unavailable" message={getErrorMessage(collectorsQuery.error)} />
        ) : null}

        <Routes>
          <Route
            path="/"
            element={<Navigate to="/overview" replace />}
          />
          <Route
            path="/overview"
            element={
              <OverviewPage
                filters={filters}
                slowPollMs={slowPollMs}
                fastPollMs={fastPollMs}
                collectors={collectors}
                onOpenJob={openJob}
              />
            }
          />
          <Route
            path="/monitors"
            element={
              <MonitorsPage
                filters={filters}
                slowPollMs={slowPollMs}
                fastPollMs={fastPollMs}
                selectedMonitorUuid={selectedMonitorUuid}
                setSelectedMonitorUuid={(value) => updateSearchParam("monitorDetail", value)}
                collectors={collectors}
                onOpenJob={openJob}
              />
            }
          />
          <Route
            path="/events"
            element={
              <MonitorEventsPage
                filters={filters}
                slowPollMs={slowPollMs}
                monitorOptions={filterOptionsQuery.data}
              />
            }
          />
          <Route path="/routes" element={<RoutesPage filters={filters} slowPollMs={slowPollMs} />} />
          <Route path="/providers" element={<ProvidersPage filters={filters} slowPollMs={slowPollMs} />} />
          <Route path="/operations" element={<OperationsPage filters={filters} slowPollMs={slowPollMs} />} />
          <Route
            path="/backlog"
            element={
              <BacklogPage
                filters={filters}
                slowPollMs={slowPollMs}
                fastPollMs={fastPollMs}
                selectedTicketId={selectedTicketId}
                setSelectedTicketId={(value) => updateSearchParam("ticketDetail", value)}
                canManageBacklog={canManageBacklog}
              />
            }
          />
          <Route
            path="/jobs"
            element={
              <JobsPage
                filters={filters}
                slowPollMs={slowPollMs}
                fastPollMs={fastPollMs}
                monitorOptions={filterOptionsQuery.data}
                collectors={collectors}
                selectedJobId={selectedJobId}
                setSelectedJobId={(value) => updateSearchParam("job", value)}
                setGlobalMonitorUuid={(value) => updateSearchParam("monitor", value)}
              />
            }
          />
        </Routes>
      </main>
    </div>
  );
}

async function loadCurrentOperator(): Promise<AuthMeResponse | null> {
  try {
    return await api.me();
  } catch (error) {
    if (isUnauthorized(error)) {
      return null;
    }
    throw error;
  }
}

export default function App() {
  const queryClient = useQueryClient();
  const [loginError, setLoginError] = useState<string | null>(null);
  const settingsQuery = useQuery({
    queryKey: ["settings"],
    queryFn: api.settings,
    staleTime: 60_000,
  });
  const meQuery = useQuery({
    queryKey: ["me"],
    queryFn: loadCurrentOperator,
    enabled: settingsQuery.isSuccess && settingsQuery.data.auth_enabled,
    retry: false,
  });

  const loginMutation = useMutation({
    mutationFn: async ({
      provider,
      username,
      password,
    }: {
      provider: string;
      username: string;
      password: string;
    }) => api.login(provider, username, password),
    onSuccess: async () => {
      setLoginError(null);
      await queryClient.invalidateQueries({ queryKey: ["me"] });
    },
    onError: (error) => {
      setLoginError(getErrorMessage(error));
    },
  });

  const logoutMutation = useMutation({
    mutationFn: api.logout,
    onSuccess: async () => {
      await queryClient.invalidateQueries();
      await queryClient.refetchQueries({ queryKey: ["settings"] });
    },
  });

  if (settingsQuery.isLoading || (settingsQuery.data?.auth_enabled && meQuery.isLoading)) {
    return <LoadingScreen label="Loading Bakery operator console" />;
  }

  if (settingsQuery.isError) {
    return (
      <ErrorScreen
        title="Bakery UI bootstrap failed"
        message={getErrorMessage(settingsQuery.error)}
        onRetry={() => void settingsQuery.refetch()}
      />
    );
  }

  if (meQuery.isError) {
    return (
      <ErrorScreen
        title="Operator session lookup failed"
        message={getErrorMessage(meQuery.error)}
        onRetry={() => void meQuery.refetch()}
      />
    );
  }

  const settings = settingsQuery.data;
  if (!settings) {
    return <LoadingScreen label="Loading Bakery operator console" />;
  }

  if (settings.auth_enabled && !meQuery.data) {
    return (
      <LoginScreen
        settings={settings}
        error={loginError}
        pending={loginMutation.isPending}
        onLogin={async (provider, username, password) => {
          await loginMutation.mutateAsync({ provider, username, password });
        }}
      />
    );
  }

  return (
    <ConsoleShell
      settings={settings}
      me={settings.auth_enabled ? meQuery.data ?? null : null}
      onLogout={async () => {
        await logoutMutation.mutateAsync();
      }}
    />
  );
}
