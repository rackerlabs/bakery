"""Monitor registry and heartbeat tables

Revision ID: 002
Revises: 001
Create Date: 2026-03-31 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("monitor_uuid", sa.String(length=36), nullable=True))
    op.create_index("ix_tickets_monitor_uuid", "tickets", ["monitor_uuid"], unique=False)

    op.create_table(
        "monitor_bootstrap_credentials",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("monitor_id", sa.String(length=255), nullable=False),
        sa.Column("key_id", sa.String(length=64), nullable=False),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "monitor_id",
            name="uq_monitor_bootstrap_credentials_monitor_id",
        ),
    )
    op.create_index(
        "ix_monitor_bootstrap_credentials_id",
        "monitor_bootstrap_credentials",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_monitor_bootstrap_credentials_monitor_id",
        "monitor_bootstrap_credentials",
        ["monitor_id"],
        unique=False,
    )

    op.create_table(
        "monitors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("monitor_uuid", sa.String(length=36), nullable=False),
        sa.Column("monitor_id", sa.String(length=255), nullable=False),
        sa.Column("key_id", sa.String(length=64), nullable=False),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("route_catalog_hash", sa.String(length=64), nullable=True),
        sa.Column("route_sync_required", sa.Boolean(), nullable=False),
        sa.Column("last_checkin_at", sa.DateTime(), nullable=True),
        sa.Column("unreachable_at", sa.DateTime(), nullable=True),
        sa.Column("last_seen_payload", mysql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("monitor_uuid", name="uq_monitors_monitor_uuid"),
        sa.UniqueConstraint("monitor_id", name="uq_monitors_monitor_id"),
    )
    for index_name, columns in (
        ("ix_monitors_id", ["id"]),
        ("ix_monitors_monitor_uuid", ["monitor_uuid"]),
        ("ix_monitors_monitor_id", ["monitor_id"]),
        ("ix_monitors_status", ["status"]),
        ("ix_monitors_last_checkin_at", ["last_checkin_at"]),
    ):
        op.create_index(index_name, "monitors", columns, unique=False)

    op.create_table(
        "monitor_route_catalog_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("monitor_uuid", sa.String(length=36), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("owner_key", sa.String(length=255), nullable=False),
        sa.Column("route_id", sa.String(length=255), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("execution_target", sa.String(length=100), nullable=False),
        sa.Column("destination_target", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("provider_config", mysql.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("outage_enabled", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "monitor_uuid",
            "scope",
            "owner_key",
            "route_id",
            name="uq_monitor_route_catalog_entries_monitor_route",
        ),
    )
    for index_name, columns in (
        ("ix_monitor_route_catalog_entries_id", ["id"]),
        ("ix_monitor_route_catalog_entries_monitor_uuid", ["monitor_uuid"]),
        ("ix_monitor_route_catalog_entries_scope", ["scope"]),
        ("ix_monitor_route_catalog_entries_owner_key", ["owner_key"]),
        ("ix_monitor_route_catalog_entries_route_id", ["route_id"]),
        ("ix_monitor_route_catalog_entries_execution_target", ["execution_target"]),
    ):
        op.create_index(index_name, "monitor_route_catalog_entries", columns, unique=False)

    op.create_table(
        "monitor_outage_route_states",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("monitor_uuid", sa.String(length=36), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("owner_key", sa.String(length=255), nullable=False),
        sa.Column("route_id", sa.String(length=255), nullable=False),
        sa.Column("ticket_id", sa.String(length=36), nullable=True),
        sa.Column("last_state", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "monitor_uuid",
            "scope",
            "owner_key",
            "route_id",
            name="uq_monitor_outage_route_states_monitor_route",
        ),
    )
    for index_name, columns in (
        ("ix_monitor_outage_route_states_id", ["id"]),
        ("ix_monitor_outage_route_states_monitor_uuid", ["monitor_uuid"]),
        ("ix_monitor_outage_route_states_scope", ["scope"]),
        ("ix_monitor_outage_route_states_owner_key", ["owner_key"]),
        ("ix_monitor_outage_route_states_route_id", ["route_id"]),
        ("ix_monitor_outage_route_states_ticket_id", ["ticket_id"]),
    ):
        op.create_index(index_name, "monitor_outage_route_states", columns, unique=False)

    op.create_table(
        "monitor_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("monitor_uuid", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", mysql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for index_name, columns in (
        ("ix_monitor_events_id", ["id"]),
        ("ix_monitor_events_monitor_uuid", ["monitor_uuid"]),
        ("ix_monitor_events_event_type", ["event_type"]),
        ("ix_monitor_events_created_at", ["created_at"]),
    ):
        op.create_index(index_name, "monitor_events", columns, unique=False)


def downgrade() -> None:
    for index_name in (
        "ix_monitor_events_created_at",
        "ix_monitor_events_event_type",
        "ix_monitor_events_monitor_uuid",
        "ix_monitor_events_id",
    ):
        op.drop_index(index_name, table_name="monitor_events")
    op.drop_table("monitor_events")

    for index_name in (
        "ix_monitor_outage_route_states_ticket_id",
        "ix_monitor_outage_route_states_route_id",
        "ix_monitor_outage_route_states_owner_key",
        "ix_monitor_outage_route_states_scope",
        "ix_monitor_outage_route_states_monitor_uuid",
        "ix_monitor_outage_route_states_id",
    ):
        op.drop_index(index_name, table_name="monitor_outage_route_states")
    op.drop_table("monitor_outage_route_states")

    for index_name in (
        "ix_monitor_route_catalog_entries_execution_target",
        "ix_monitor_route_catalog_entries_route_id",
        "ix_monitor_route_catalog_entries_owner_key",
        "ix_monitor_route_catalog_entries_scope",
        "ix_monitor_route_catalog_entries_monitor_uuid",
        "ix_monitor_route_catalog_entries_id",
    ):
        op.drop_index(index_name, table_name="monitor_route_catalog_entries")
    op.drop_table("monitor_route_catalog_entries")

    for index_name in (
        "ix_monitors_last_checkin_at",
        "ix_monitors_status",
        "ix_monitors_monitor_id",
        "ix_monitors_monitor_uuid",
        "ix_monitors_id",
    ):
        op.drop_index(index_name, table_name="monitors")
    op.drop_table("monitors")

    op.drop_index(
        "ix_monitor_bootstrap_credentials_monitor_id",
        table_name="monitor_bootstrap_credentials",
    )
    op.drop_index("ix_monitor_bootstrap_credentials_id", table_name="monitor_bootstrap_credentials")
    op.drop_table("monitor_bootstrap_credentials")

    op.drop_index("ix_tickets_monitor_uuid", table_name="tickets")
    op.drop_column("tickets", "monitor_uuid")
