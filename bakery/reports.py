#!/usr/bin/env python3
"""Operator reporting queries for Bakery."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, TypeVar, cast

from sqlalchemy import case, func, or_
from sqlalchemy.orm import Query, Session

from bakery.collection_jobs import collection_job_response, list_collection_jobs_query
from bakery.models import (
    CollectionJob,
    Monitor,
    MonitorEvent,
    MonitorRouteCatalogEntry,
    Ticket,
    TicketOperation,
)
from bakery.schemas import (
    CollectionJobResponse,
    MonitorEventResponse,
    MonitorDetailResponse,
    MonitorFilterOptionResponse,
    MonitorRouteInventoryResponse,
    MonitorSummaryResponse,
    OperationAnalyticsResponse,
    ProviderAnalyticsResponse,
    ReportFilterOptionsResponse,
    ReportOverviewResponse,
    TicketBacklogResponse,
)

QueryT = TypeVar("QueryT", bound=Query[Any])


def _apply_time_range(
    query: QueryT,
    column: Any,
    *,
    start_at: datetime | None,
    end_at: datetime | None,
) -> QueryT:
    filtered_query: Query[Any] = query
    if start_at is not None:
        filtered_query = filtered_query.filter(column >= start_at)
    if end_at is not None:
        filtered_query = filtered_query.filter(column <= end_at)
    return cast(QueryT, filtered_query)


def _monitor_scope_query(
    db: Session,
    *,
    monitor_uuid: str | None,
    environment_label: str | None,
    provider_type: str | None,
    account_number: str | None,
) -> Query:
    query = db.query(Monitor.monitor_uuid)
    if monitor_uuid:
        query = query.filter(Monitor.monitor_uuid == monitor_uuid)
    if environment_label:
        query = query.filter(Monitor.environment_label == environment_label)
    if provider_type or account_number:
        query = query.join(
            MonitorRouteCatalogEntry,
            MonitorRouteCatalogEntry.monitor_uuid == Monitor.monitor_uuid,
        )
        if provider_type:
            query = query.filter(MonitorRouteCatalogEntry.provider_type == provider_type)
        if account_number:
            query = query.filter(MonitorRouteCatalogEntry.account_number == account_number)
    return query.distinct()


def _monitor_uuid_values(
    db: Session,
    *,
    monitor_uuid: str | None,
    environment_label: str | None,
    provider_type: str | None,
    account_number: str | None,
) -> list[str]:
    rows = _monitor_scope_query(
        db,
        monitor_uuid=monitor_uuid,
        environment_label=environment_label,
        provider_type=provider_type,
        account_number=account_number,
    ).all()
    return [str(row[0]) for row in rows]


def report_overview(
    db: Session,
    *,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    monitor_uuid: str | None = None,
    environment_label: str | None = None,
    provider_type: str | None = None,
    account_number: str | None = None,
) -> ReportOverviewResponse:
    monitor_scope = _monitor_scope_query(
        db,
        monitor_uuid=monitor_uuid,
        environment_label=environment_label,
        provider_type=provider_type,
        account_number=account_number,
    )
    monitor_ids = monitor_scope.subquery()
    monitor_query = db.query(Monitor).join(
        monitor_ids,
        monitor_ids.c.monitor_uuid == Monitor.monitor_uuid,
    )

    monitors_total = monitor_query.count()
    monitors_healthy = monitor_query.filter(Monitor.status == "healthy").count()
    monitors_unreachable = monitor_query.filter(Monitor.status == "unreachable").count()

    ticket_query = db.query(Ticket).join(
        monitor_ids,
        monitor_ids.c.monitor_uuid == Ticket.monitor_uuid,
    )
    ticket_query = _apply_time_range(
        ticket_query,
        Ticket.updated_at,
        start_at=start_at,
        end_at=end_at,
    )

    operation_query = (
        db.query(TicketOperation)
        .join(
            Ticket,
            Ticket.internal_ticket_id == TicketOperation.internal_ticket_id,
        )
        .join(
            monitor_ids,
            monitor_ids.c.monitor_uuid == Ticket.monitor_uuid,
        )
    )
    operation_query = _apply_time_range(
        operation_query,
        TicketOperation.created_at,
        start_at=start_at,
        end_at=end_at,
    )
    if provider_type:
        operation_query = operation_query.filter(Ticket.provider_type == provider_type)

    job_query = db.query(CollectionJob).join(
        monitor_ids,
        monitor_ids.c.monitor_uuid == CollectionJob.monitor_uuid,
    )
    job_query = _apply_time_range(
        job_query,
        CollectionJob.created_at,
        start_at=start_at,
        end_at=end_at,
    )

    return ReportOverviewResponse(
        monitors_total=monitors_total,
        monitors_healthy=monitors_healthy,
        monitors_unreachable=monitors_unreachable,
        open_tickets=ticket_query.filter(Ticket.state != "closed").count(),
        queued_operations=operation_query.filter(TicketOperation.status == "queued").count(),
        failed_operations=operation_query.filter(TicketOperation.status == "failed").count(),
        dead_letter_operations=operation_query.filter(
            TicketOperation.status == "dead_letter"
        ).count(),
        queued_collection_jobs=job_query.filter(CollectionJob.status == "queued").count(),
        leased_collection_jobs=job_query.filter(CollectionJob.status == "leased").count(),
        timed_out_collection_jobs=job_query.filter(CollectionJob.status == "timed_out").count(),
    )


def report_filter_options(db: Session) -> ReportFilterOptionsResponse:
    monitor_rows = (
        db.query(Monitor)
        .order_by(
            Monitor.status.asc(),
            Monitor.environment_label.asc(),
            Monitor.monitor_id.asc(),
        )
        .all()
    )
    environment_labels = [
        str(value)
        for value, in (
            db.query(Monitor.environment_label)
            .filter(
                Monitor.environment_label.is_not(None),
                Monitor.environment_label != "",
            )
            .distinct()
            .order_by(Monitor.environment_label.asc())
            .all()
        )
    ]
    provider_types = [
        str(value)
        for value, in (
            db.query(MonitorRouteCatalogEntry.provider_type)
            .filter(
                MonitorRouteCatalogEntry.provider_type.is_not(None),
                MonitorRouteCatalogEntry.provider_type != "",
            )
            .distinct()
            .order_by(MonitorRouteCatalogEntry.provider_type.asc())
            .all()
        )
    ]
    account_numbers = [
        str(value)
        for value, in (
            db.query(MonitorRouteCatalogEntry.account_number)
            .filter(
                MonitorRouteCatalogEntry.account_number.is_not(None),
                MonitorRouteCatalogEntry.account_number != "",
            )
            .distinct()
            .order_by(MonitorRouteCatalogEntry.account_number.asc())
            .all()
        )
    ]
    return ReportFilterOptionsResponse(
        monitors=[
            MonitorFilterOptionResponse(
                monitor_uuid=monitor.monitor_uuid,
                monitor_id=monitor.monitor_id,
                status=monitor.status,
                environment_label=monitor.environment_label,
                region=monitor.region,
                cluster_name=monitor.cluster_name,
                namespace=monitor.namespace,
                release_name=monitor.release_name,
                route_sync_required=bool(monitor.route_sync_required),
                last_checkin_at=monitor.last_checkin_at,
            )
            for monitor in monitor_rows
        ],
        environment_labels=environment_labels,
        provider_types=provider_types,
        account_numbers=account_numbers,
    )


def list_monitors(
    db: Session,
    *,
    monitor_uuid: str | None = None,
    environment_label: str | None = None,
    provider_type: str | None = None,
    account_number: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[MonitorSummaryResponse]:
    route_counts = (
        db.query(
            MonitorRouteCatalogEntry.monitor_uuid.label("monitor_uuid"),
            func.count(MonitorRouteCatalogEntry.id).label("route_count"),
            func.sum(case((MonitorRouteCatalogEntry.outage_enabled.is_(True), 1), else_=0)).label(
                "outage_route_count"
            ),
        )
        .group_by(MonitorRouteCatalogEntry.monitor_uuid)
        .subquery()
    )

    query = db.query(
        Monitor,
        func.coalesce(route_counts.c.route_count, 0),
        func.coalesce(route_counts.c.outage_route_count, 0),
    ).outerjoin(route_counts, route_counts.c.monitor_uuid == Monitor.monitor_uuid)
    if monitor_uuid:
        query = query.filter(Monitor.monitor_uuid == monitor_uuid)
    if environment_label:
        query = query.filter(Monitor.environment_label == environment_label)
    if provider_type or account_number:
        query = query.join(
            MonitorRouteCatalogEntry,
            MonitorRouteCatalogEntry.monitor_uuid == Monitor.monitor_uuid,
        )
        if provider_type:
            query = query.filter(MonitorRouteCatalogEntry.provider_type == provider_type)
        if account_number:
            query = query.filter(MonitorRouteCatalogEntry.account_number == account_number)
        query = query.distinct()
    query = _apply_time_range(query, Monitor.updated_at, start_at=start_at, end_at=end_at)
    rows = (
        query.order_by(
            Monitor.status.asc(),
            Monitor.environment_label.asc(),
            Monitor.monitor_id.asc(),
        )
        .limit(limit)
        .offset(offset)
        .all()
    )
    return [
        MonitorSummaryResponse(
            monitor_uuid=monitor.monitor_uuid,
            monitor_id=monitor.monitor_id,
            status=monitor.status,
            environment_label=monitor.environment_label,
            region=monitor.region,
            cluster_name=monitor.cluster_name,
            namespace=monitor.namespace,
            release_name=monitor.release_name,
            tags=list(monitor.tags_json or []),
            route_sync_required=bool(monitor.route_sync_required),
            route_count=int(row[1] or 0),
            outage_route_count=int(row[2] or 0),
            last_checkin_at=monitor.last_checkin_at,
            unreachable_at=monitor.unreachable_at,
            created_at=monitor.created_at,
            updated_at=monitor.updated_at,
            last_seen_payload=monitor.last_seen_payload,
        )
        for row in rows
        for monitor in [row[0]]
    ]


def list_monitor_events(
    db: Session,
    *,
    monitor_uuid: str | None = None,
    environment_label: str | None = None,
    provider_type: str | None = None,
    account_number: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[MonitorEventResponse]:
    monitor_ids = _monitor_uuid_values(
        db,
        monitor_uuid=monitor_uuid,
        environment_label=environment_label,
        provider_type=provider_type,
        account_number=account_number,
    )
    query = db.query(MonitorEvent)
    if monitor_ids:
        query = query.filter(MonitorEvent.monitor_uuid.in_(monitor_ids))
    elif any([monitor_uuid, environment_label, provider_type, account_number]):
        return []
    query = _apply_time_range(query, MonitorEvent.created_at, start_at=start_at, end_at=end_at)
    rows = (
        query.order_by(MonitorEvent.created_at.desc(), MonitorEvent.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return [
        MonitorEventResponse(
            monitor_uuid=row.monitor_uuid,
            event_type=row.event_type,
            payload=row.payload,
            created_at=row.created_at,
        )
        for row in rows
    ]


def list_route_inventory(
    db: Session,
    *,
    monitor_uuid: str | None = None,
    environment_label: str | None = None,
    provider_type: str | None = None,
    account_number: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    limit: int = 500,
    offset: int = 0,
) -> list[MonitorRouteInventoryResponse]:
    query = db.query(MonitorRouteCatalogEntry, Monitor).join(
        Monitor,
        Monitor.monitor_uuid == MonitorRouteCatalogEntry.monitor_uuid,
    )
    if monitor_uuid:
        query = query.filter(Monitor.monitor_uuid == monitor_uuid)
    if environment_label:
        query = query.filter(Monitor.environment_label == environment_label)
    if provider_type:
        query = query.filter(MonitorRouteCatalogEntry.provider_type == provider_type)
    if account_number:
        query = query.filter(MonitorRouteCatalogEntry.account_number == account_number)
    query = _apply_time_range(
        query,
        MonitorRouteCatalogEntry.updated_at,
        start_at=start_at,
        end_at=end_at,
    )
    rows = (
        query.order_by(
            Monitor.monitor_id.asc(),
            MonitorRouteCatalogEntry.scope.asc(),
            MonitorRouteCatalogEntry.owner_key.asc(),
            MonitorRouteCatalogEntry.position.asc(),
        )
        .limit(limit)
        .offset(offset)
        .all()
    )
    return [
        MonitorRouteInventoryResponse(
            monitor_uuid=route.monitor_uuid,
            monitor_id=monitor.monitor_id,
            environment_label=monitor.environment_label,
            scope=route.scope,
            owner_key=route.owner_key,
            route_id=route.route_id,
            label=route.label,
            provider_type=route.provider_type,
            execution_target=route.execution_target,
            destination_target=route.destination_target,
            account_number=route.account_number,
            queue=route.queue,
            subcategory=route.subcategory,
            enabled=bool(route.enabled),
            outage_enabled=bool(route.outage_enabled),
            position=route.position,
            updated_at=route.updated_at,
        )
        for route, monitor in rows
    ]


def provider_analytics(
    db: Session,
    *,
    monitor_uuid: str | None = None,
    environment_label: str | None = None,
    provider_type: str | None = None,
    account_number: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> list[ProviderAnalyticsResponse]:
    monitor_ids = _monitor_uuid_values(
        db,
        monitor_uuid=monitor_uuid,
        environment_label=environment_label,
        provider_type=provider_type,
        account_number=account_number,
    )
    provider_rows: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "route_count": 0,
            "ticket_count": 0,
            "open_ticket_count": 0,
            "failed_operation_count": 0,
            "dead_letter_count": 0,
        }
    )

    route_query = db.query(
        MonitorRouteCatalogEntry.provider_type,
        func.count(MonitorRouteCatalogEntry.id),
    )
    if monitor_ids:
        route_query = route_query.filter(MonitorRouteCatalogEntry.monitor_uuid.in_(monitor_ids))
    elif any([monitor_uuid, environment_label, provider_type, account_number]):
        route_query = route_query.filter(MonitorRouteCatalogEntry.id == -1)
    if provider_type:
        route_query = route_query.filter(MonitorRouteCatalogEntry.provider_type == provider_type)
    if account_number:
        route_query = route_query.filter(MonitorRouteCatalogEntry.account_number == account_number)
    route_query = route_query.group_by(MonitorRouteCatalogEntry.provider_type)
    for provider, count in route_query.all():
        provider_rows[str(provider)]["route_count"] = int(count or 0)

    ticket_query = db.query(
        Ticket.provider_type,
        func.count(Ticket.id),
        func.sum(case((Ticket.state != "closed", 1), else_=0)),
    )
    if monitor_ids:
        ticket_query = ticket_query.filter(Ticket.monitor_uuid.in_(monitor_ids))
    elif any([monitor_uuid, environment_label, provider_type, account_number]):
        ticket_query = ticket_query.filter(Ticket.id == -1)
    if provider_type:
        ticket_query = ticket_query.filter(Ticket.provider_type == provider_type)
    ticket_query = _apply_time_range(
        ticket_query, Ticket.updated_at, start_at=start_at, end_at=end_at
    )
    ticket_query = ticket_query.group_by(Ticket.provider_type)
    for provider, total, open_count in ticket_query.all():
        provider_rows[str(provider)]["ticket_count"] = int(total or 0)
        provider_rows[str(provider)]["open_ticket_count"] = int(open_count or 0)

    operation_query = db.query(
        Ticket.provider_type,
        TicketOperation.status,
        func.count(TicketOperation.id),
    ).join(Ticket, Ticket.internal_ticket_id == TicketOperation.internal_ticket_id)
    if monitor_ids:
        operation_query = operation_query.filter(Ticket.monitor_uuid.in_(monitor_ids))
    elif any([monitor_uuid, environment_label, provider_type, account_number]):
        operation_query = operation_query.filter(TicketOperation.id == -1)
    if provider_type:
        operation_query = operation_query.filter(Ticket.provider_type == provider_type)
    operation_query = _apply_time_range(
        operation_query,
        TicketOperation.created_at,
        start_at=start_at,
        end_at=end_at,
    )
    operation_query = operation_query.group_by(Ticket.provider_type, TicketOperation.status)
    for provider, status, count in operation_query.all():
        key = str(provider)
        if status == "failed":
            provider_rows[key]["failed_operation_count"] += int(count or 0)
        if status == "dead_letter":
            provider_rows[key]["dead_letter_count"] += int(count or 0)

    return [
        ProviderAnalyticsResponse(provider_type=provider, **metrics)
        for provider, metrics in sorted(provider_rows.items())
    ]


def operation_analytics(
    db: Session,
    *,
    monitor_uuid: str | None = None,
    environment_label: str | None = None,
    provider_type: str | None = None,
    account_number: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> list[OperationAnalyticsResponse]:
    monitor_ids = _monitor_uuid_values(
        db,
        monitor_uuid=monitor_uuid,
        environment_label=environment_label,
        provider_type=provider_type,
        account_number=account_number,
    )
    query = db.query(
        Ticket.provider_type,
        TicketOperation.action,
        TicketOperation.status,
        func.count(TicketOperation.id),
    ).join(Ticket, Ticket.internal_ticket_id == TicketOperation.internal_ticket_id)
    if monitor_ids:
        query = query.filter(Ticket.monitor_uuid.in_(monitor_ids))
    elif any([monitor_uuid, environment_label, provider_type, account_number]):
        return []
    if provider_type:
        query = query.filter(Ticket.provider_type == provider_type)
    query = _apply_time_range(query, TicketOperation.created_at, start_at=start_at, end_at=end_at)
    rows = (
        query.group_by(Ticket.provider_type, TicketOperation.action, TicketOperation.status)
        .order_by(
            Ticket.provider_type.asc(), TicketOperation.action.asc(), TicketOperation.status.asc()
        )
        .all()
    )
    return [
        OperationAnalyticsResponse(
            provider_type=str(provider),
            action=str(action),
            status=str(status),
            count=int(count or 0),
        )
        for provider, action, status, count in rows
    ]


def ticket_backlog(
    db: Session,
    *,
    monitor_uuid: str | None = None,
    environment_label: str | None = None,
    provider_type: str | None = None,
    account_number: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[TicketBacklogResponse]:
    query = db.query(Ticket, Monitor).outerjoin(
        Monitor,
        Monitor.monitor_uuid == Ticket.monitor_uuid,
    )
    if monitor_uuid:
        query = query.filter(Ticket.monitor_uuid == monitor_uuid)
    if environment_label:
        query = query.filter(Monitor.environment_label == environment_label)
    if provider_type:
        query = query.filter(Ticket.provider_type == provider_type)
    if account_number:
        monitor_ids = _monitor_uuid_values(
            db,
            monitor_uuid=None,
            environment_label=environment_label,
            provider_type=provider_type,
            account_number=account_number,
        )
        if not monitor_ids:
            return []
        query = query.filter(Ticket.monitor_uuid.in_(monitor_ids))
    query = query.filter(or_(Ticket.state != "closed", Ticket.latest_error.is_not(None)))
    query = _apply_time_range(query, Ticket.updated_at, start_at=start_at, end_at=end_at)
    rows = (
        query.order_by(Ticket.updated_at.desc(), Ticket.id.desc()).limit(limit).offset(offset).all()
    )
    return [
        TicketBacklogResponse(
            ticket_id=ticket.internal_ticket_id,
            provider_type=ticket.provider_type,
            provider_ticket_id=ticket.provider_ticket_id,
            monitor_uuid=ticket.monitor_uuid,
            monitor_id=(None if monitor is None else monitor.monitor_id),
            environment_label=(None if monitor is None else monitor.environment_label),
            state=ticket.state,
            latest_error=ticket.latest_error,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
        )
        for ticket, monitor in rows
    ]


def monitor_detail(
    db: Session,
    *,
    monitor_uuid: str,
    recent_event_limit: int = 12,
    recent_job_limit: int = 25,
    recent_route_limit: int = 100,
    backlog_limit: int = 10,
) -> MonitorDetailResponse | None:
    monitor_rows = list_monitors(db, monitor_uuid=monitor_uuid, limit=1, offset=0)
    if not monitor_rows:
        return None

    recent_jobs_rows = (
        list_collection_jobs_query(db, monitor_uuid=monitor_uuid)
        .limit(recent_job_limit)
        .offset(0)
        .all()
    )
    latest_successful_rows = (
        db.query(CollectionJob)
        .filter(
            CollectionJob.monitor_uuid == monitor_uuid,
            CollectionJob.status == "succeeded",
        )
        .order_by(
            CollectionJob.completed_at.desc(),
            CollectionJob.updated_at.desc(),
            CollectionJob.id.desc(),
        )
        .all()
    )
    latest_successful_jobs: list[CollectionJobResponse] = []
    seen_collectors: set[str] = set()
    for job in latest_successful_rows:
        if job.collector_type in seen_collectors:
            continue
        latest_successful_jobs.append(collection_job_response(job))
        seen_collectors.add(job.collector_type)

    return MonitorDetailResponse(
        monitor=monitor_rows[0],
        recent_events=list_monitor_events(db, monitor_uuid=monitor_uuid, limit=recent_event_limit),
        recent_routes=list_route_inventory(db, monitor_uuid=monitor_uuid, limit=recent_route_limit),
        recent_jobs=[collection_job_response(job) for job in recent_jobs_rows],
        latest_successful_jobs=latest_successful_jobs,
        operation_analytics=operation_analytics(db, monitor_uuid=monitor_uuid),
        backlog=ticket_backlog(db, monitor_uuid=monitor_uuid, limit=backlog_limit),
    )
