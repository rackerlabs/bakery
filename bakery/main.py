#!/usr/bin/env python3
"""Bakery FastAPI application."""

import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
import structlog

from bakery.api.communications import router as communications_router
from bakery.config import settings
from bakery.api.admin import router as admin_router
from bakery.api.collection_jobs import router as collection_jobs_router
from bakery.api.health import router as health_router
from bakery.api.mixers import router as mixers_router
from bakery.api.monitors import router as monitors_router
from bakery.api.operator_auth import router as operator_auth_router
from bakery.api.reports import router as reports_router
from bakery.api.settings import router as settings_router
from bakery.api.tickets import router as tickets_router
from bakery.metrics import render_metrics


# Configure structured logging
def configure_logging() -> None:
    """Configure structured logging for Bakery."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper()),
    )

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Lifespan context manager for FastAPI application.

    Handles startup and shutdown events.
    """
    logger = structlog.get_logger()
    logger.info(
        "Bakery starting",
        version=settings.app_version,
        environment=settings.environment,
    )
    yield
    logger.info("Bakery shutting down")


# Configure logging
configure_logging()

# OpenAPI tag metadata for Swagger grouping
tags_metadata = [
    {
        "name": "health",
        "description": "Health check and readiness probes.",
    },
    {
        "name": "communications",
        "description": (
            "Submit and query provider-agnostic communications. "
            "Mutating endpoints return operation handles and are processed asynchronously."
        ),
    },
    {
        "name": "monitors",
        "description": (
            "Register PoundCake monitors, sync their communication route catalogs, and accept "
            "heartbeat check-ins."
        ),
    },
    {
        "name": "admin",
        "description": "Administrative monitor bootstrap credential management endpoints.",
    },
    {
        "name": "auth",
        "description": "Human operator authentication, session, and RBAC management endpoints.",
    },
    {
        "name": "reports",
        "description": "Durable DB-backed operator reports for monitors, routes, providers, and backlog.",
    },
    {
        "name": "collection-jobs",
        "description": "Queue and inspect read-only PoundCake collection jobs.",
    },
    {
        "name": "settings",
        "description": "UI bootstrap settings and auth-provider discovery helpers.",
    },
    {
        "name": "tickets",
        "description": (
            "Legacy compatibility endpoints retained for callers that still speak the older "
            "Bakery ticket contract."
        ),
    },
    {
        "name": "mixers",
        "description": (
            "Discover and validate ticketing system integrations. "
            "Each mixer corresponds to an external ticketing system "
            "(ServiceNow, Jira, GitHub, PagerDuty, Rackspace Core)."
        ),
    },
]

# Create FastAPI application
app = FastAPI(
    title="Bakery",
    description=(
        "Bakery is a standalone ticketing and messaging integration service.\n\n"
        "Bakery acts as a translation layer between client applications and "
        "external communication systems (ServiceNow, Jira, GitHub Issues, "
        "PagerDuty, Rackspace Core, Teams, Discord). It receives generic communication requests, "
        "queues operations, and processes them asynchronously via worker(s).\n\n"
        "## Request Flow\n\n"
        "1. `POST /api/v1/communications` - Submit open request (returns 202 with UUID handles)\n"
        "2. `GET /api/v1/communications/operations/{operation_id}` - Poll operation status\n"
        "3. `GET /api/v1/communications/{communication_id}` - Read logical communication state\n"
        "4. Legacy callers may continue using `/api/v1/tickets*` during migration windows.\n"
    ),
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=tags_metadata,
)


# Exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Global exception handler.

    Args:
        request: FastAPI request
        exc: Exception that was raised

    Returns:
        JSON error response
    """
    logger = structlog.get_logger()
    logger.error(
        "Unhandled exception",
        exc_info=exc,
        path=request.url.path,
        method=request.method,
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if settings.environment == "development" else None,
        },
    )


# Include routers
app.include_router(health_router, prefix=settings.api_prefix, tags=["health"])
app.include_router(settings_router, prefix=settings.api_prefix, tags=["settings"])
app.include_router(operator_auth_router, prefix=settings.api_prefix, tags=["auth"])
app.include_router(admin_router, prefix=settings.api_prefix, tags=["admin"])
app.include_router(monitors_router, prefix=settings.api_prefix, tags=["monitors"])
app.include_router(reports_router, prefix=settings.api_prefix, tags=["reports"])
app.include_router(collection_jobs_router, prefix=settings.api_prefix, tags=["collection-jobs"])
app.include_router(communications_router, prefix=settings.api_prefix, tags=["communications"])
app.include_router(tickets_router, prefix=settings.api_prefix, tags=["tickets"])
app.include_router(mixers_router, prefix=settings.api_prefix, tags=["mixers"])


@app.get("/metrics")
async def metrics() -> Response:
    payload, content_type = render_metrics()
    return Response(content=payload, media_type=content_type)


# Root endpoint
@app.get("/")
async def root() -> dict[str, str]:
    """
    Root endpoint.

    Returns:
        Service information
    """
    return {
        "service": "Bakery",
        "version": settings.app_version,
        "description": "Standalone communication integration service",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "bakery.main:app",
        host="0.0.0.0",
        port=8000,
        log_level=settings.log_level.lower(),
        reload=settings.environment == "development",
    )
