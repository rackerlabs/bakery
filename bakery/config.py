#!/usr/bin/env python3
"""Bakery configuration settings."""

import os
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from shared.env import env_to_bool
from shared.version import resolve_version


def normalize_external_url(value: str) -> str:
    """Normalize a configured external URL for safe equality checks."""
    trimmed = str(value or "").strip()
    if not trimmed:
        return ""
    parsed = urlsplit(trimmed)
    if not parsed.scheme or not parsed.netloc:
        return ""
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))


def external_url_origin(value: str) -> str:
    """Return only the origin portion of a configured external URL."""
    normalized = normalize_external_url(value)
    if not normalized:
        return ""
    parsed = urlsplit(normalized)
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


class Settings:
    """Bakery application settings loaded from environment variables."""

    def __init__(self) -> None:
        """Initialize settings from environment variables."""
        # Application
        self.environment: str = os.getenv("ENVIRONMENT", "production")
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")
        self.api_prefix: str = "/api/v1"
        self.app_version: str = resolve_version("BAKERY_APP_VERSION")
        self.instance_id: str = os.getenv("HOSTNAME", "bakery-0")

        # Database
        self.database_host: str = os.getenv("DATABASE_HOST", "bakery-mariadb")
        self.database_port: int = int(os.getenv("DATABASE_PORT", "3306"))
        self.database_user: str = os.getenv("DATABASE_USER", "bakery")
        self.database_password: str = os.getenv("DATABASE_PASSWORD", "")
        self.database_name: str = os.getenv("DATABASE_NAME", "bakery")

        # Message queue settings
        self.message_retention_hours: int = int(os.getenv("MESSAGE_RETENTION_HOURS", "24"))
        self.max_messages_per_poll: int = int(os.getenv("MAX_MESSAGES_PER_POLL", "100"))

        # Mixer settings
        self.mixer_timeout_sec: int = int(os.getenv("MIXER_TIMEOUT_SEC", "30"))
        self.mixer_max_retries: int = int(os.getenv("MIXER_MAX_RETRIES", "3"))
        self.ticketing_dry_run: bool = env_to_bool(os.getenv("TICKETING_DRY_RUN"), default=False)
        self.active_provider: str = os.getenv("BAKERY_ACTIVE_PROVIDER", "rackspace_core")

        # Worker settings
        self.worker_poll_interval_sec: int = int(os.getenv("BAKERY_WORKER_POLL_INTERVAL_SEC", "2"))
        self.worker_batch_size: int = int(os.getenv("BAKERY_WORKER_BATCH_SIZE", "10"))
        self.worker_max_attempts: int = int(os.getenv("BAKERY_WORKER_MAX_ATTEMPTS", "5"))
        self.worker_backoff_base_sec: int = int(os.getenv("BAKERY_WORKER_BACKOFF_BASE_SEC", "5"))
        self.worker_backoff_max_sec: int = int(os.getenv("BAKERY_WORKER_BACKOFF_MAX_SEC", "300"))

        # Auth settings
        self.bakery_auth_enabled: bool = env_to_bool(os.getenv("BAKERY_AUTH_ENABLED"), default=True)
        self.bakery_auth_mode: str = os.getenv("BAKERY_AUTH_MODE", "hmac")
        self.bakery_hmac_active_key_id: str = os.getenv("BAKERY_HMAC_ACTIVE_KEY_ID", "")
        self.bakery_hmac_active_key: str = os.getenv("BAKERY_HMAC_ACTIVE_KEY", "")
        self.bakery_hmac_next_key_id: str = os.getenv("BAKERY_HMAC_NEXT_KEY_ID", "")
        self.bakery_hmac_next_key: str = os.getenv("BAKERY_HMAC_NEXT_KEY", "")
        self.bakery_hmac_timestamp_skew_sec: int = int(
            os.getenv("BAKERY_HMAC_TIMESTAMP_SKEW_SEC", "300")
        )
        self.bakery_admin_hmac_active_key_id: str = os.getenv(
            "BAKERY_ADMIN_HMAC_ACTIVE_KEY_ID",
            self.bakery_hmac_active_key_id,
        )
        self.bakery_admin_hmac_active_key: str = os.getenv(
            "BAKERY_ADMIN_HMAC_ACTIVE_KEY",
            self.bakery_hmac_active_key,
        )
        self.bakery_admin_hmac_next_key_id: str = os.getenv(
            "BAKERY_ADMIN_HMAC_NEXT_KEY_ID",
            self.bakery_hmac_next_key_id,
        )
        self.bakery_admin_hmac_next_key: str = os.getenv(
            "BAKERY_ADMIN_HMAC_NEXT_KEY",
            self.bakery_hmac_next_key,
        )
        self.bakery_secret_encryption_key: str = os.getenv("BAKERY_SECRET_ENCRYPTION_KEY", "")
        self.bakery_monitor_default_key_id: str = os.getenv(
            "BAKERY_MONITOR_DEFAULT_KEY_ID",
            "active",
        )
        self.bakery_monitor_bootstrap_key_id: str = os.getenv(
            "BAKERY_MONITOR_BOOTSTRAP_KEY_ID",
            "bootstrap",
        )
        self.bakery_monitor_heartbeat_interval_sec: int = int(
            os.getenv("BAKERY_MONITOR_HEARTBEAT_INTERVAL_SEC", "30")
        )
        self.bakery_monitor_miss_threshold: int = int(
            os.getenv("BAKERY_MONITOR_MISS_THRESHOLD", "5")
        )
        self.bakery_monitor_sweep_interval_sec: int = int(
            os.getenv("BAKERY_MONITOR_SWEEP_INTERVAL_SEC", "5")
        )
        self.bakery_collection_job_lease_sec: int = int(
            os.getenv("BAKERY_COLLECTION_JOB_LEASE_SEC", "300")
        )
        self.bakery_collection_sweep_interval_sec: int = int(
            os.getenv("BAKERY_COLLECTION_SWEEP_INTERVAL_SEC", "5")
        )

        # Operator auth settings
        self.operator_auth_enabled: bool = env_to_bool(
            os.getenv("BAKERY_OPERATOR_AUTH_ENABLED"), default=True
        )
        self.operator_auth_session_timeout: int = int(
            os.getenv("BAKERY_OPERATOR_AUTH_SESSION_TIMEOUT", "86400")
        )
        self.operator_auth_oidc_state_ttl: int = int(
            os.getenv("BAKERY_OPERATOR_AUTH_OIDC_STATE_TTL", "600")
        )
        self.operator_auth_rbac_enabled: bool = env_to_bool(
            os.getenv("BAKERY_OPERATOR_AUTH_RBAC_ENABLED"), default=True
        )
        self.operator_auth_service_token: str = os.getenv("BAKERY_OPERATOR_AUTH_SERVICE_TOKEN", "")
        self.ui_public_url: str = os.getenv("BAKERY_UI_PUBLIC_URL", "").strip()

        self.operator_auth_local_enabled: bool = env_to_bool(
            os.getenv("BAKERY_OPERATOR_AUTH_LOCAL_ENABLED"), default=True
        )
        self.operator_auth_username: str = os.getenv("BAKERY_OPERATOR_AUTH_USERNAME", "")
        self.operator_auth_password: str = os.getenv("BAKERY_OPERATOR_AUTH_PASSWORD", "")
        self.operator_auth_dev_username: str = os.getenv("BAKERY_OPERATOR_AUTH_DEV_USERNAME", "")
        self.operator_auth_dev_password: str = os.getenv("BAKERY_OPERATOR_AUTH_DEV_PASSWORD", "")

        self.operator_auth_auth0_enabled: bool = env_to_bool(
            os.getenv("BAKERY_OPERATOR_AUTH_AUTH0_ENABLED"), default=False
        )
        self.operator_auth_auth0_domain: str = os.getenv("BAKERY_OPERATOR_AUTH_AUTH0_DOMAIN", "")
        self.operator_auth_auth0_audience: str = os.getenv(
            "BAKERY_OPERATOR_AUTH_AUTH0_AUDIENCE", ""
        )
        self.operator_auth_auth0_scope: str = os.getenv(
            "BAKERY_OPERATOR_AUTH_AUTH0_SCOPE", "openid profile email"
        )
        self.operator_auth_auth0_organization: str = os.getenv(
            "BAKERY_OPERATOR_AUTH_AUTH0_ORGANIZATION", ""
        )
        self.operator_auth_auth0_connection: str = os.getenv(
            "BAKERY_OPERATOR_AUTH_AUTH0_CONNECTION", ""
        )
        self.operator_auth_auth0_username_claim: str = os.getenv(
            "BAKERY_OPERATOR_AUTH_AUTH0_USERNAME_CLAIM", "email"
        )
        self.operator_auth_auth0_display_name_claim: str = os.getenv(
            "BAKERY_OPERATOR_AUTH_AUTH0_DISPLAY_NAME_CLAIM", "name"
        )
        self.operator_auth_auth0_groups_claim: str = os.getenv(
            "BAKERY_OPERATOR_AUTH_AUTH0_GROUPS_CLAIM", "groups"
        )
        self.operator_auth_auth0_subject_claim: str = os.getenv(
            "BAKERY_OPERATOR_AUTH_AUTH0_SUBJECT_CLAIM", "sub"
        )
        self.operator_auth_auth0_ui_enabled: bool = env_to_bool(
            os.getenv("BAKERY_OPERATOR_AUTH_AUTH0_UI_ENABLED"),
            default=bool(os.getenv("BAKERY_OPERATOR_AUTH_AUTH0_UI_CLIENT_ID", "")),
        )
        self.operator_auth_auth0_ui_client_id: str = os.getenv(
            "BAKERY_OPERATOR_AUTH_AUTH0_UI_CLIENT_ID", ""
        )
        self.operator_auth_auth0_ui_client_secret: str = os.getenv(
            "BAKERY_OPERATOR_AUTH_AUTH0_UI_CLIENT_SECRET", ""
        )
        self.operator_auth_auth0_ui_callback_url: str = os.getenv(
            "BAKERY_OPERATOR_AUTH_AUTH0_UI_CALLBACK_URL", ""
        )
        self.operator_auth_auth0_cli_enabled: bool = env_to_bool(
            os.getenv("BAKERY_OPERATOR_AUTH_AUTH0_CLI_ENABLED"),
            default=bool(os.getenv("BAKERY_OPERATOR_AUTH_AUTH0_CLI_CLIENT_ID", "")),
        )
        self.operator_auth_auth0_cli_client_id: str = os.getenv(
            "BAKERY_OPERATOR_AUTH_AUTH0_CLI_CLIENT_ID", ""
        )
        self.operator_auth_auth0_cli_client_secret: str = os.getenv(
            "BAKERY_OPERATOR_AUTH_AUTH0_CLI_CLIENT_SECRET", ""
        )

        self.operator_auth_azure_ad_enabled: bool = env_to_bool(
            os.getenv("BAKERY_OPERATOR_AUTH_AZURE_AD_ENABLED"), default=False
        )
        self.operator_auth_azure_ad_tenant: str = os.getenv(
            "BAKERY_OPERATOR_AUTH_AZURE_AD_TENANT", ""
        )
        self.operator_auth_azure_ad_audience: str = os.getenv(
            "BAKERY_OPERATOR_AUTH_AZURE_AD_AUDIENCE", ""
        )
        self.operator_auth_azure_ad_scope: str = os.getenv(
            "BAKERY_OPERATOR_AUTH_AZURE_AD_SCOPE", "openid profile email"
        )
        self.operator_auth_azure_ad_username_claim: str = os.getenv(
            "BAKERY_OPERATOR_AUTH_AZURE_AD_USERNAME_CLAIM", "preferred_username"
        )
        self.operator_auth_azure_ad_display_name_claim: str = os.getenv(
            "BAKERY_OPERATOR_AUTH_AZURE_AD_DISPLAY_NAME_CLAIM", "name"
        )
        self.operator_auth_azure_ad_groups_claim: str = os.getenv(
            "BAKERY_OPERATOR_AUTH_AZURE_AD_GROUPS_CLAIM", "groups"
        )
        self.operator_auth_azure_ad_subject_claim: str = os.getenv(
            "BAKERY_OPERATOR_AUTH_AZURE_AD_SUBJECT_CLAIM", "sub"
        )
        self.operator_auth_azure_ad_ui_enabled: bool = env_to_bool(
            os.getenv("BAKERY_OPERATOR_AUTH_AZURE_AD_UI_ENABLED"),
            default=bool(os.getenv("BAKERY_OPERATOR_AUTH_AZURE_AD_UI_CLIENT_ID", "")),
        )
        self.operator_auth_azure_ad_ui_client_id: str = os.getenv(
            "BAKERY_OPERATOR_AUTH_AZURE_AD_UI_CLIENT_ID", ""
        )
        self.operator_auth_azure_ad_ui_client_secret: str = os.getenv(
            "BAKERY_OPERATOR_AUTH_AZURE_AD_UI_CLIENT_SECRET", ""
        )
        self.operator_auth_azure_ad_ui_callback_url: str = os.getenv(
            "BAKERY_OPERATOR_AUTH_AZURE_AD_UI_CALLBACK_URL", ""
        )
        self.operator_auth_azure_ad_cli_enabled: bool = env_to_bool(
            os.getenv("BAKERY_OPERATOR_AUTH_AZURE_AD_CLI_ENABLED"),
            default=bool(os.getenv("BAKERY_OPERATOR_AUTH_AZURE_AD_CLI_CLIENT_ID", "")),
        )
        self.operator_auth_azure_ad_cli_client_id: str = os.getenv(
            "BAKERY_OPERATOR_AUTH_AZURE_AD_CLI_CLIENT_ID", ""
        )

        # ServiceNow
        self.servicenow_url: Optional[str] = os.getenv("SERVICENOW_URL")
        self.servicenow_username: Optional[str] = os.getenv("SERVICENOW_USERNAME")
        self.servicenow_password: Optional[str] = os.getenv("SERVICENOW_PASSWORD")

        # Jira
        self.jira_url: Optional[str] = os.getenv("JIRA_URL")
        self.jira_username: Optional[str] = os.getenv("JIRA_USERNAME")
        self.jira_api_token: Optional[str] = os.getenv("JIRA_API_TOKEN")

        # GitHub
        self.github_token: Optional[str] = os.getenv("GITHUB_TOKEN")

        # PagerDuty
        self.pagerduty_api_key: Optional[str] = os.getenv("PAGERDUTY_API_KEY")

        # Teams / Discord
        self.teams_webhook_url: Optional[str] = os.getenv("TEAMS_WEBHOOK_URL")
        self.discord_webhook_url: Optional[str] = os.getenv("DISCORD_WEBHOOK_URL")

        # Rackspace Core
        self.rackspace_core_url: Optional[str] = os.getenv("RACKSPACE_CORE_URL", "")
        self.rackspace_core_username: Optional[str] = os.getenv("RACKSPACE_CORE_USERNAME")
        self.rackspace_core_password: Optional[str] = os.getenv("RACKSPACE_CORE_PASSWORD")
        self.rackspace_core_verify_ssl: bool = env_to_bool(
            os.getenv("RACKSPACE_CORE_VERIFY_SSL"), default=True
        )
        self.rackspace_core_default_queue: str = os.getenv("RACKSPACE_CORE_DEFAULT_QUEUE", "")
        self.rackspace_core_default_subcategory: str = os.getenv(
            "RACKSPACE_CORE_DEFAULT_SUBCATEGORY", "Monitoring"
        )
        self.bakery_rackspace_confirmed_solved_status: str = os.getenv(
            "BAKERY_RACKSPACE_CONFIRMED_SOLVED_STATUS", "confirmed solved"
        )

    @property
    def database_url(self) -> str:
        """Construct database URL for SQLAlchemy."""
        return (
            f"mysql+pymysql://{self.database_user}:{self.database_password}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
        )

    @property
    def ui_public_origin(self) -> str:
        """Return the configured UI origin for credentialed CORS."""
        return external_url_origin(self.ui_public_url)


# Global settings instance
settings = Settings()
