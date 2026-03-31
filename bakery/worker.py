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
from bakery.config import settings
from bakery.database import SessionLocal
from bakery.formatters import provider_config_from_context, render_provider_content
from bakery.metrics import (
    BAKERY_DEAD_LETTER_TOTAL,
    BAKERY_OPERATION_LATENCY_SECONDS,
    BAKERY_OPERATIONS_TOTAL,
    BAKERY_RETRIES_TOTAL,
)
from bakery.mixer.factory import get_mixer
from bakery.models import (
    Monitor,
    MonitorOutageRouteState,
    MonitorRouteCatalogEntry,
    Ticket,
    TicketOperation,
)
from bakery.monitoring import get_outage_enabled_routes, record_monitor_event
from bakery.schemas import TicketCommentRequest, TicketCreateRequest

logger = structlog.get_logger()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if _is_non_empty(value):
            return value
    return None


def _build_provider_payload(
    action: str,
    ticket: Ticket,
    payload: dict[str, Any],
) -> dict[str, Any]:
    provider = str(ticket.provider_type or settings.active_provider or "").strip().lower()
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    provider_payload = provider_config_from_context(provider, payload)

    for key in ("source", "visibility"):
        if context.get(key) is not None and key not in provider_payload:
            provider_payload[key] = context.get(key)

    if action == "create":
        provider_payload.update(render_provider_content(provider, action, payload))
        provider_payload.setdefault("title", payload.get("title", ""))
        provider_payload.setdefault("description", payload.get("description", ""))
        if payload.get("severity") is not None:
            provider_payload.setdefault("severity", payload.get("severity"))
        if payload.get("category") is not None:
            provider_payload.setdefault("category", payload.get("category"))
        if payload.get("source") is not None:
            provider_payload.setdefault("source", payload.get("source"))

        if provider == "rackspace_core":
            provider_payload.setdefault("subject", payload.get("title", ""))
            provider_payload.setdefault("body", payload.get("description", ""))
            if settings.rackspace_core_default_queue:
                provider_payload.setdefault("queue", settings.rackspace_core_default_queue)
            if settings.rackspace_core_default_subcategory:
                provider_payload.setdefault(
                    "subcategory", settings.rackspace_core_default_subcategory
                )
        return provider_payload

    if ticket.provider_ticket_id:
        provider_payload.setdefault("ticket_id", ticket.provider_ticket_id)
    elif provider in {"teams", "discord"}:
        provider_payload.setdefault("ticket_id", ticket.internal_ticket_id)
    elif settings.ticketing_dry_run:
        # In dry-run mode we never require a provider-issued ID to proceed.
        provider_payload.setdefault("ticket_id", f"dryrun-{ticket.internal_ticket_id}")
    else:
        raise ValueError("Provider ticket id is not available yet for this ticket")

    if action == "update":
        if provider in {"teams", "discord"}:
            provider_payload.update(render_provider_content(provider, action, payload))
            provider_payload.setdefault(
                "message",
                _first_non_empty(
                    provider_payload.get("message"),
                    payload.get("message"),
                    payload.get("comment"),
                    payload.get("description"),
                    payload.get("title"),
                )
                or "PoundCake communication update.",
            )
            return provider_payload
        updates = provider_payload.get("updates")
        if not updates:
            updates = {}
            for field in ("title", "description", "severity", "category", "state"):
                if payload.get(field) is not None:
                    updates[field] = payload.get(field)
            if updates:
                provider_payload["updates"] = updates
        if provider == "rackspace_core" and updates:
            provider_payload.setdefault("attributes", updates)
        return provider_payload

    if action == "comment":
        provider_payload.update(render_provider_content(provider, action, payload))
        if provider in {"teams", "discord"}:
            provider_payload.setdefault(
                "message",
                _first_non_empty(
                    provider_payload.get("message"),
                    payload.get("comment"),
                    payload.get("message"),
                    payload.get("description"),
                    payload.get("title"),
                )
                or "PoundCake communication update.",
            )
            return provider_payload
        provider_payload.setdefault("comment", payload.get("comment", ""))
        if payload.get("visibility") is not None:
            provider_payload.setdefault("visibility", payload.get("visibility"))
        if payload.get("source") is not None:
            provider_payload.setdefault("source", payload.get("source"))
        return provider_payload

    if action == "close":
        provider_payload.update(render_provider_content(provider, action, payload))
        if provider in {"teams", "discord"}:
            provider_payload.setdefault(
                "message",
                _first_non_empty(
                    provider_payload.get("message"),
                    payload.get("message"),
                    payload.get("comment"),
                    payload.get("resolution_notes"),
                    payload.get("description"),
                    payload.get("title"),
                )
                or "PoundCake communication closed.",
            )
            return provider_payload
        if provider == "rackspace_core":
            status_hint = _first_non_empty(provider_payload.get("status"), payload.get("state"))
            normalized_hint = str(status_hint or "").strip().lower().replace("_", " ")
            if normalized_hint in {"", "closed"}:
                status_hint = (
                    settings.bakery_rackspace_confirmed_solved_status or "confirmed solved"
                )
            provider_payload.setdefault("status", str(status_hint).replace("_", " "))
        if payload.get("resolution_notes") is not None:
            provider_payload.setdefault("close_notes", payload.get("resolution_notes"))
        if payload.get("resolution_code") is not None:
            provider_payload.setdefault("resolution_code", payload.get("resolution_code"))
        if payload.get("state") is not None:
            provider_payload.setdefault("state", payload.get("state"))
        if payload.get("source") is not None:
            provider_payload.setdefault("source", payload.get("source"))
        return provider_payload

    raise ValueError(f"Unsupported action: {action}")


