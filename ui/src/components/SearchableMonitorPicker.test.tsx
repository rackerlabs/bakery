import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { SearchableMonitorPicker } from "./SearchableMonitorPicker";

describe("SearchableMonitorPicker", () => {
  it("shows human-friendly monitor labels and returns the selected uuid", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const monitors = [
      {
        monitor_uuid: "monitor-uuid-1",
        monitor_id: "alpha-monitor",
        status: "healthy",
        environment_label: "prod",
        region: "ord",
        cluster_name: "cluster-a",
        namespace: "rackspace",
        release_name: "poundcake",
        route_sync_required: false,
        last_checkin_at: "2026-04-06T12:00:00Z",
      },
      {
        monitor_uuid: "monitor-uuid-2",
        monitor_id: "beta-monitor",
        status: "unreachable",
        environment_label: "stage",
        region: "dfw",
        cluster_name: "cluster-b",
        namespace: "example-stage",
        release_name: "poundcake-stage",
        route_sync_required: true,
        last_checkin_at: "2026-04-06T09:00:00Z",
      },
    ];

    function WrappedPicker() {
      const [value, setValue] = useState("");

      return (
        <SearchableMonitorPicker
          monitors={monitors}
          value={value}
          onChange={(monitorUuid) => {
            onChange(monitorUuid);
            setValue(monitorUuid);
          }}
        />
      );
    }

    render(<WrappedPicker />);

    await user.click(screen.getByLabelText("Monitor"));
    await user.type(screen.getByLabelText("Monitor"), "alpha");

    expect(screen.getByRole("button", { name: /alpha-monitor/i })).toBeInTheDocument();
    expect(screen.getByText(/prod/i)).toBeInTheDocument();
    expect(screen.getByText(/monitor-uuid-1/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /alpha-monitor/i }));

    expect(onChange).toHaveBeenCalledWith("monitor-uuid-1");
    expect(screen.getByLabelText("Monitor")).toHaveValue("alpha-monitor · prod");
  });
});
