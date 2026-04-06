#!/usr/bin/env python3
"""Pydantic schemas for Bakery API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel as PydanticBaseModel, ConfigDict, Field
from shared.bakery_contract import (
    CollectionJobClaimResponse,
    CollectionJobCompleteRequest,
    CollectionJobCreateRequest,
    CollectionJobResponse,
    CommunicationAcceptedResponse,
    CommunicationCloseRequest,
    CommunicationNotifyRequest,
    CommunicationOpenRequest,
    CommunicationOperationListResponse,
    CommunicationOperationResponse,
    CommunicationResponse,
    CommunicationUpdateRequest,
    MonitorBootstrapCredentialResponse,
    MonitorHeartbeatRequest,
    MonitorHeartbeatResponse,
    MonitorMetadata,
    MonitorRegistrationRequest,
    MonitorRegistrationResponse,
    MonitorRouteCatalogEntry,
    MonitorRouteCatalogSyncRequest,
    MonitorRouteCatalogSyncResponse,
)

__all__ = [
    "CommunicationAcceptedResponse",
    "CommunicationCloseRequest",
    "CollectionCollectorFieldResponse",
    "CollectionCollectorResponse",
    "CollectionJobClaimResponse",
    "CollectionJobCompleteRequest",
    "CollectionJobCreateRequest",
    "CollectionJobResponse",
    "CommunicationNotifyRequest",
    "CommunicationOpenRequest",
    "CommunicationOperationListResponse",
    "CommunicationOperationResponse",
    "CommunicationResponse",
    "CommunicationUpdateRequest",
    "MonitorBootstrapCredentialResponse",
    "MonitorDetailResponse",
    "MonitorFilterOptionResponse",
    "MonitorHeartbeatRequest",
    "MonitorHeartbeatResponse",
    "MonitorMetadata",
    "MonitorRegistrationRequest",
    "MonitorRegistrationResponse",
    "MonitorRouteCatalogEntry",
    "MonitorRouteCatalogSyncRequest",
    "MonitorRouteCatalogSyncResponse",
    "ReportFilterOptionsResponse",
]


class BaseModel(PydanticBaseModel):
    """Strict base model for Bakery-owned DTOs."""

    model_config = ConfigDict(extra="forbid")


class TicketCreateRequest(BaseModel):
    """Create a new logical ticket."""

    title: str = Field(..., min_length=1, max_length=512)
    description: str = Field(..., min_length=1)
    message: Optional[str] = Field(default=None, min_length=1)
    severity: Optional[str] = Field(default=None, max_length=50)
    category: Optional[str] = Field(default=None, max_length=100)
    source: Optional[str] = Field(default=None, max_length=100)
    context: Dict[str, Any] = Field(default_factory=dict)


class TicketUpdateRequest(BaseModel):
    """Update mutable ticket fields."""

    title: Optional[str] = Field(default=None, min_length=1, max_length=512)
    description: Optional[str] = Field(default=None, min_length=1)
    severity: Optional[str] = Field(default=None, max_length=50)
    category: Optional[str] = Field(default=None, max_length=100)
    state: Optional[str] = Field(default=None, max_length=50)
    context: Dict[str, Any] = Field(default_factory=dict)


class TicketCommentRequest(BaseModel):
    """Add a comment to a ticket."""

    comment: str = Field(..., min_length=1)
    visibility: Optional[str] = Field(default=None, max_length=50)
    context: Dict[str, Any] = Field(default_factory=dict)


class TicketCloseRequest(BaseModel):
    """Close a ticket."""

    title: Optional[str] = Field(default=None, min_length=1, max_length=512)
    description: Optional[str] = Field(default=None, min_length=1)
    message: Optional[str] = Field(default=None, min_length=1)
    source: Optional[str] = Field(default=None, max_length=100)
    resolution_code: Optional[str] = Field(default=None, max_length=100)
    resolution_notes: Optional[str] = Field(default=None, max_length=4096)
    state: Optional[str] = Field(default="closed", max_length=50)
    context: Dict[str, Any] = Field(default_factory=dict)


class OperationAcceptedResponse(BaseModel):
    """Accepted async operation response."""

    ticket_id: str
    operation_id: str
    action: str
    status: str
    created_at: datetime


class TicketResponse(BaseModel):
    """Logical ticket status."""

    ticket_id: str
    provider_type: str
    provider_ticket_id: Optional[str] = None
    state: str
    latest_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    data_source: str = "local_cache"
    ticket_data: Optional[Dict[str, Any]] = None
    last_sync_operation_id: Optional[str] = None
    last_sync_at: Optional[datetime] = None


class TicketOperationResponse(BaseModel):
    """Detailed ticket operation state."""

    operation_id: str
    ticket_id: str
    action: str
    status: str
    attempt_count: int
    max_attempts: int
    next_attempt_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_error: Optional[str] = None
    provider_response: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class TicketOperationListResponse(BaseModel):
    """List of operations for a ticket."""

    ticket_id: str
    operations: List[TicketOperationResponse]
    count: int


class ComponentHealth(BaseModel):
    """Health status of a single component."""

    status: str = Field(..., description="healthy, degraded, unhealthy")
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., description="Overall system health status")
    version: str = Field(..., description="Bakery version")
    instance_id: str = Field(..., description="Unique instance identifier")
    timestamp: datetime = Field(..., description="Health check timestamp")
    components: Dict[str, ComponentHealth] = Field(
        ..., description="Health status of individual components"
    )


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str
    detail: Optional[str] = None


class MixerInfo(BaseModel):
    """Information about a single mixer."""

    mixer_type: str = Field(..., description="Mixer identifier")
    actions: List[str] = Field(..., description="Supported actions for this mixer")
    configured: bool = Field(
        ..., description="Whether credentials are configured (not necessarily valid)"
    )


class MixerListResponse(BaseModel):
    """Response for listing available mixers."""

    mixers: List[MixerInfo]
    count: int = Field(..., description="Number of registered mixers")


class MixerValidateResponse(BaseModel):
    """Response for mixer credential validation."""

    mixer_type: str = Field(..., description="Mixer that was validated")
    valid: bool = Field(..., description="Whether credentials are valid and connectivity works")
    message: str = Field(..., description="Human-readable validation result")


class SessionResponse(BaseModel):
    """Response returned after Bakery operator login."""

    session_id: str
    username: str
    expires_at: str
    provider: str
    role: str
    display_name: str | None = None
    is_superuser: bool = False
    permissions: list[str] = Field(default_factory=list)
    token_type: str = "Bearer"


class AuthLoginRequest(BaseModel):
    """Password login request for Bakery operators."""

    provider: str | None = None
    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=255)


class AuthProviderResponse(BaseModel):
    """Enabled Bakery auth provider metadata for UI and CLI discovery."""

    name: str
    label: str
    login_mode: str
    cli_login_mode: str
    browser_login: bool = False
    device_login: bool = False
    password_login: bool = False


class AuthMeResponse(BaseModel):
    """Current authenticated operator context."""

    username: str
    display_name: str | None = None
    provider: str
    role: str
    principal_type: str
    principal_id: int | None = None
    is_superuser: bool = False
    permissions: list[str] = Field(default_factory=list)
    groups: list[str] = Field(default_factory=list)
    expires_at: str | None = None


class AuthLogoutResponse(BaseModel):
    """Logout acknowledgement."""

    message: str


class DeviceAuthorizationStartResponse(BaseModel):
    """Device authorization bootstrap payload."""

    provider: str
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str | None = None
    expires_in: int
    interval: int


class DeviceAuthorizationStartRequest(BaseModel):
    """Device authorization start request."""

    provider: str | None = None


class DeviceAuthorizationPollRequest(BaseModel):
    """Device authorization polling request."""

    provider: str | None = None
    device_code: str = Field(..., min_length=1)


class DeviceAuthorizationPollResponse(BaseModel):
    """Device authorization status response."""

    status: str
    interval: int | None = None
    detail: str | None = None
    session: SessionResponse | None = None


class AuthPrincipalResponse(BaseModel):
    """Observed principal metadata for access binding management."""

    id: int
    provider: str
    subject_id: str
    username: str
    display_name: str | None = None
    principal_type: str
    groups: list[str] = Field(default_factory=list)
    last_seen_at: datetime
    created_at: datetime
    updated_at: datetime


class AuthRoleBindingCreate(BaseModel):
    """Create a new RBAC binding."""

    provider: str
    binding_type: str
    role: str
    principal_id: int | None = None
    external_group: str | None = Field(default=None, max_length=255)
    created_by: str | None = Field(default=None, max_length=255)


class AuthRoleBindingUpdate(BaseModel):
    """Update an existing RBAC binding."""

    role: str | None = None
    external_group: str | None = Field(default=None, max_length=255)


class AuthRoleBindingResponse(BaseModel):
    """RBAC binding record returned to operators."""

    id: int
    provider: str
    binding_type: str
    role: str
    principal_id: int | None = None
    external_group: str | None = None
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
    principal: AuthPrincipalResponse | None = None


class DeleteResponse(BaseModel):
    """Simple delete acknowledgement."""

    message: str


class SettingsResponse(BaseModel):
    """Bakery UI bootstrap settings."""

    auth_enabled: bool
    rbac_enabled: bool
    auth_providers: list[AuthProviderResponse]
    version: str


class ReportOverviewResponse(BaseModel):
    """High-level operational summary for Bakery operators."""

    monitors_total: int
    monitors_healthy: int
    monitors_unreachable: int
    open_tickets: int
    queued_operations: int
    failed_operations: int
    dead_letter_operations: int
    queued_collection_jobs: int
    leased_collection_jobs: int
    timed_out_collection_jobs: int


class MonitorFilterOptionResponse(BaseModel):
    """Compact monitor metadata used by UI pickers and filter UIs."""

    monitor_uuid: str
    monitor_id: str
    status: str
    environment_label: str | None = None
    region: str | None = None
    cluster_name: str | None = None
    namespace: str | None = None
    release_name: str | None = None
    route_sync_required: bool = False
    last_checkin_at: datetime | None = None


class ReportFilterOptionsResponse(BaseModel):
    """Distinct filter options surfaced to the Bakery operator UI."""

    monitors: list[MonitorFilterOptionResponse] = Field(default_factory=list)
    environment_labels: list[str] = Field(default_factory=list)
    provider_types: list[str] = Field(default_factory=list)
    account_numbers: list[str] = Field(default_factory=list)


class MonitorSummaryResponse(BaseModel):
    """Monitor inventory row for reporting and drill-down."""

    monitor_uuid: str
    monitor_id: str
    status: str
    environment_label: str | None = None
    region: str | None = None
    cluster_name: str | None = None
    namespace: str | None = None
    release_name: str | None = None
    tags: list[str] = Field(default_factory=list)
    route_sync_required: bool
    route_count: int = 0
    outage_route_count: int = 0
    last_checkin_at: datetime | None = None
    unreachable_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    last_seen_payload: Dict[str, Any] | None = None


class MonitorEventResponse(BaseModel):
    """Monitor event record."""

    monitor_uuid: str
    event_type: str
    payload: Dict[str, Any] | None = None
    created_at: datetime


class MonitorRouteInventoryResponse(BaseModel):
    """Monitor route inventory row with report-friendly dimensions."""

    monitor_uuid: str
    monitor_id: str
    environment_label: str | None = None
    scope: str
    owner_key: str
    route_id: str
    label: str
    provider_type: str
    execution_target: str
    destination_target: str
    account_number: str | None = None
    queue: str | None = None
    subcategory: str | None = None
    enabled: bool
    outage_enabled: bool
    position: int
    updated_at: datetime


class ProviderAnalyticsResponse(BaseModel):
    """Aggregated provider usage and failure metrics."""

    provider_type: str
    route_count: int
    ticket_count: int
    open_ticket_count: int
    failed_operation_count: int
    dead_letter_count: int


class OperationAnalyticsResponse(BaseModel):
    """Aggregated Bakery operation queue metrics."""

    provider_type: str
    action: str
    status: str
    count: int


class TicketBacklogResponse(BaseModel):
    """Ticket backlog row for open or errored Bakery communications."""

    ticket_id: str
    provider_type: str
    provider_ticket_id: str | None = None
    monitor_uuid: str | None = None
    monitor_id: str | None = None
    environment_label: str | None = None
    state: str
    latest_error: str | None = None
    created_at: datetime
    updated_at: datetime


class CollectionCollectorFieldResponse(BaseModel):
    """One UI field exposed for a collector's parameters."""

    name: str
    label: str
    field_type: str
    description: str
    required: bool = False
    default_value: Any | None = None
    placeholder: str | None = None


class CollectionCollectorResponse(BaseModel):
    """UI-friendly metadata about a supported collection collector."""

    collector_type: str
    label: str
    description: str
    default_parameters: Dict[str, Any] = Field(default_factory=dict)
    example_parameters: Dict[str, Any] = Field(default_factory=dict)
    parameters: list[CollectionCollectorFieldResponse] = Field(default_factory=list)


class MonitorDetailResponse(BaseModel):
    """Drill-down payload for one Bakery monitor."""

    monitor: MonitorSummaryResponse
    recent_events: list[MonitorEventResponse] = Field(default_factory=list)
    recent_routes: list[MonitorRouteInventoryResponse] = Field(default_factory=list)
    recent_jobs: list[CollectionJobResponse] = Field(default_factory=list)
    latest_successful_jobs: list[CollectionJobResponse] = Field(default_factory=list)
    operation_analytics: list[OperationAnalyticsResponse] = Field(default_factory=list)
    backlog: list[TicketBacklogResponse] = Field(default_factory=list)
