#!/usr/bin/env python3
"""Microsoft Teams webhook provider."""

from __future__ import annotations

from typing import Any, Dict

import httpx

from bakery.config import settings
from bakery.providers.base_provider import BaseProvider
from bakery.providers.types import ProviderExecutionContext, ProviderExecutionResult


class TeamsProvider(BaseProvider):
    provider_type = "teams"
    actions = ("create", "update", "close", "comment")

    def __init__(self) -> None:
        super().__init__()
        self.webhook_url = settings.teams_webhook_url
        self.timeout = settings.provider_timeout_sec

    @staticmethod
    def _message(data: Dict[str, Any]) -> str:
        for key in ("message", "comment", "description", "title"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "PoundCake communication update."

    async def execute(self, ctx: ProviderExecutionContext) -> ProviderExecutionResult:
        data = ctx.normalized_payload or self.normalize_payload(ctx)
        if not self.webhook_url:
            return ProviderExecutionResult(
                success=False,
                error="Teams webhook URL not configured",
                retryable=False,
            )
        if ctx.action == "search":
            return ProviderExecutionResult(
                success=False,
                error="Teams provider does not support search",
                retryable=False,
            )
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(self.webhook_url, json={"text": self._message(data)})
            response.raise_for_status()
        return ProviderExecutionResult(
            success=True,
            ticket_id=str(data.get("ticket_id") or "teams-message"),
        )

    async def validate_credentials(self) -> bool:
        return bool(self.webhook_url)