def _compute_backoff(attempt: int) -> int:
    raw = settings.worker_backoff_base_sec * int(math.pow(2, max(attempt - 1, 0)))
    return min(raw, settings.worker_backoff_max_sec)


def _missing_rackspace_core_create_fields(payload: dict[str, Any]) -> list[str]:
    required = ("account_number", "queue", "subcategory", "subject", "body")
    missing: list[str] = []
    for field in required:
        value = payload.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return missing


def _preflight_missing_fields(provider: str, action: str, payload: dict[str, Any]) -> list[str]:
    def missing(*fields: str) -> list[str]:
        out: list[str] = []
        for field in fields:
            value = payload.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                out.append(field)
        return out

    if provider == "rackspace_core":
        if action == "create":
            return _missing_rackspace_core_create_fields(payload)
        if action == "update":
            errors = missing("ticket_id")
            has_updates = _is_non_empty(payload.get("attributes")) or _is_non_empty(
                payload.get("updates")
            )
            if not has_updates:
                errors.append("attributes|updates")
            return errors
        if action == "close":
            return missing("ticket_id")
        if action == "comment":
            return missing("ticket_id", "comment")
        return []

    if provider == "servicenow":
        if action in {"update", "close"}:
            return missing("ticket_id")
        if action == "comment":
            return missing("ticket_id", "comment")
        return []

    if provider == "jira":
        if action == "create":
            return missing("project_key")
        if action in {"update", "close"}:
            return missing("ticket_id")
        if action == "comment":
            return missing("ticket_id", "comment")
        return []

    if provider == "github":
        if action == "create":
            return missing("owner", "repo")
        if action in {"update", "close"}:
            return missing("owner", "repo", "ticket_id")
        if action == "comment":
            return missing("owner", "repo", "ticket_id", "comment")
        return []

    if provider == "pagerduty":
        if action == "create":
            return missing("service_id", "from_email")
        if action in {"update", "close"}:
            return missing("ticket_id", "from_email")
        if action == "comment":
            return missing("ticket_id", "from_email", "comment")
        return []

    if provider in {"teams", "discord"}:
        if action in {"create", "update", "close", "comment"}:
            return missing("message")
        return []

    return []


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
            if (ticket.provider_type or settings.active_provider) == "rackspace_core":
                normalized_payload = operation.normalized_payload or {}
                requested_state = str(
                    normalized_payload.get("status")
                    or normalized_payload.get("state")
                    or (operation.request_payload or {}).get("state")
                    or ""
                ).lower()
                if requested_state.replace(" ", "_") == "confirmed_solved":
                    ticket.state = "confirmed_solved"
                else:
                    ticket.state = "closed"
            else:
                ticket.state = "closed"
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
    provider = str(ticket.provider_type or settings.active_provider or "").strip().lower()
    payload = _build_provider_payload(operation.action, ticket, operation.request_payload)
    _persist_normalized_payload(operation.operation_id, payload)
    missing = _preflight_missing_fields(provider, operation.action, payload)
    if missing:
        error = f"{provider} {operation.action} missing required fields: " + ", ".join(missing)
        logger.error(
            "Provider preflight validation failed",
            operation_id=operation.operation_id,
            ticket_id=operation.internal_ticket_id,
            provider=provider,
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
            provider=provider,
        )
        result = _build_dry_run_result(operation, ticket, payload)
    else:
        mixer = get_mixer(provider)
        result = asyncio.run(mixer.process_request(operation.action, payload))
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
    while True:
        if time.monotonic() >= next_monitor_sweep:
            try:
                _run_monitor_sweep()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Monitor sweep failed", error=str(exc))
            next_monitor_sweep = time.monotonic() + settings.bakery_monitor_sweep_interval_sec

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
