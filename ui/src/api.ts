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
  overview: () => request<Overview>("/api/v1/reports/overview"),
  monitors: () => request<MonitorRow[]>("/api/v1/reports/monitors"),
  routes: () => request<RouteRow[]>("/api/v1/reports/routes"),
  providers: () => request<ProviderAnalyticsRow[]>("/api/v1/reports/providers"),
  backlog: () => request<BacklogRow[]>("/api/v1/reports/backlog"),
  jobs: () => request<CollectionJob[]>("/api/v1/collection-jobs"),
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
