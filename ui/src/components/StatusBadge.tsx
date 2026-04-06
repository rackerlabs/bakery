type StatusTone =
  | "healthy"
  | "warning"
  | "danger"
  | "info"
  | "muted";

function toneForStatus(status: string): StatusTone {
  switch (status) {
    case "healthy":
    case "succeeded":
    case "open":
      return "healthy";
    case "queued":
    case "leased":
    case "route_sync_required":
      return "info";
    case "unreachable":
    case "failed":
    case "dead_letter":
    case "timed_out":
      return "danger";
    case "degraded":
    case "warning":
      return "warning";
    default:
      return "muted";
  }
}

export function StatusBadge({ status }: { status: string }) {
  const tone = toneForStatus(status);
  return <span className={`status-badge ${tone}`}>{status.replace(/_/g, " ")}</span>;
}
