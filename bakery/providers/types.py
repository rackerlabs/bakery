"""Strict provider runtime contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ProviderAction = Literal["create", "update", "comment", "close", "search"]
ProviderBootstrapStatus = Literal["ready", "initializing", "failed"]
ProviderHealthStatus = Literal["unknown", "configured", "healthy", "degraded", "unhealthy"]


class _StrictProviderModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ProviderExecutionContext(_StrictProviderModel):
    """Validated request contract from Bakery's worker into a provider."""

    provider_type: str = Field(..., min_length=1, max_length=50)
    action: ProviderAction
    internal_ticket_id: str | None = Field(default=None, max_length=36)
    provider_ticket_id: str | None = Field(default=None, max_length=255)
    request_payload: dict[str, Any] = Field(default_factory=dict)
    normalized_payload: dict[str, Any] | None = None
    dry_run: bool = False

    @field_validator("provider_type")
    @classmethod
    def _normalize_provider_type(cls, value: str) -> str:
        return value.strip().lower()


class ProviderExecutionResult(_StrictProviderModel):
    """Canonical response contract from providers back to Bakery."""

    success: bool
    ticket_id: str | None = Field(default=None, max_length=255)
    data: dict[str, Any] | None = None
    error: str | None = None
    retryable: bool = True
    raw: dict[str, Any] | None = None

    def as_provider_response(self) -> dict[str, Any]:
        """Return the legacy provider response shape stored on operations."""
        payload: dict[str, Any] = {"success": self.success}
        if self.ticket_id is not None:
            payload["ticket_id"] = self.ticket_id
        if self.data is not None:
            payload["data"] = self.data
        if self.error is not None:
            payload["error"] = self.error
        if self.raw is not None:
            payload["raw"] = self.raw
        payload["retryable"] = self.retryable
        return payload


class ProviderHealthResult(_StrictProviderModel):
    """Non-secret provider health and configuration state."""

    provider_type: str = Field(..., min_length=1, max_length=50)
    status: ProviderHealthStatus
    configured: bool = False
    message: str | None = None
    details: dict[str, Any] | None = None

    @field_validator("provider_type")
    @classmethod
    def _normalize_provider_type(cls, value: str) -> str:
        return value.strip().lower()


class ProviderBootstrapResult(_StrictProviderModel):
    """Provider bootstrap/registration status."""

    provider_type: str = Field(..., min_length=1, max_length=50)
    status: ProviderBootstrapStatus
    message: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("provider_type")
    @classmethod
    def _normalize_provider_type(cls, value: str) -> str:
        return value.strip().lower()
