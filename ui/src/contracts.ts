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

export type MonitorFilterOption = {
  monitor_uuid: string;
  monitor_id: string;
  status: string;
  environment_label: string | null;
  region: string | null;
  cluster_name: string | null;
  namespace: string | null;
  release_name: string | null;
  route_sync_required: boolean;
  last_checkin_at: string | null;
};

export type FilterOptions = {
  monitors: MonitorFilterOption[];
  environment_labels: string[];
  provider_types: string[];
  account_numbers: string[];
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

export type MonitorEventRow = {
  monitor_uuid: string;
  event_type: string;
  payload: Record<string, unknown> | null;
  created_at: string;
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

export type OperationAnalyticsRow = {
  provider_type: string;
  action: string;
  status: string;
  count: number;
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
  is_dry_run: boolean;
  backlog_reason: string;
  can_close: boolean;
  can_resync: boolean;
};

export type TicketDetail = {
  ticket_id: string;
  provider_type: string;
  provider_ticket_id: string | null;
  state: string;
  latest_error: string | null;
  created_at: string;
  updated_at: string;
  data_source: string;
  ticket_data: Record<string, unknown> | null;
  last_sync_operation_id: string | null;
  last_sync_at: string | null;
};

export type TicketOperation = {
  operation_id: string;
  ticket_id: string;
  action: string;
  status: string;
  attempt_count: number;
  max_attempts: number;
  next_attempt_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  last_error: string | null;
  provider_response: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type TicketOperationList = {
  ticket_id: string;
  operations: TicketOperation[];
  count: number;
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

export type CollectionCollectorField = {
  name: string;
  label: string;
  field_type: string;
  description: string;
  required: boolean;
  default_value: unknown;
  placeholder: string | null;
};

export type CollectionCollector = {
  collector_type: string;
  label: string;
  description: string;
  default_parameters: Record<string, unknown>;
  example_parameters: Record<string, unknown>;
  parameters: CollectionCollectorField[];
};

export type MonitorDetail = {
  monitor: MonitorRow;
  recent_events: MonitorEventRow[];
  recent_routes: RouteRow[];
  recent_jobs: CollectionJob[];
  latest_successful_jobs: CollectionJob[];
  operation_analytics: OperationAnalyticsRow[];
  backlog: BacklogRow[];
};

export type ReportFilters = {
  monitorUuid?: string;
  environmentLabel?: string;
  providerType?: string;
  accountNumber?: string;
  startAt?: string;
  endAt?: string;
  limit?: number;
  offset?: number;
};

export type JobFilters = {
  monitorUuid?: string;
  status?: string;
  collectorType?: string;
  limit?: number;
  offset?: number;
};
