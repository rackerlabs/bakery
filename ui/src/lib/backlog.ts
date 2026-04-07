import type { BacklogRow } from "../contracts";

export function backlogReasonLabel(reason: string): string {
  if (reason === "dry_run") {
    return "Dry run";
  }
  if (reason === "error") {
    return "Needs attention";
  }
  return "Open";
}

export function backlogReasonMessage(ticket: BacklogRow): string {
  if (ticket.is_dry_run) {
    return "This ticket was created in Bakery dry-run mode. It will never close in a provider because no provider ticket exists behind it.";
  }
  if (ticket.backlog_reason === "error") {
    return "Bakery has local error state for this ticket. Resync against the provider or close it explicitly when operator review is complete.";
  }
  return "This ticket is open in Bakery and currently read-only in this first management pass.";
}

export function backlogActionState(ticket: BacklogRow): {
  canClose: boolean;
  canResync: boolean;
  isReadOnly: boolean;
} {
  return {
    canClose: Boolean(ticket.can_close),
    canResync: Boolean(ticket.can_resync),
    isReadOnly: !ticket.can_close && !ticket.can_resync,
  };
}
