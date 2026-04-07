export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "Never";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function formatRelativeTime(value: string | null | undefined, now = Date.now()): string {
  if (!value) {
    return "Never";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  const diffSeconds = Math.round((date.getTime() - now) / 1000);
  const abs = Math.abs(diffSeconds);
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

  if (abs < 60) {
    return formatter.format(diffSeconds, "second");
  }
  if (abs < 3600) {
    return formatter.format(Math.round(diffSeconds / 60), "minute");
  }
  if (abs < 86400) {
    return formatter.format(Math.round(diffSeconds / 3600), "hour");
  }
  return formatter.format(Math.round(diffSeconds / 86400), "day");
}

export function formatDurationFrom(start: string | null | undefined, end?: string | null): string {
  if (!start) {
    return "Not started";
  }
  const startTime = new Date(start).getTime();
  const endTime = end ? new Date(end).getTime() : Date.now();
  if (Number.isNaN(startTime) || Number.isNaN(endTime)) {
    return "Unknown";
  }
  return formatDurationMs(Math.max(endTime - startTime, 0));
}

export function formatDurationMs(ms: number): string {
  const totalSeconds = Math.round(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${seconds}s`;
  }
  return `${seconds}s`;
}

export function formatCount(value: number): string {
  return new Intl.NumberFormat().format(value);
}

export function formatBytes(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "Unknown";
  }
  if (value === 0) {
    return "0 B";
  }
  const units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"];
  const sign = value < 0 ? -1 : 1;
  let scaled = Math.abs(value);
  let unitIndex = 0;
  while (scaled >= 1024 && unitIndex < units.length - 1) {
    scaled /= 1024;
    unitIndex += 1;
  }
  const digits = scaled >= 10 || unitIndex === 0 ? 0 : 1;
  return `${sign < 0 ? "-" : ""}${scaled.toFixed(digits)} ${units[unitIndex]}`;
}

export function formatCpuMillicores(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "Unknown";
  }
  if (Math.abs(value) >= 1000 && value % 1000 === 0) {
    return `${value / 1000} cores`;
  }
  if (Math.abs(value) >= 1000) {
    return `${(value / 1000).toFixed(1)} cores`;
  }
  return `${Math.round(value)}m`;
}

export function humanizeIdentifier(value: string): string {
  return value.replace(/_/g, " ");
}
