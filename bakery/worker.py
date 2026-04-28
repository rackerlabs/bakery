#!/usr/bin/env python3
"""DB-backed worker for Bakery ticket operations."""

from __future__ import annotations

import asyncio
import hashlib
import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import and_, or_

from bakery.api.tickets import _enqueue_ticket_action_request, create_ticket_request
from bakery.collection_jobs import expire_collection_job_leases
from bakery.config import settings
from bakery.database import SessionLocal
from bakery.metrics import (
    BAKERY_DEAD_LETTER_TOTAL,
    BAKERY_OPERATION_LATENCY_SECONDS,
    BAKERY_OPERATIONS_TOTAL,
    BAKERY_RETRIES_TOTAL,
)
from bakery.models import (
    Monitor,
    MonitorOutageRouteState,
    MonitorRouteCatalogEntry,
    Ticket,
    TicketOperation,
)
from bakery.monitoring import get_outage_enabled_routes, record_monitor_event
from bakery.providers import get_provider
from bakery.providers.types import ProviderExecutionContext
from bakery.schemas import TicketCommentRequest, TicketCreateRequest

logger = structlog.get_logger()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _compute_backoff(attempt: int) -> int:
    raw = settings.worker_backoff_base_sec * int(math.pow(2, max(attempt - 1, 0)))
    return min(raw, settings.worker_backoff_max_sec)


