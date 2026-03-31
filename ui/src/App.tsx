import { FormEvent, useEffect, useState } from "react";

import { ApiError, api } from "./api";
import type {
  AuthMeResponse,
  CollectionJob,
  MonitorRow,
  Overview,
  ProviderAnalyticsRow,
  RouteRow,
  SettingsResponse,
  BacklogRow,
} from "./contracts";

type View = "overview" | "monitors" | "routes" | "providers" | "backlog" | "jobs";

type DashboardData = {
  overview: Overview | null;
  monitors: MonitorRow[];
  routes: RouteRow[];
  providers: ProviderAnalyticsRow[];
  backlog: BacklogRow[];
  jobs: CollectionJob[];
};

const emptyData: DashboardData = {
  overview: null,
  monitors: [],
  routes: [],
  providers: [],
  backlog: [],
  jobs: [],
};

async function loadDashboard(): Promise<DashboardData> {
  const [overview, monitors, routes, providers, backlog, jobs] = await Promise.all([
    api.overview(),
    api.monitors(),
    api.routes(),
    api.providers(),
    api.backlog(),
    api.jobs(),
  ]);
  return { overview, monitors, routes, providers, backlog, jobs };
}

function LoginScreen({
  settings,
  error,
  onLogin,
}: {
  settings: SettingsResponse;
  error: string | null;
  onLogin: (provider: string, username: string, password: string) => Promise<void>;
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
        <p className="eyebrow">Bakery Operator Console</p>
        <h1>Signal first, panic never.</h1>
        <p className="lead">
          Inspect PoundCake monitors, query route inventory, and queue read-only collection jobs
          from one place.
        </p>
        {error ? <div className="error-banner">{error}</div> : null}
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
              <input value={username} onChange={(event) => setUsername(event.target.value)} />
            </label>
            <label>
              Password
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            <button type="submit">Sign In</button>
          </form>
        ) : null}
        <div className="provider-strip">
          {settings.auth_providers
            .filter((item) => item.browser_login)
            .map((item) => (
              <a
                key={item.name}
                className="provider-link"
                href={`/api/v1/auth/oidc/login?provider=${encodeURIComponent(item.name)}&next=/`}
              >
                Continue with {item.label}
              </a>
            ))}
        </div>
      </div>
    </div>
  );
}

