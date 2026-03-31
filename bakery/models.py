#!/usr/bin/env python3
"""Database models for Bakery."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from bakery.database import Base


class Message(Base):
    """Message queue table for responses from ticketing systems."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    correlation_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="Links to original request"
    )
    ticket_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        comment="Bakery internal ticket UUID exposed to PoundCake API",
    )
    mixer_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="servicenow, jira, github, pagerduty, rackspace_core, teams, discord",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        comment="pending, success, error",
    )
    response_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="Full response from mixer"
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Error details if failed"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="When message was created",
    )
    retrieved_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="When message was retrieved by API"
    )


class TicketRequest(Base):
    """Log of all ticket requests processed by Bakery."""

    __tablename__ = "ticket_requests"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    correlation_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="Unique request identifier"
    )
    mixer_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="servicenow, jira, github, pagerduty, rackspace_core, teams, discord",
    )
    action: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="create, update, close, comment, etc"
    )
    request_data: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, comment="Original request payload"
    )
    ticket_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Bakery internal ticket UUID if mapped"
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        comment="pending, processing, success, error",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class MixerConfig(Base):
    """Optional table for storing mixer-specific configuration."""

    __tablename__ = "mixer_configs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    mixer_type: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, comment="Mixer identifier"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    config_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="Mixer-specific settings"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class TicketIdMapping(Base):
    """Stable ID mapping between Bakery internal UUIDs and external ticket IDs."""

    __tablename__ = "ticket_id_mappings"
    __table_args__ = (
        UniqueConstraint("internal_ticket_id", name="uq_ticket_id_mappings_internal_ticket_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    internal_ticket_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
        comment="Bakery-generated UUID exposed to PoundCake API",
    )
    mixer_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="servicenow, jira, github, pagerduty, rackspace_core, teams, discord",
    )
    external_ticket_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Native ticket/incident/issue ID from external system",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="When mapping was created",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        comment="When mapping was last updated",
    )


class Ticket(Base):
    """Logical ticket exposed to PoundCake via Bakery UUID."""

    __tablename__ = "tickets"
    __table_args__ = (UniqueConstraint("internal_ticket_id", name="uq_tickets_internal_ticket_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    internal_ticket_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
        comment="Bakery ticket UUID exposed externally",
    )
    provider_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    provider_ticket_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    monitor_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    state: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="queued",
        index=True,
        comment="queued, open, updating, closing, closed, error",
    )
    latest_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class TicketOperation(Base):
    """Asynchronous operation queue for ticket actions."""

    __tablename__ = "ticket_operations"
    __table_args__ = (UniqueConstraint("operation_id", name="uq_ticket_operations_operation_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    operation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    internal_ticket_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tickets.internal_ticket_id"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="queued",
        index=True,
        comment="queued, running, succeeded, failed, dead_letter",
    )
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    normalized_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    provider_response: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(default=5, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class IdempotencyKey(Base):
    """Idempotency records for replay-safe API behavior."""

    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            "action",
            "ticket_scope",
            name="uq_idempotency_keys_key_action_scope",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    ticket_scope: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="global",
        index=True,
        comment="global for create, internal_ticket_id for ticket-scoped actions",
    )
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    operation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class MonitorBootstrapCredential(Base):
    """Bootstrap credential used for first-time PoundCake monitor registration."""

    __tablename__ = "monitor_bootstrap_credentials"
    __table_args__ = (
        UniqueConstraint("monitor_id", name="uq_monitor_bootstrap_credentials_monitor_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    monitor_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    key_id: Mapped[str] = mapped_column(String(64), nullable=False)
    encrypted_secret: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Monitor(Base):
    """Registered PoundCake monitor identity and liveness state."""

    __tablename__ = "monitors"
    __table_args__ = (
        UniqueConstraint("monitor_uuid", name="uq_monitors_monitor_uuid"),
        UniqueConstraint("monitor_id", name="uq_monitors_monitor_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    monitor_uuid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    monitor_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    key_id: Mapped[str] = mapped_column(String(64), nullable=False)
    encrypted_secret: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="healthy", index=True)
    route_catalog_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    route_sync_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    environment_label: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    cluster_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    namespace: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    release_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    tags_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    last_checkin_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    unreachable_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class MonitorRouteCatalogEntry(Base):
    """Registered PoundCake route catalog entry."""

    __tablename__ = "monitor_route_catalog_entries"
    __table_args__ = (
        UniqueConstraint(
            "monitor_uuid",
            "scope",
            "owner_key",
            "route_id",
            name="uq_monitor_route_catalog_entries_monitor_route",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    monitor_uuid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    owner_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    route_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    execution_target: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    provider_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    destination_target: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    account_number: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    queue: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    subcategory: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    provider_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    outage_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class MonitorOutageRouteState(Base):
    """Tracks the reused outage communication for one monitor route."""

    __tablename__ = "monitor_outage_route_states"
    __table_args__ = (
        UniqueConstraint(
            "monitor_uuid",
            "scope",
            "owner_key",
            "route_id",
            name="uq_monitor_outage_route_states_monitor_route",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    monitor_uuid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    owner_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    route_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    ticket_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    last_state: Mapped[str] = mapped_column(String(32), nullable=False, default="healthy")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class MonitorEvent(Base):
    """Audit trail of registration, route sync, and reachability transitions."""

    __tablename__ = "monitor_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    monitor_uuid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )


class AuthPrincipal(Base):
    """Observed human principal used for Bakery RBAC bindings."""

    __tablename__ = "auth_principals"
    __table_args__ = (
        UniqueConstraint("provider", "subject_id", name="uq_auth_principals_provider_subject"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subject_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    principal_type: Mapped[str] = mapped_column(String(32), nullable=False, default="user")
    groups_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class AuthRoleBinding(Base):
    """RBAC binding matching a user or group to a Bakery role."""

    __tablename__ = "auth_role_bindings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    binding_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    principal_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_principals.id"),
        nullable=True,
        index=True,
    )
    external_group: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class AuthSession(Base):
    """Browser or CLI session persisted in Bakery MariaDB."""

    __tablename__ = "auth_sessions"
    __table_args__ = (UniqueConstraint("session_id", name="uq_auth_sessions_session_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subject_id: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    principal_type: Mapped[str] = mapped_column(String(32), nullable=False, default="user")
    principal_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    groups_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    permissions_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class AuthState(Base):
    """Short-lived OIDC state stored in MariaDB for Bakery operator auth."""

    __tablename__ = "auth_state"
    __table_args__ = (UniqueConstraint("kind", "state_key", name="uq_auth_state_kind_key"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    state_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class CollectionJob(Base):
    """Queued, leased, or completed read-only collection job for a PoundCake monitor."""

    __tablename__ = "collection_jobs"
    __table_args__ = (UniqueConstraint("job_id", name="uq_collection_jobs_job_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    monitor_uuid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    monitor_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    collector_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
