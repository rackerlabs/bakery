export type AuthProvider = {
  name: string;
  label: string;
  login_mode: string;
  cli_login_mode: string;
  browser_login: boolean;
  device_login: boolean;
  password_login: boolean;
};

export type SettingsResponse = {
  auth_enabled: boolean;
  rbac_enabled: boolean;
  auth_providers: AuthProvider[];
  version: string;
};

export type AuthMeResponse = {
  username: string;
  display_name: string | null;
  provider: string;
  role: string;
  principal_type: string;
  principal_id: number | null;
  is_superuser: boolean;
  permissions: string[];
  groups: string[];
  expires_at: string | null;
};

export type Overview = {
  monitors_total: number;
  monitors_healthy: number;
  monitors_unreachable: number;
  open_tickets: number;
  queued_operations: number;
  failed_operations: number;
  dead_letter_operations: number;
  queued_collection_jobs: number;
  leased_collection_jobs: number;
  timed_out_collection_jobs: number;
};

export type MonitorRow = {
  monitor_uuid: string;
  monitor_id: string;
  status: string;
  environment_label: string | null;
  region: string | null;
  cluster_name: string | null;
  namespace: string | null;
  release_name: string | null;
  tags: string[];
  route_sync_required: boolean;
  route_count: number;
  outage_route_count: number;
  last_checkin_at: string | null;
  unreachable_at: string | null;
  created_at: string;
  updated_at: string;
  last_seen_payload: Record<string, unknown> | null;
};

export type RouteRow = {
  monitor_uuid: string;
  monitor_id: string;
  environment_label: string | null;
  scope: string;
  owner_key: string;
  route_id: string;
  label: string;
  provider_type: string;
  execution_target: string;
  destination_target: string;
  account_number: string | null;
  queue: string | null;
  subcategory: string | null;
  enabled: boolean;
  outage_enabled: boolean;
  position: number;
  updated_at: string;
};

export type ProviderAnalyticsRow = {
  provider_type: string;
  route_count: number;
  ticket_count: number;
  open_ticket_count: number;
  failed_operation_count: number;
  dead_letter_count: number;
};

export type BacklogRow = {
  ticket_id: string;
  provider_type: string;
  provider_ticket_id: string | null;
  monitor_uuid: string | null;
  monitor_id: string | null;
  environment_label: string | null;
  state: string;
  latest_error: string | null;
  created_at: string;
  updated_at: string;
};

export type CollectionJob = {
  job_id: string;
  monitor_uuid: string;
  monitor_id: string;
  collector_type: string;
  status: string;
  parameters: Record<string, unknown>;
  reason: string | null;
  requested_by: string | null;
  lease_expires_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  updated_at: string;
};