function Table({ rows }: { rows: Array<Record<string, unknown>> }) {
  if (rows.length === 0) {
    return <div className="empty-state">No records.</div>;
  }
  const keys = Object.keys(rows[0]);
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {keys.map((key) => (
              <th key={key}>{key}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {keys.map((key) => (
                <td key={key}>{renderValue(row[key])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "-";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

export default function App() {
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [me, setMe] = useState<AuthMeResponse | null>(null);
  const [data, setData] = useState<DashboardData>(emptyData);
  const [selectedView, setSelectedView] = useState<View>("overview");
  const [selectedJob, setSelectedJob] = useState<CollectionJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [jobForm, setJobForm] = useState({
    monitor_uuid: "",
    collector_type: "monitor_diagnostics",
    reason: "",
    parameters: "{}",
  });

  async function bootstrap() {
    setLoading(true);
    setError(null);
    try {
      const settingsValue = await api.settings();
      setSettings(settingsValue);
      try {
        const meValue = await api.me();
        setMe(meValue);
        setData(await loadDashboard());
      } catch (exc) {
        if (exc instanceof ApiError && exc.status === 401) {
          setMe(null);
          setData(emptyData);
        } else {
          throw exc;
        }
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void bootstrap();
  }, []);

  async function handleLogin(provider: string, username: string, password: string) {
    setError(null);
    try {
      await api.login(provider, username, password);
      await bootstrap();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    }
  }

  async function handleLogout() {
    await api.logout();
    await bootstrap();
  }

  async function handleQueueJob(event: FormEvent) {
    event.preventDefault();
    try {
      await api.queueJob({
        monitor_uuid: jobForm.monitor_uuid,
        collector_type: jobForm.collector_type,
        reason: jobForm.reason || undefined,
        parameters: JSON.parse(jobForm.parameters || "{}") as Record<string, unknown>,
      });
      setJobForm((current) => ({ ...current, reason: "", parameters: "{}" }));
      setData(await loadDashboard());
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    }
  }

  async function handleRequeue(jobId: string) {
    try {
      await api.requeueJob(jobId);
      setData(await loadDashboard());
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    }
  }

  if (loading) {
    return <div className="loading-shell">Loading Bakery control plane...</div>;
  }

  if (!settings) {
    return <div className="loading-shell">Settings unavailable.</div>;
  }

  if (!me) {
    return <LoginScreen settings={settings} error={error} onLogin={handleLogin} />;
  }

  const views: Array<{ id: View; label: string }> = [
    { id: "overview", label: "Overview" },
    { id: "monitors", label: "Monitors" },
    { id: "routes", label: "Routes" },
    { id: "providers", label: "Providers" },
    { id: "backlog", label: "Backlog" },
    { id: "jobs", label: "Collection Jobs" },
  ];

  return (
    <div className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Bakery {settings.version}</p>
          <h1>Operator control plane for PoundCake traffic.</h1>
          <p className="lead">
            Durable reports, monitor inventory, and a pull-based collection queue for read-only
            diagnostics.
          </p>
        </div>
        <div className="hero-meta">
          <div className="pill">
            {me.display_name || me.username}
            <span>{me.role}</span>
          </div>
          <button className="ghost-button" onClick={() => void handleLogout()}>
            Sign Out
          </button>
        </div>
      </header>

      {error ? <div className="error-banner">{error}</div> : null}

      <nav className="nav-tabs">
        {views.map((view) => (
          <button
            key={view.id}
            className={selectedView === view.id ? "tab active" : "tab"}
            onClick={() => setSelectedView(view.id)}
          >
            {view.label}
          </button>
        ))}
      </nav>

      {selectedView === "overview" && data.overview ? (
        <section className="card-grid">
          {Object.entries(data.overview).map(([key, value]) => (
            <article className="metric-card" key={key}>
              <span>{key.replace(/_/g, " ")}</span>
              <strong>{value}</strong>
            </article>
          ))}
        </section>
      ) : null}

      {selectedView === "monitors" ? <Table rows={data.monitors} /> : null}
      {selectedView === "routes" ? <Table rows={data.routes} /> : null}
      {selectedView === "providers" ? <Table rows={data.providers} /> : null}
      {selectedView === "backlog" ? <Table rows={data.backlog} /> : null}

      {selectedView === "jobs" ? (
        <section className="jobs-layout">
          <form className="job-form card" onSubmit={handleQueueJob}>
            <h2>Queue Collection Job</h2>
            <label>
              Monitor UUID
              <input
                value={jobForm.monitor_uuid}
                onChange={(event) =>
                  setJobForm((current) => ({ ...current, monitor_uuid: event.target.value }))
                }
                required
              />
            </label>
            <label>
              Collector
              <select
                value={jobForm.collector_type}
                onChange={(event) =>
                  setJobForm((current) => ({ ...current, collector_type: event.target.value }))
                }
              >
                <option value="monitor_diagnostics">monitor_diagnostics</option>
                <option value="cluster_inventory">cluster_inventory</option>
                <option value="ticket_context">ticket_context</option>
              </select>
            </label>
            <label>
              Reason
              <input
                value={jobForm.reason}
                onChange={(event) =>
                  setJobForm((current) => ({ ...current, reason: event.target.value }))
                }
              />
            </label>
            <label>
              Parameters (JSON)
              <textarea
                rows={6}
                value={jobForm.parameters}
                onChange={(event) =>
                  setJobForm((current) => ({ ...current, parameters: event.target.value }))
                }
              />
            </label>
            <button type="submit">Queue Job</button>
          </form>

          <div className="card">
            <div className="section-header">
              <h2>Queued and Completed Jobs</h2>
            </div>
            <div className="job-list">
              {data.jobs.map((job) => (
                <button
                  key={job.job_id}
                  className={selectedJob?.job_id === job.job_id ? "job-row active" : "job-row"}
                  onClick={() => setSelectedJob(job)}
                >
                  <span>{job.collector_type}</span>
                  <strong>{job.monitor_id}</strong>
                  <em>{job.status}</em>
                </button>
              ))}
            </div>
          </div>

          <div className="card">
            <div className="section-header">
              <h2>Job Detail</h2>
              {selectedJob && (
                <button className="ghost-button" onClick={() => void handleRequeue(selectedJob.job_id)}>
                  Requeue
                </button>
              )}
            </div>
            <pre className="json-view">{JSON.stringify(selectedJob, null, 2)}</pre>
          </div>
        </section>
      ) : null}
    </div>
  );
}
