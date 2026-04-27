import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import type { AuthMeResponse, FilterOptions, MonitorDetail, MonitorRow, SettingsResponse } from "./contracts";

const apiMock = vi.hoisted(() => ({
  settings: vi.fn(),
  me: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  filterOptions: vi.fn(),
  collectors: vi.fn(),
  overview: vi.fn(),
  monitors: vi.fn(),
  monitorDetail: vi.fn(),
  removeMonitor: vi.fn(),
  monitorEvents: vi.fn(),
  routes: vi.fn(),
  providers: vi.fn(),
  operations: vi.fn(),
  backlog: vi.fn(),
  jobs: vi.fn(),
}));

vi.mock("./api", () => ({
  ApiError: class ApiError extends Error {
    status: number;
    body: unknown;

    constructor(message: string, status: number, body: unknown) {
      super(message);
      this.status = status;
      this.body = body;
    }
  },
  api: apiMock,
}));

const settings: SettingsResponse = {
  auth_enabled: true,
  rbac_enabled: true,
  auth_providers: [],
  version: "0.1.18",
};

const monitor: MonitorRow = {
  monitor_uuid: "monitor-uuid-1",
  monitor_id: "alpha-monitor",
  status: "unreachable",
  environment_label: "prod",
  region: "ord",
  cluster_name: "ord-deployer",
  namespace: "rackspace",
  release_name: "poundcake",
  tags: [],
  route_sync_required: false,
  route_count: 1,
  outage_route_count: 0,
  last_checkin_at: null,
  unreachable_at: "2026-04-27T14:00:00Z",
  created_at: "2026-04-27T13:00:00Z",
  updated_at: "2026-04-27T14:00:00Z",
  last_seen_payload: null,
};

const filters: FilterOptions = {
  monitors: [monitor],
  environment_labels: ["prod"],
  provider_types: [],
  account_numbers: [],
};

const detail: MonitorDetail = {
  monitor,
  recent_events: [],
  recent_routes: [],
  recent_jobs: [],
  latest_successful_jobs: [],
  operation_analytics: [],
  backlog: [],
};

function operator(permissions: string[]): AuthMeResponse {
  return {
    username: "operator",
    display_name: "Operator",
    provider: "local",
    role: permissions.includes("manage_bootstrap") ? "admin" : "reader",
    principal_type: "user",
    principal_id: 1,
    is_superuser: false,
    permissions,
    groups: [],
    expires_at: "2030-01-01T00:00:00Z",
  };
}

function renderConsole(permissions: string[], options: { emptyAfterRemoval?: boolean } = {}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        refetchOnWindowFocus: false,
      },
    },
  });
  apiMock.settings.mockResolvedValue(settings);
  apiMock.me.mockResolvedValue(operator(permissions));
  apiMock.filterOptions.mockResolvedValue(filters);
  apiMock.collectors.mockResolvedValue([]);
  if (options.emptyAfterRemoval) {
    apiMock.monitors.mockResolvedValueOnce([monitor]).mockResolvedValue([]);
  } else {
    apiMock.monitors.mockResolvedValue([monitor]);
  }
  apiMock.monitorDetail.mockResolvedValue(detail);
  apiMock.removeMonitor.mockResolvedValue({
    monitor_uuid: monitor.monitor_uuid,
    monitor_id: monitor.monitor_id,
    removed_at: "2026-04-27T14:05:00Z",
    removed_by: "operator:admin",
    affected_counts: { monitors: 1 },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/monitors"]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("App monitor removal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows monitor removal controls only to bootstrap managers", async () => {
    const { unmount } = renderConsole(["read", "manage_bootstrap"]);

    expect(await screen.findByRole("button", { name: "Remove monitor" })).toBeInTheDocument();

    unmount();
    renderConsole(["read"]);

    expect(await screen.findByText("alpha-monitor")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove monitor" })).not.toBeInTheDocument();
  });

  it("requires typed confirmation and refreshes monitor data after removal", async () => {
    const user = userEvent.setup();
    renderConsole(["read", "manage_bootstrap"], { emptyAfterRemoval: true });

    const removeButton = await screen.findByRole("button", { name: "Remove monitor" });
    expect(removeButton).toBeDisabled();

    await user.type(screen.getByLabelText("Confirm monitor ID"), "alpha-monitor");
    expect(removeButton).toBeEnabled();
    await user.click(removeButton);

    await waitFor(() => {
      expect(apiMock.removeMonitor).toHaveBeenCalledWith("monitor-uuid-1");
    });
    await waitFor(() => {
      expect(apiMock.monitors.mock.calls.length).toBeGreaterThan(1);
    });
    expect(await screen.findByText("Removed monitor alpha-monitor.")).toBeInTheDocument();
  });
});
