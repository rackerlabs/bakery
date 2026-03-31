"""Operator control plane tables and reporting dimensions

Revision ID: 003
Revises: 002
Create Date: 2026-03-31 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("monitors", sa.Column("environment_label", sa.String(length=255), nullable=True))
    op.add_column("monitors", sa.Column("region", sa.String(length=100), nullable=True))
    op.add_column("monitors", sa.Column("cluster_name", sa.String(length=255), nullable=True))
    op.add_column("monitors", sa.Column("namespace", sa.String(length=255), nullable=True))
    op.add_column("monitors", sa.Column("release_name", sa.String(length=255), nullable=True))
    op.add_column(
        "monitors",
        sa.Column(
            "tags_json",
            mysql.JSON(),
            nullable=True,
        ),
    )
    op.execute("UPDATE monitors SET tags_json = '[]' WHERE tags_json IS NULL")
    op.alter_column("monitors", "tags_json", existing_type=mysql.JSON(), nullable=False)
    op.create_index("ix_monitors_environment_label", "monitors", ["environment_label"], unique=False)
    op.create_index("ix_monitors_region", "monitors", ["region"], unique=False)
    op.create_index("ix_monitors_cluster_name", "monitors", ["cluster_name"], unique=False)
    op.create_index("ix_monitors_namespace", "monitors", ["namespace"], unique=False)
    op.create_index("ix_monitors_release_name", "monitors", ["release_name"], unique=False)

    op.add_column(
        "monitor_route_catalog_entries",
        sa.Column("provider_type", sa.String(length=100), nullable=False, server_default=""),
    )
    op.add_column(
        "monitor_route_catalog_entries",
        sa.Column("account_number", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "monitor_route_catalog_entries",
        sa.Column("queue", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "monitor_route_catalog_entries",
        sa.Column("subcategory", sa.String(length=255), nullable=True),
    )
    op.execute(
        "UPDATE monitor_route_catalog_entries "
        "SET provider_type = execution_target "
        "WHERE provider_type = '' OR provider_type IS NULL"
    )
    op.create_index(
        "ix_monitor_route_catalog_entries_provider_type",
        "monitor_route_catalog_entries",
        ["provider_type"],
        unique=False,
    )
    op.create_index(
        "ix_monitor_route_catalog_entries_account_number",
        "monitor_route_catalog_entries",
        ["account_number"],
        unique=False,
    )
    op.create_index(
        "ix_monitor_route_catalog_entries_queue",
        "monitor_route_catalog_entries",
        ["queue"],
        unique=False,
    )
    op.create_index(
        "ix_monitor_route_catalog_entries_subcategory",
        "monitor_route_catalog_entries",
        ["subcategory"],
        unique=False,
    )

    op.create_table(
        "auth_principals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("subject_id", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("principal_type", sa.String(length=32), nullable=False),
        sa.Column("groups_json", mysql.JSON(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "subject_id", name="uq_auth_principals_provider_subject"),
    )
    for index_name, columns in (
        ("ix_auth_principals_id", ["id"]),
        ("ix_auth_principals_provider", ["provider"]),
        ("ix_auth_principals_subject_id", ["subject_id"]),
        ("ix_auth_principals_username", ["username"]),
        ("ix_auth_principals_last_seen_at", ["last_seen_at"]),
    ):
        op.create_index(index_name, "auth_principals", columns, unique=False)

    op.create_table(
        "auth_role_bindings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("binding_type", sa.String(length=32), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("principal_id", sa.Integer(), nullable=True),
        sa.Column("external_group", sa.String(length=255), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["principal_id"], ["auth_principals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for index_name, columns in (
        ("ix_auth_role_bindings_id", ["id"]),
        ("ix_auth_role_bindings_provider", ["provider"]),
        ("ix_auth_role_bindings_binding_type", ["binding_type"]),
        ("ix_auth_role_bindings_role", ["role"]),
        ("ix_auth_role_bindings_principal_id", ["principal_id"]),
        ("ix_auth_role_bindings_external_group", ["external_group"]),
    ):
        op.create_index(index_name, "auth_role_bindings", columns, unique=False)

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("subject_id", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("principal_type", sa.String(length=32), nullable=False),
        sa.Column("principal_id", sa.Integer(), nullable=True),
        sa.Column("is_superuser", sa.Boolean(), nullable=False),
        sa.Column("groups_json", mysql.JSON(), nullable=False),
        sa.Column("permissions_json", mysql.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_auth_sessions_session_id"),
    )
    for index_name, columns in (
        ("ix_auth_sessions_id", ["id"]),
        ("ix_auth_sessions_session_id", ["session_id"]),
        ("ix_auth_sessions_provider", ["provider"]),
        ("ix_auth_sessions_username", ["username"]),
        ("ix_auth_sessions_role", ["role"]),
        ("ix_auth_sessions_principal_id", ["principal_id"]),
        ("ix_auth_sessions_expires_at", ["expires_at"]),
    ):
        op.create_index(index_name, "auth_sessions", columns, unique=False)

    op.create_table(
        "auth_state",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("state_key", sa.String(length=255), nullable=False),
        sa.Column("payload_json", mysql.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "state_key", name="uq_auth_state_kind_key"),
    )
    for index_name, columns in (
        ("ix_auth_state_id", ["id"]),
        ("ix_auth_state_kind", ["kind"]),
        ("ix_auth_state_state_key", ["state_key"]),
        ("ix_auth_state_expires_at", ["expires_at"]),
    ):
        op.create_index(index_name, "auth_state", columns, unique=False)

    op.create_table(
        "collection_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("monitor_uuid", sa.String(length=36), nullable=False),
        sa.Column("monitor_id", sa.String(length=255), nullable=False),
        sa.Column("collector_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("parameters", mysql.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.String(length=255), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("result", mysql.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", name="uq_collection_jobs_job_id"),
    )
    for index_name, columns in (
        ("ix_collection_jobs_id", ["id"]),
        ("ix_collection_jobs_job_id", ["job_id"]),
        ("ix_collection_jobs_monitor_uuid", ["monitor_uuid"]),
        ("ix_collection_jobs_monitor_id", ["monitor_id"]),
        ("ix_collection_jobs_collector_type", ["collector_type"]),
        ("ix_collection_jobs_status", ["status"]),
        ("ix_collection_jobs_requested_by", ["requested_by"]),
        ("ix_collection_jobs_lease_expires_at", ["lease_expires_at"]),
        ("ix_collection_jobs_created_at", ["created_at"]),
    ):
        op.create_index(index_name, "collection_jobs", columns, unique=False)


def downgrade() -> None:
    for index_name in (
        "ix_collection_jobs_created_at",
        "ix_collection_jobs_lease_expires_at",
        "ix_collection_jobs_requested_by",
        "ix_collection_jobs_status",
        "ix_collection_jobs_collector_type",
        "ix_collection_jobs_monitor_id",
        "ix_collection_jobs_monitor_uuid",
        "ix_collection_jobs_job_id",
        "ix_collection_jobs_id",
    ):
        op.drop_index(index_name, table_name="collection_jobs")
    op.drop_table("collection_jobs")

    for index_name in (
        "ix_auth_state_expires_at",
        "ix_auth_state_state_key",
        "ix_auth_state_kind",
        "ix_auth_state_id",
    ):
        op.drop_index(index_name, table_name="auth_state")
    op.drop_table("auth_state")

    for index_name in (
        "ix_auth_sessions_expires_at",
        "ix_auth_sessions_principal_id",
        "ix_auth_sessions_role",
        "ix_auth_sessions_username",
        "ix_auth_sessions_provider",
        "ix_auth_sessions_session_id",
        "ix_auth_sessions_id",
    ):
        op.drop_index(index_name, table_name="auth_sessions")
    op.drop_table("auth_sessions")

    for index_name in (
        "ix_auth_role_bindings_external_group",
        "ix_auth_role_bindings_principal_id",
        "ix_auth_role_bindings_role",
        "ix_auth_role_bindings_binding_type",
        "ix_auth_role_bindings_provider",
        "ix_auth_role_bindings_id",
    ):
        op.drop_index(index_name, table_name="auth_role_bindings")
    op.drop_table("auth_role_bindings")

    for index_name in (
        "ix_auth_principals_last_seen_at",
        "ix_auth_principals_username",
        "ix_auth_principals_subject_id",
        "ix_auth_principals_provider",
        "ix_auth_principals_id",
    ):
        op.drop_index(index_name, table_name="auth_principals")
    op.drop_table("auth_principals")

    for index_name in (
        "ix_monitor_route_catalog_entries_subcategory",
        "ix_monitor_route_catalog_entries_queue",
        "ix_monitor_route_catalog_entries_account_number",
        "ix_monitor_route_catalog_entries_provider_type",
    ):
        op.drop_index(index_name, table_name="monitor_route_catalog_entries")
    op.drop_column("monitor_route_catalog_entries", "subcategory")
    op.drop_column("monitor_route_catalog_entries", "queue")
    op.drop_column("monitor_route_catalog_entries", "account_number")
    op.drop_column("monitor_route_catalog_entries", "provider_type")

    for index_name in (
        "ix_monitors_release_name",
        "ix_monitors_namespace",
        "ix_monitors_cluster_name",
        "ix_monitors_region",
        "ix_monitors_environment_label",
    ):
        op.drop_index(index_name, table_name="monitors")
    op.drop_column("monitors", "tags_json")
    op.drop_column("monitors", "release_name")
    op.drop_column("monitors", "namespace")
    op.drop_column("monitors", "cluster_name")
    op.drop_column("monitors", "region")
    op.drop_column("monitors", "environment_label")
