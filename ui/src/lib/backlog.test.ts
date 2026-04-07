import { describe, expect, it } from "vitest";

import { backlogActionState, backlogReasonLabel, backlogReasonMessage } from "./backlog";

const dryRunTicket = {
  ticket_id: "ticket-dryrun",
  provider_type: "rackspace_core",
  provider_ticket_id: "dryrun-ticket-dryrun",
  monitor_uuid: "monitor-1",
  monitor_id: "alpha-monitor",
  environment_label: "prod",
  state: "open",
  latest_error: null,
  created_at: "2026-04-06T12:00:00Z",
  updated_at: "2026-04-06T12:05:00Z",
  is_dry_run: true,
  backlog_reason: "dry_run",
  can_close: true,
  can_resync: false,
};

describe("backlog helpers", () => {
  it("explains dry-run backlog rows clearly", () => {
    expect(backlogReasonLabel(dryRunTicket.backlog_reason)).toBe("Dry run");
    expect(backlogReasonMessage(dryRunTicket)).toMatch(/never close/i);
    expect(backlogActionState(dryRunTicket)).toEqual({
      canClose: true,
      canResync: false,
      isReadOnly: false,
    });
  });

  it("marks healthy provider-backed tickets read-only", () => {
    expect(
      backlogActionState({
        ...dryRunTicket,
        is_dry_run: false,
        backlog_reason: "open",
        can_close: false,
        can_resync: false,
      }),
    ).toEqual({
      canClose: false,
      canResync: false,
      isReadOnly: true,
    });
  });
});
