#!/usr/bin/env python3
"""UI bootstrap settings for Bakery."""

from __future__ import annotations

from fastapi import APIRouter

from bakery.config import settings
from bakery.operator_auth import get_enabled_provider_metadata
from bakery.schemas import AuthProviderResponse, SettingsResponse

router = APIRouter()


@router.get("/settings", response_model=SettingsResponse)
async def get_settings() -> SettingsResponse:
    return SettingsResponse(
        auth_enabled=settings.operator_auth_enabled,
        rbac_enabled=settings.operator_auth_rbac_enabled,
        auth_providers=[
            AuthProviderResponse.model_validate(item) for item in get_enabled_provider_metadata()
        ],
        version=settings.app_version,
    )
