#!/usr/bin/env python3
"""Base provider interface for ticketing and messaging systems."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from bakery.providers.base import Provider
from bakery.providers.payloads import (
    build_provider_payload,
    missing_provider_fields,
    provider_credentials_configured,
)
from bakery.providers.types import (
    ProviderAction,
    ProviderExecutionContext,
    ProviderExecutionResult,
    ProviderHealthResult,
)


class BaseProvider(Provider, ABC):
    """Base class for Bakery providers."""

    provider_type: str
    actions: tuple[ProviderAction, ...] = ("create", "update", "close", "comment", "search")

    def __init__(self) -> None:
        pass

    def supported_actions(self) -> tuple[ProviderAction, ...]:
        return self.actions

    def normalize_payload(self, ctx: ProviderExecutionContext) -> dict[str, Any]:
        return build_provider_payload(
            ctx.action,
            provider=ctx.provider_type,
            internal_ticket_id=ctx.internal_ticket_id,
            provider_ticket_id=ctx.provider_ticket_id,
            payload=ctx.request_payload,
        )

    def validate_payload(self, ctx: ProviderExecutionContext) -> list[str]:
        payload = ctx.normalized_payload or ctx.request_payload
        return missing_provider_fields(ctx.provider_type, ctx.action, payload)

    def provider_result(self, result: dict[str, Any]) -> ProviderExecutionResult:
        return ProviderExecutionResult(
            success=bool(result.get("success")),
            ticket_id=str(result["ticket_id"]) if result.get("ticket_id") is not None else None,
            data=result.get("data") if isinstance(result.get("data"), dict) else None,
            error=str(result["error"]) if result.get("error") is not None else None,
            retryable=bool(result.get("retryable", True)),
            raw=result if "raw" in result else None,
        )

    async def health_check(self) -> ProviderHealthResult:
        configured = provider_credentials_configured(self.provider_type, self)
        if not configured:
            return ProviderHealthResult(
                provider_type=self.provider_type,
                status="unhealthy",
                configured=False,
                message=f"{self.provider_type} credentials are not configured",
            )
        try:
            valid = await self.validate_credentials()
        except Exception as exc:  # noqa: BLE001
            return ProviderHealthResult(
                provider_type=self.provider_type,
                status="unhealthy",
                configured=True,
                message=f"Provider health check failed: {exc}",
            )
        return ProviderHealthResult(
            provider_type=self.provider_type,
            status="healthy" if valid else "degraded",
            configured=True,
            message="Provider credentials are valid" if valid else "Provider validation failed",
        )

    @abstractmethod
    async def validate_credentials(self) -> bool:
        """Validate provider credentials/connectivity."""
