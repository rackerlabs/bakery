#!/usr/bin/env python3
"""Health check endpoint for Bakery."""

import os
from datetime import datetime, timezone
from typing import cast
from fastapi import APIRouter

from bakery.config import settings
from bakery.schemas import HealthResponse, ComponentHealth

router = APIRouter()


def _check_database() -> ComponentHealth:
    """
    Check database pool health without consuming pool connections.

    Uses pool-level introspection instead of opening a connection,
    ensuring the probe never competes with application traffic for
    scarce DB connections.
    """
    from sqlalchemy.pool import QueuePool

    from bakery.database import engine

    try:
        pool = cast("QueuePool", engine.pool)
        checked_in = pool.checkedin()
        checked_out = pool.checkedout()
        overflow = pool.overflow()
        total = checked_in + checked_out
        return ComponentHealth(
            status="healthy",
            message="Database pool operational",
            details={
                "checked_in": checked_in,
                "checked_out": checked_out,
                "overflow": overflow,
                "total": total,
            },
        )
    except Exception as e:
        return ComponentHealth(
            status="unhealthy",
            message="Database pool check failed",
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
