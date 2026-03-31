#!/usr/bin/env python3
"""Operator reporting APIs for Bakery."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from bakery.database import get_db
from bakery.operator_auth import AuthContext, require_reader
from bakery.reports import (
    list_monitor_events,
    list_monitors,
    list_route_inventory,
    operation_analytics,
    provider_analytics,
    report_overview,
    ticket_backlog,
)
from bakery.schemas import (
    MonitorEventResponse,
    MonitorRouteInventoryResponse,
    MonitorSummaryResponse,
    OperationAnalyticsResponse,
    ProviderAnalyticsResponse,
    ReportOverviewResponse,
    TicketBacklogResponse,
)

router = APIRouter()


def _filters(
    *,
    start_at: datetime | None,
    end_at: datetime | None,
    monitor_uuid: str | None,
    environment_label: str | None,
    provider_type: str | None,
    account_number: str | None,
) -> dict[str, object | None]:
    return {
        "start_at": start_at,
        "end_at": end_at,
        "monitor_uuid": monitor_uuid,
        "environment_label": environment_label,
        "provider_type": provider_type,
        "account_number": account_number,
    }


@router.get("/reports/overview", response_model=ReportOverviewResponse)
async def get_report_overview(
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    monitor_uuid: str | None = Query(default=None),
    environment_label: str | None = Query(default=None),
    provider_type: str | None = Query(default=None),
    account_number: str | None = Query(default=None),
    _context: AuthContext = Depends(require_reader),
    db: Session = Depends(get_db),
) -> ReportOverviewResponse:
    return report_overview(
        db,
        **_filters(
            start_at=start_at,
            end_at=end_at,
            monitor_uuid=monitor_uuid,
            environment_label=environment_label,
            provider_type=provider_type,
            account_number=account_number,
        ),
    )


@router.get("/reports/monitors", response_model=list[MonitorSummaryResponse])
async def get_monitor_report(
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    monitor_uuid: str | None = Query(default=None),
    environment_label: str | None = Query(default=None),
    provider_type: str | None = Query(default=None),
    account_number: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    _context: AuthContext = Depends(require_reader),
    db: Session = Depends(get_db),
) -> list[MonitorSummaryResponse]:
    return list_monitors(
        db,
        **_filters(
            start_at=start_at,
            end_at=end_at,
            monitor_uuid=monitor_uuid,
            environment_label=environment_label,
            provider_type=provider_type,
            account_number=account_number,
        ),
        limit=limit,
        offset=offset,
    )


@router.get("/reports/monitor-events", response_model=list[MonitorEventResponse])
async def get_monitor_event_report(
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    monitor_uuid: str | None = Query(default=None),
    environment_label: str | None = Query(default=None),
    provider_type: str | None = Query(default=None),
    account_number: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    _context: AuthContext = Depends(require_reader),
    db: Session = Depends(get_db),
) -> list[MonitorEventResponse]:
    return list_monitor_events(
        db,
        **_filters(
            start_at=start_at,
            end_at=end_at,
            monitor_uuid=monitor_uuid,
            environment_label=environment_label,
            provider_type=provider_type,
            account_number=account_number,
        ),
        limit=limit,
        offset=offset,
    )


@router.get("/reports/routes", response_model=list[MonitorRouteInventoryResponse])
async def get_route_inventory_report(
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    monitor_uuid: str | None = Query(default=None),
    environment_label: str | None = Query(default=None),
    provider_type: str | None = Query(default=None),
    account_number: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    _context: AuthContext = Depends(require_reader),
    db: Session = Depends(get_db),
) -> list[MonitorRouteInventoryResponse]:
    return list_route_inventory(
        db,
        **_filters(
            start_at=start_at,
            end_at=end_at,
            monitor_uuid=monitor_uuid,
            environment_label=environment_label,
            provider_type=provider_type,
            account_number=account_number,
        ),
        limit=limit,
        offset=offset,
    )


@router.get("/reports/providers", response_model=list[ProviderAnalyticsResponse])
async def get_provider_analytics_report(
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    monitor_uuid: str | None = Query(default=None),
    environment_label: str | None = Query(default=None),
    provider_type: str | None = Query(default=None),
    account_number: str | None = Query(default=None),
    _context: AuthContext = Depends(require_reader),
    db: Session = Depends(get_db),
) -> list[ProviderAnalyticsResponse]:
    return provider_analytics(
        db,
        **_filters(
            start_at=start_at,
            end_at=end_at,
            monitor_uuid=monitor_uuid,
            environment_label=environment_label,
            provider_type=provider_type,
            account_number=account_number,
        ),
    )


@router.get("/reports/operations", response_model=list[OperationAnalyticsResponse])
async def get_operation_analytics_report(
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    monitor_uuid: str | None = Query(default=None),
    environment_label: str | None = Query(default=None),
    provider_type: str | None = Query(default=None),
    account_number: str | None = Query(default=None),
    _context: AuthContext = Depends(require_reader),
    db: Session = Depends(get_db),
) -> list[OperationAnalyticsResponse]:
    return operation_analytics(
        db,
        **_filters(
            start_at=start_at,
            end_at=end_at,
            monitor_uuid=monitor_uuid,
            environment_label=environment_label,
            provider_type=provider_type,
            account_number=account_number,
        ),
    )


@router.get("/reports/backlog", response_model=list[TicketBacklogResponse])
async def get_ticket_backlog_report(
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    monitor_uuid: str | None = Query(default=None),
    environment_label: str | None = Query(default=None),
    provider_type: str | None = Query(default=None),
    account_number: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    _context: AuthContext = Depends(require_reader),
    db: Session = Depends(get_db),
) -> list[TicketBacklogResponse]:
    return ticket_backlog(
        db,
        **_filters(
            start_at=start_at,
            end_at=end_at,
            monitor_uuid=monitor_uuid,
            environment_label=environment_label,
            provider_type=provider_type,
            account_number=account_number,
        ),
        limit=limit,
        offset=offset,
    )
