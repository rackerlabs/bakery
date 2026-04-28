#!/usr/bin/env python3
"""Provider management endpoints for Bakery."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from bakery.auth import require_bootstrap_admin_access
from bakery.database import get_db
from bakery.providers import get_provider, list_providers
from bakery.providers.bootstrap import bootstrap_providers, registered_provider_config
from bakery.schemas import (
    ProviderBootstrapResponse,
    ProviderHealthResponse,
    ProviderInfo,
    ProviderListResponse,
)

router = APIRouter()


@router.get(
    "/providers",
    response_model=ProviderListResponse,
    summary="List providers",
    description=(
        "Returns all registered providers and their current configuration "
        "status. Providers are Bakery's backend integrations for systems "
        "such as Jira, Rackspace Core, ServiceNow, GitHub, PagerDuty, Teams, and Discord."
    ),
)
async def get_available_providers(db: Session = Depends(get_db)) -> ProviderListResponse:
    providers: list[ProviderInfo] = []

    for provider_type in list_providers():
        provider = get_provider(provider_type)
        health = await provider.health_check()
        registration = registered_provider_config(db, provider_type)
        config_data = registration.config_data if registration is not None else {}
        bootstrap = config_data.get("bootstrap") if isinstance(config_data, dict) else {}
        providers.append(
            ProviderInfo(
                provider_type=provider_type,
                actions=list(provider.supported_actions()),
                registered=registration is not None,
                enabled=bool(registration.enabled) if registration is not None else True,
                configured=health.configured,
                config_schema=provider.config_schema(),
                credential_requirements=provider.credential_requirements(),
                bootstrap_status=(
                    str(bootstrap.get("status"))
                    if isinstance(bootstrap, dict) and bootstrap.get("status") is not None
                    else None
                ),
            )
        )

    return ProviderListResponse(providers=providers, count=len(providers))


@router.post(
    "/providers/bootstrap",
    response_model=ProviderBootstrapResponse,
    summary="Bootstrap providers",
    description=(
        "Registers every discovered provider's non-secret manifest into Bakery's durable "
        "provider catalog. This does not write provider secrets."
    ),
)
async def bootstrap_provider_catalog(
    _access: str = Depends(require_bootstrap_admin_access),
    db: Session = Depends(get_db),
) -> ProviderBootstrapResponse:
    result = await bootstrap_providers(db)
    db.commit()
    return ProviderBootstrapResponse(**result)


@router.post(
    "/providers/{provider_type}/health-check",
    response_model=ProviderHealthResponse,
    summary="Run provider health check",
    description=(
        "Tests connectivity and authentication with the specified provider backend. "
        "This makes a live provider call when the provider supports one."
    ),
)
async def run_provider_health_check(provider_type: str) -> ProviderHealthResponse:
    available = list_providers()
    if provider_type not in available:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown provider_type: {provider_type}. Available: {', '.join(available)}",
        )

    health = await get_provider(provider_type).health_check()
    return ProviderHealthResponse(
        provider_type=health.provider_type,
        status=health.status,
        configured=health.configured,
        message=health.message,
        details=health.details,
    )