def _claim_operations(batch_size: int) -> list[TicketOperation]:
    now = _now()
    with SessionLocal() as db:
        rows = (
            db.query(TicketOperation)
            .filter(
                and_(
                    TicketOperation.status.in_(["queued", "failed"]),
                    or_(
                        TicketOperation.next_attempt_at.is_(None),
                        TicketOperation.next_attempt_at <= now,
                    ),
                )
            )
            .order_by(TicketOperation.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(batch_size)
            .all()
        )
        if not rows:
            db.commit()
            return []

        for row in rows:
            row.status = "running"
            row.started_at = now
            row.updated_at = now
        db.commit()
        for row in rows:
            db.refresh(row)
        return rows


def _load_ticket(internal_ticket_id: str) -> Ticket:
    with SessionLocal() as db:
        ticket = db.query(Ticket).filter(Ticket.internal_ticket_id == internal_ticket_id).first()
        if not ticket:
            raise ValueError("Ticket does not exist")
        db.expunge(ticket)
        return ticket


def _persist_success(operation_id: str, result: dict[str, Any]) -> None:
    now = _now()
    with SessionLocal() as db:
        operation = (
            db.query(TicketOperation).filter(TicketOperation.operation_id == operation_id).first()
        )
        if not operation:
            return
        ticket = (
            db.query(Ticket)
            .filter(Ticket.internal_ticket_id == operation.internal_ticket_id)
            .first()
        )
        if not ticket:
            return

        operation.status = "succeeded"
        operation.provider_response = result
        operation.last_error = None
        operation.completed_at = now
        operation.updated_at = now

        external_ticket_id = result.get("ticket_id")
        if operation.action == "create" and external_ticket_id:
            ticket.provider_ticket_id = str(external_ticket_id)
            ticket.state = "open"
        elif operation.action == "close":
            data = result.get("data")
            provider_state = data.get("state") if isinstance(data, dict) else None
            ticket.state = str(provider_state).strip() if provider_state else "closed"
        elif operation.action == "update":
            ticket.state = "updating"
        elif operation.action == "comment":
            ticket.state = "open"
        ticket.latest_error = None
        ticket.updated_at = now
        BAKERY_OPERATIONS_TOTAL.labels(action=operation.action, status="succeeded").inc()
        db.commit()


def _persist_normalized_payload(operation_id: str, payload: dict[str, Any]) -> None:
    now = _now()
    with SessionLocal() as db:
        operation = (
            db.query(TicketOperation).filter(TicketOperation.operation_id == operation_id).first()
        )
        if not operation:
            return
        operation.normalized_payload = payload
        operation.updated_at = now
        db.commit()


def _persist_failure(operation_id: str, error: str) -> None:
    now = _now()
    with SessionLocal() as db:
        operation = (
            db.query(TicketOperation).filter(TicketOperation.operation_id == operation_id).first()
        )
        if not operation:
            return
        ticket = (
            db.query(Ticket)
            .filter(Ticket.internal_ticket_id == operation.internal_ticket_id)
            .first()
        )
        if not ticket:
            return

        operation.attempt_count += 1
        operation.last_error = error
        operation.updated_at = now

        if operation.attempt_count >= operation.max_attempts:
            operation.status = "dead_letter"
            operation.completed_at = now
            operation.next_attempt_at = None
            ticket.state = "error"
            BAKERY_DEAD_LETTER_TOTAL.labels(action=operation.action).inc()
            BAKERY_OPERATIONS_TOTAL.labels(action=operation.action, status="dead_letter").inc()
        else:
            operation.status = "failed"
            delay = _compute_backoff(operation.attempt_count)
            operation.next_attempt_at = now + timedelta(seconds=delay)
            ticket.state = "error"
            BAKERY_RETRIES_TOTAL.labels(action=operation.action).inc()
            BAKERY_OPERATIONS_TOTAL.labels(action=operation.action, status="failed").inc()

        ticket.latest_error = error
        ticket.updated_at = now
        db.commit()


def _persist_non_retryable_failure(operation_id: str, error: str) -> None:
    now = _now()
    with SessionLocal() as db:
        operation = (
            db.query(TicketOperation).filter(TicketOperation.operation_id == operation_id).first()
        )
        if not operation:
            return
        ticket = (
            db.query(Ticket)
            .filter(Ticket.internal_ticket_id == operation.internal_ticket_id)
            .first()
        )
        if not ticket:
            return

        operation.status = "dead_letter"
        operation.attempt_count = operation.max_attempts
        operation.last_error = error
        operation.next_attempt_at = None
        operation.completed_at = now
        operation.updated_at = now

        ticket.state = "error"
        ticket.latest_error = error
        ticket.updated_at = now

        BAKERY_DEAD_LETTER_TOTAL.labels(action=operation.action).inc()
        BAKERY_OPERATIONS_TOTAL.labels(action=operation.action, status="dead_letter").inc()
        db.commit()


def _build_dry_run_result(
    operation: TicketOperation,
    ticket: Ticket,
    payload: dict[str, Any],
) -> dict[str, Any]:
    simulated_ticket_id = ticket.provider_ticket_id or f"dryrun-{ticket.internal_ticket_id}"
    return {
        "success": True,
        "ticket_id": simulated_ticket_id,
        "data": {
            "dry_run": True,
            "provider": ticket.provider_type or settings.active_provider,
            "action": operation.action,
            "operation_id": operation.operation_id,
            "payload": payload,
        },
    }


def _monitor_threshold_deadline(monitor: Monitor) -> datetime:
    baseline = _as_utc(monitor.last_checkin_at or monitor.created_at)
    return baseline + timedelta(
        seconds=settings.bakery_monitor_heartbeat_interval_sec
        * settings.bakery_monitor_miss_threshold
    )


def _ticket_is_closed(ticket: Ticket | None) -> bool:
    if ticket is None:
        return True
    return str(ticket.state or "").strip().lower() in {"closed", "confirmed_solved"}


def _idempotency_key(*parts: str) -> str:
    joined = ":".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _outage_open_payload(monitor: Monitor, route: MonitorRouteCatalogEntry) -> TicketCreateRequest:
    title = f"PoundCake monitor unreachable: {monitor.monitor_id}"
    description = (
        f"PoundCake monitor `{monitor.monitor_id}` (`{monitor.monitor_uuid}`) has not checked in "
        f"for at least {settings.bakery_monitor_miss_threshold} heartbeat intervals."
    )
    return TicketCreateRequest(
        title=title,
        description=description,
        message=description,
        source="bakery",
        context={
            "source": "bakery",
            "provider_type": route.execution_target,
            "execution_target": route.execution_target,
            "destination_target": route.destination_target or "",
            "route_label": route.label,
            "provider_config": route.provider_config or {},
            "monitor": {
                "monitor_id": monitor.monitor_id,
                "monitor_uuid": monitor.monitor_uuid,
            },
        },
    )


def _outage_comment_payload(
    monitor: Monitor,
    *,
    recovered: bool,
) -> TicketCommentRequest:
    if recovered:
        comment = (
            f"PoundCake monitor `{monitor.monitor_id}` resumed check-ins at {_now().isoformat()}. "
            "Leaving this communication open for operator follow-up."
        )
    else:
        comment = (
            f"PoundCake monitor `{monitor.monitor_id}` is unreachable again as of "
            f"{_now().isoformat()}."
        )
    return TicketCommentRequest(
        comment=comment,
        context={
            "source": "bakery",
            "monitor": {
                "monitor_id": monitor.monitor_id,
                "monitor_uuid": monitor.monitor_uuid,
            },
        },
    )


def _ensure_route_state(
    db,
    *,
    monitor_uuid: str,
    route: MonitorRouteCatalogEntry,
) -> MonitorOutageRouteState:
    state = (
        db.query(MonitorOutageRouteState)
        .filter(
            MonitorOutageRouteState.monitor_uuid == monitor_uuid,
            MonitorOutageRouteState.scope == route.scope,
            MonitorOutageRouteState.owner_key == route.owner_key,
            MonitorOutageRouteState.route_id == route.route_id,
        )
        .first()
    )
    if state is not None:
        return state
    state = MonitorOutageRouteState(
        monitor_uuid=monitor_uuid,
        scope=route.scope,
        owner_key=route.owner_key,
        route_id=route.route_id,
        last_state="healthy",
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(state)
    db.flush()
    return state


def _current_ticket(db, ticket_id: str | None) -> Ticket | None:
    if not ticket_id:
        return None
    return db.query(Ticket).filter(Ticket.internal_ticket_id == ticket_id).first()


def _handle_monitor_unreachable_transition(monitor: Monitor) -> None:
    now = _now()
    with SessionLocal() as db:
        db_monitor = db.query(Monitor).filter(Monitor.monitor_uuid == monitor.monitor_uuid).first()
        if db_monitor is None:
            return
        routes = get_outage_enabled_routes(db, monitor_uuid=db_monitor.monitor_uuid)
        for route in routes:
            state = _ensure_route_state(db, monitor_uuid=db_monitor.monitor_uuid, route=route)
            ticket = _current_ticket(db, state.ticket_id)
            if ticket is None or _ticket_is_closed(ticket):
                accepted = asyncio.run(
                    create_ticket_request(
                        _outage_open_payload(db_monitor, route),
                        idempotency_key=_idempotency_key(
                            "monitor",
                            db_monitor.monitor_uuid,
                            route.scope,
                            route.owner_key,
                            route.route_id,
                            "open",
                            now.isoformat(),
                        ),
                        db=db,
                        monitor_uuid=db_monitor.monitor_uuid,
                        validate_route=False,
                    )
                )
                state.ticket_id = accepted.ticket_id
            else:
                _enqueue_ticket_action_request(
                    db,
                    ticket.internal_ticket_id,
                    "comment",
                    _outage_comment_payload(db_monitor, recovered=False).model_dump(),
                    _idempotency_key(
                        "monitor",
                        db_monitor.monitor_uuid,
                        route.scope,
                        route.owner_key,
                        route.route_id,
                        "down-comment",
                        now.isoformat(),
                    ),
                    monitor_uuid=db_monitor.monitor_uuid,
                    validate_route=False,
                )
            state.last_state = "unreachable"
            state.updated_at = now

        db_monitor.status = "unreachable"
        db_monitor.unreachable_at = now
        db_monitor.updated_at = now
        record_monitor_event(
            db,
            monitor_uuid=db_monitor.monitor_uuid,
            event_type="unreachable",
            payload={"monitor_id": db_monitor.monitor_id, "route_count": len(routes)},
        )
        db.commit()


def _handle_monitor_recovery_transition(monitor: Monitor) -> None:
    now = _now()
    with SessionLocal() as db:
        db_monitor = db.query(Monitor).filter(Monitor.monitor_uuid == monitor.monitor_uuid).first()
        if db_monitor is None:
            return
        states = (
            db.query(MonitorOutageRouteState)
            .filter(MonitorOutageRouteState.monitor_uuid == db_monitor.monitor_uuid)
            .all()
        )
        for state in states:
            ticket = _current_ticket(db, state.ticket_id)
            if ticket is None:
                state.last_state = "healthy"
                state.updated_at = now
                continue
            _enqueue_ticket_action_request(
                db,
                ticket.internal_ticket_id,
                "comment",
                _outage_comment_payload(db_monitor, recovered=True).model_dump(),
                _idempotency_key(
                    "monitor",
                    db_monitor.monitor_uuid,
                    state.scope,
                    state.owner_key,
                    state.route_id,
                    "recovery-comment",
                    now.isoformat(),
                ),
                monitor_uuid=db_monitor.monitor_uuid,
                validate_route=False,
            )
            state.last_state = "healthy"
            state.updated_at = now

        db_monitor.status = "healthy"
        db_monitor.unreachable_at = None
        db_monitor.updated_at = now
        record_monitor_event(
            db,
            monitor_uuid=db_monitor.monitor_uuid,
            event_type="recovered",
            payload={"monitor_id": db_monitor.monitor_id, "state_count": len(states)},
        )
        db.commit()


def _run_monitor_sweep() -> None:
    now = _now()
    with SessionLocal() as db:
        monitors = db.query(Monitor).all()
        for monitor in monitors:
            overdue = _monitor_threshold_deadline(monitor) <= now
            if overdue and monitor.status != "unreachable":
                db.expunge(monitor)
                _handle_monitor_unreachable_transition(monitor)
                continue
            if not overdue and monitor.status == "unreachable":
                db.expunge(monitor)
                _handle_monitor_recovery_transition(monitor)


def _process_operation(operation: TicketOperation) -> None:
    started = time.monotonic()
    ticket = _load_ticket(operation.internal_ticket_id)
    provider_type = str(ticket.provider_type or settings.active_provider or "").strip().lower()
    provider = get_provider(provider_type)
    ctx = ProviderExecutionContext(
        provider_type=provider_type,
        action=operation.action,
        internal_ticket_id=ticket.internal_ticket_id,
        provider_ticket_id=ticket.provider_ticket_id,
        request_payload=operation.request_payload,
        dry_run=settings.ticketing_dry_run,
    )
    payload = provider.normalize_payload(ctx)
    ctx = ctx.model_copy(update={"normalized_payload": payload})
    _persist_normalized_payload(operation.operation_id, payload)
    missing = provider.validate_payload(ctx)
    if missing:
        error = f"{provider_type} {operation.action} missing required fields: " + ", ".join(
            missing
        )
        logger.error(
            "Provider preflight validation failed",
            operation_id=operation.operation_id,
            ticket_id=operation.internal_ticket_id,
            provider=provider_type,
            action=operation.action,
            missing_fields=missing,
        )
        _persist_non_retryable_failure(operation.operation_id, error)
        return

    if settings.ticketing_dry_run:
        logger.info(
            "Dry-run enabled; skipping provider call",
            operation_id=operation.operation_id,
            action=operation.action,
            provider=provider_type,
        )
        result = _build_dry_run_result(operation, ticket, payload)
    else:
        result = asyncio.run(provider.execute(ctx)).as_provider_response()
    BAKERY_OPERATION_LATENCY_SECONDS.labels(action=operation.action).observe(
        max(time.monotonic() - started, 0.0)
    )
    if result.get("success"):
        _persist_success(operation.operation_id, result)
        return
    _persist_failure(operation.operation_id, str(result.get("error") or "provider request failed"))


def run_worker() -> None:
    logger.info(
        "Bakery worker started",
        provider=settings.active_provider,
        batch_size=settings.worker_batch_size,
        poll_interval_sec=settings.worker_poll_interval_sec,
    )
    next_monitor_sweep = time.monotonic()
    next_collection_sweep = time.monotonic()
    while True:
        if time.monotonic() >= next_monitor_sweep:
            try:
                _run_monitor_sweep()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Monitor sweep failed", error=str(exc))
            next_monitor_sweep = time.monotonic() + settings.bakery_monitor_sweep_interval_sec

        if time.monotonic() >= next_collection_sweep:
            try:
                with SessionLocal() as db:
                    expired = expire_collection_job_leases(db)
                    if expired:
                        db.commit()
                        logger.info("Collection job leases expired", count=expired)
                    else:
                        db.rollback()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Collection job sweep failed", error=str(exc))
            next_collection_sweep = time.monotonic() + settings.bakery_collection_sweep_interval_sec

        claimed = _claim_operations(settings.worker_batch_size)
        if not claimed:
            time.sleep(settings.worker_poll_interval_sec)
            continue

        for operation in claimed:
            try:
                _process_operation(operation)
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "Operation execution failed",
                    operation_id=operation.operation_id,
                    error=str(exc),
                )
                _persist_failure(operation.operation_id, str(exc))


if __name__ == "__main__":
    run_worker()
