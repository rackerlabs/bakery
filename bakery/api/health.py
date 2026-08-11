#!/usr/bin/env python3
"""Health check endpoint for Bakery."""

import os
from datetime import datetime, timezone
from fastapi import APIRouter
from sqlalchemy.orm import Session

from bakery.config import settings
from bakery.schemas import HealthResponse, ComponentHealth

router = APIRouter()


def _check_database() -> ComponentHealth:
    """
    Check database connectivity.

    Returns:
        ComponentHealth with status
    """
    from sqlalchemy import text

    from bakery.database import engine

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return ComponentHealth(status="healthy", message="Database accessible")
    except Exception as e:
        return ComponentHealth(
            status="unhealthy",
            message="Database connection failed",
            details={"error": str(e)},
        )


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description=(
        "Returns the health status of Bakery and its dependencies. "
        "Used by Kubernetes liveness and readiness probes."
    ),
)
def health_check() -> HealthResponse:
    """Health check endpoint."""
    components: dict[str, ComponentHealth] = {}

    components["database"] = _check_database()

    component_statuses = [comp.status for comp in components.values()]
    if all(status == "healthy" for status in component_statuses):
        overall_status = "healthy"
    elif any(status == "unhealthy" for status in component_statuses):
        overall_status = "unhealthy"
    else:
        overall_status = "degraded"

    return HealthResponse(
        status=overall_status,
        version=settings.app_version,
        instance_id=os.getenv("HOSTNAME", "unknown"),
        timestamp=datetime.now(timezone.utc),
        components=components,
    )
