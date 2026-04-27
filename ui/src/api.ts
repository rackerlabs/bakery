import type {
  AuthMeResponse,
  BacklogRow,
  CollectionCollector,
  CollectionJob,
  FilterOptions,
  JobFilters,
  MonitorDetail,
  MonitorEventRow,
  MonitorRemovalResult,
  MonitorRow,
  OperationAnalyticsRow,
  Overview,
  ProviderAnalyticsRow,
  ReportFilters,
  RouteRow,
  SettingsResponse,
  TicketDetail,
  TicketOperationList,
} from "./contracts";
import { buildApiUrl, usesExternalApiBaseUrl } from "./config";

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

function buildSearch(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === "") {
      return;
    }
    search.set(key, String(value));
  });
  const serialized = search.toString();
  return serialized ? `?${serialized}` : "";
}

function reportSearch(filters: ReportFilters = {}): string {
  return buildSearch({
    monitor_uuid: filters.monitorUuid,
    environment_label: filters.environmentLabel,
    provider_type: filters.providerType,
    account_number: filters.accountNumber,
    start_at: filters.startAt,
    end_at: filters.endAt,
    limit: filters.limit,
    offset: filters.offset,
  });
}

function jobSearch(filters: JobFilters = {}): string {
  return buildSearch({
    monitor_uuid: filters.monitorUuid,
    status: filters.status,
    collector_type: filters.collectorType,
    limit: filters.limit,
    offset: filters.offset,
  });
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(buildApiUrl(path), {
    credentials: usesExternalApiBaseUrl() ? "include" : "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers || {}),
    },
    ...init,
  });
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json")
    ? await response.json().catch(() => null)
    : await response.text().catch(() => "");
  if (!response.ok) {
    const detail =
      typeof body === "object" && body && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : response.statusText;
    throw new ApiError(detail || `Request failed (${response.status})`, response.status, body);
  }
  return body as T;
}

export const api = {
  settings: () => request<SettingsResponse>("/api/v1/settings"),
  me: () => request<AuthMeResponse>("/api/v1/auth/me"),
  login: (provider: string, username: string, password: string) =>
    request("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ provider, username, password }),
    }),
  logout: () => request("/api/v1/auth/logout", { method: "POST" }),
  filterOptions: () => request<FilterOptions>("/api/v1/reports/filter-options"),
  collectors: () => request<CollectionCollector[]>("/api/v1/collection-jobs/collectors"),
  overview: (filters: ReportFilters = {}) =>
    request<Overview>(`/api/v1/reports/overview${reportSearch(filters)}`),
  monitors: (filters: ReportFilters = {}) =>
    request<MonitorRow[]>(`/api/v1/reports/monitors${reportSearch(filters)}`),
  monitorDetail: (monitorUuid: string) =>
    request<MonitorDetail>(`/api/v1/reports/monitors/${monitorUuid}/detail`),
  removeMonitor: (monitorUuid: string) =>
    request<MonitorRemovalResult>(`/api/v1/admin/monitors/${monitorUuid}`, {
      method: "DELETE",
    }),
  monitorEvents: (filters: ReportFilters = {}) =>
    request<MonitorEventRow[]>(`/api/v1/reports/monitor-events${reportSearch(filters)}`),
  routes: (filters: ReportFilters = {}) =>
    request<RouteRow[]>(`/api/v1/reports/routes${reportSearch(filters)}`),
  providers: (filters: ReportFilters = {}) =>
    request<ProviderAnalyticsRow[]>(`/api/v1/reports/providers${reportSearch(filters)}`),
  operations: (filters: ReportFilters = {}) =>
    request<OperationAnalyticsRow[]>(`/api/v1/reports/operations${reportSearch(filters)}`),
  backlog: (filters: ReportFilters = {}) =>
    request<BacklogRow[]>(`/api/v1/reports/backlog${reportSearch(filters)}`),
  operatorTicket: (ticketId: string) =>
    request<TicketDetail>(`/api/v1/operator/tickets/${ticketId}`),
  operatorTicketOperations: (ticketId: string, limit = 100) =>
    request<TicketOperationList>(`/api/v1/operator/tickets/${ticketId}/operations${buildSearch({ limit })}`),
  operatorFindTicket: (ticketId: string) =>
    request<TicketDetail>(`/api/v1/operator/tickets/${ticketId}/find`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  operatorCloseTicket: (
    ticketId: string,
    payload: {
      resolution_notes?: string;
      resolution_code?: string;
      state?: string;
      source?: string;
      context?: Record<string, unknown>;
    },
  ) =>
    request(`/api/v1/operator/tickets/${ticketId}/close`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  jobs: (filters: JobFilters = {}) =>
    request<CollectionJob[]>(`/api/v1/collection-jobs${jobSearch(filters)}`),
  job: (jobId: string) => request<CollectionJob>(`/api/v1/collection-jobs/${jobId}`),
  queueJob: (payload: {
    monitor_uuid: string;
    collector_type: string;
    reason?: string;
    parameters?: Record<string, unknown>;
  }) =>
    request<CollectionJob>("/api/v1/collection-jobs", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  requeueJob: (jobId: string) =>
    request<CollectionJob>(`/api/v1/collection-jobs/${jobId}/requeue`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
};
