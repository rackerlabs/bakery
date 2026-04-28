"""Base provider contract for Bakery backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from bakery.providers.types import (
    ProviderAction,
    ProviderBootstrapResult,
    ProviderExecutionContext,
    ProviderExecutionResult,
    ProviderHealthResult,
)


class Provider(ABC):
    """Provider integration boundary implemented by each Bakery backend."""

    provider_type: str

    def supported_actions(self) -> tuple[ProviderAction, ...]:
        return ("create", "update", "comment", "close", "search")

    @abstractmethod
    def normalize_payload(self, ctx: ProviderExecutionContext) -> dict[str, Any]:
        """Translate Bakery's canonical operation payload into provider-native shape."""

    @abstractmethod
    def validate_payload(self, ctx: ProviderExecutionContext) -> list[str]:
        """Return missing or invalid provider-native fields before dispatch."""

    @abstractmethod
    async def execute(self, ctx: ProviderExecutionContext) -> ProviderExecutionResult:
        """Execute provider work for a normalized payload."""

    async def search(self, ctx: ProviderExecutionContext) -> ProviderExecutionResult:
        search_ctx = ctx.model_copy(update={"action": "search"})
        return await self.execute(search_ctx)

    @abstractmethod
    async def health_check(self) -> ProviderHealthResult:
        """Check provider backend configuration/connectivity without exposing secrets."""

    def config_schema(self) -> dict[str, Any]:
        """Return non-secret operator-visible configuration requirements."""
        return {"type": "object", "properties": {}, "additionalProperties": False}

    def credential_requirements(self) -> list[dict[str, Any]]:
        """Return non-secret credential requirement descriptors."""
        return []

    def registration_manifest(self) -> dict[str, Any]:
        """Return the non-secret provider manifest stored during bootstrap."""
        return {
            "contract_version": 1,
            "provider_type": self.provider_type,
            "actions": list(self.supported_actions()),
            "config_schema": self.config_schema(),
            "credential_requirements": self.credential_requirements(),
        }

    async def bootstrap(self) -> ProviderBootstrapResult:
        """Bootstrap provider-owned state before the provider is activated."""
        return ProviderBootstrapResult(
            provider_type=self.provider_type,
            status="ready",
            message="Provider bootstrap is not required",
            details={"bootstrap_status": "ready"},
        )
