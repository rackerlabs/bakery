import { useEffect, useMemo, useState } from "react";

import type { MonitorFilterOption } from "../contracts";
import { formatRelativeTime } from "../lib/format";
import { StatusBadge } from "./StatusBadge";

function monitorLabel(monitor: MonitorFilterOption): string {
  return monitor.environment_label
    ? `${monitor.monitor_id} · ${monitor.environment_label}`
    : monitor.monitor_id;
}

export function SearchableMonitorPicker({
  monitors,
  value,
  onChange,
}: {
  monitors: MonitorFilterOption[];
  value: string;
  onChange: (monitorUuid: string) => void;
}) {
  const selectedMonitor = monitors.find((monitor) => monitor.monitor_uuid === value) ?? null;
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open && selectedMonitor) {
      setQuery(monitorLabel(selectedMonitor));
    }
    if (!open && !selectedMonitor) {
      setQuery("");
    }
  }, [open, selectedMonitor]);

  const filteredMonitors = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) {
      return monitors.slice(0, 12);
    }
    return monitors
      .filter((monitor) =>
        [
          monitor.monitor_id,
          monitor.environment_label,
          monitor.cluster_name,
          monitor.namespace,
          monitor.release_name,
          monitor.monitor_uuid,
        ]
          .filter(Boolean)
          .some((candidate) => String(candidate).toLowerCase().includes(normalizedQuery)),
      )
      .slice(0, 12);
  }, [monitors, query]);

  return (
    <div className="monitor-picker">
      <div className="picker-input-row">
        <input
          aria-label="Monitor"
          value={query}
          placeholder="Search by monitor name, environment, or UUID"
          onFocus={() => {
            setOpen(true);
            if (selectedMonitor) {
              setQuery("");
            }
          }}
          onBlur={() => {
            window.setTimeout(() => {
              setOpen(false);
            }, 120);
          }}
          onChange={(event) => {
            setOpen(true);
            setQuery(event.target.value);
          }}
        />
        {value ? (
          <button
            type="button"
            className="ghost-button"
            onClick={() => {
              setQuery("");
              onChange("");
              setOpen(false);
            }}
          >
            Clear
          </button>
        ) : null}
      </div>
      {open ? (
        <div className="picker-menu" role="listbox">
          {filteredMonitors.length === 0 ? (
            <div className="picker-empty">No monitors match that search.</div>
          ) : (
            filteredMonitors.map((monitor) => (
              <button
                key={monitor.monitor_uuid}
                type="button"
                className="picker-option"
                onMouseDown={(event) => {
                  event.preventDefault();
                  onChange(monitor.monitor_uuid);
                  setQuery(monitorLabel(monitor));
                  setOpen(false);
                }}
              >
                <div className="picker-option-main">
                  <strong>{monitor.monitor_id}</strong>
                  <StatusBadge status={monitor.status} />
                </div>
                <span className="picker-option-meta">
                  {monitor.environment_label || monitor.cluster_name || monitor.namespace || "No environment metadata"}
                </span>
                <span className="picker-option-meta">
                  Last check-in {formatRelativeTime(monitor.last_checkin_at)} · {monitor.monitor_uuid}
                </span>
              </button>
            ))
          )}
        </div>
      ) : null}
    </div>
  );
}
