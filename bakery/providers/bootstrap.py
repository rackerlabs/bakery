"""Provider bootstrap and durable registration helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from bakery.models import ProviderConfig
from bakery.providers import get_provider, list_providers
from bakery.providers.types import ProviderBootstrapResult


async def register_provider(db: Session, provider_type: str) -> ProviderBootstrapResult:
    """Sync one provider's non-secret manifest into Bakery's provider registry."""

    provider = get_provider(provider_type)
    manifest = provider.registration_manifest()
    bootstrap = await provider.bootstrap()
    now = datetime.now(timezone.utc)
    config_data: dict[str, Any] = {
        **manifest,
        "bootstrap": bootstrap.model_dump(mode="json"),
        "registered_at": now.isoformat(),
        "source": "provider_contract",
    }
    row = (
        db.query(ProviderConfig)
        .filter(ProviderConfig.provider_type == provider.provider_type)
        .first()
    )
    if row is None:
        row = ProviderConfig(
            provider_type=provider.provider_type,
            enabled=True,
            config_data=config_data,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.config_data = config_data
        row.updated_at = now
    db.flush()
    return bootstrap


async def bootstrap_providers(db: Session) -> dict[str, Any]:
    """Register every discovered provider and return aggregate bootstrap status."""

    results: list[dict[str, Any]] = []
    failures = 0
    for provider_type in list_providers():
        try:
            result = await register_provider(db, provider_type)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            result = ProviderBootstrapResult(
                provider_type=provider_type,
                status="failed",
                message=f"Provider registration failed: {exc}",
                details={"bootstrap_status": "failed"},
            )
        results.append(result.model_dump(mode="json"))

    return {
        "providers": results,
        "count": len(results),
        "failures": failures,
        "status": "ready" if failures == 0 else "failed",
    }


def registered_provider_config(db: Session, provider_type: str) -> ProviderConfig | None:
    """Return the durable provider registration row when present."""

    normalized = (provider_type or "").strip().lower()
    return db.query(ProviderConfig).filter(ProviderConfig.provider_type == normalized).first()
