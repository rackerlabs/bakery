#!/usr/bin/env python3
"""Helpers for operator backlog classification and actions."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from sqlalchemy.orm import Session

from bakery.models import Monitor, Ticket, TicketOperation
from bakery.schemas import TicketBacklogResponse

_CLOSED_STATES = {"closed", "confirmed_solved"}


def _provider_response_data(operation: TicketOperation) -> dict[str, object]:
    payload = operation.provider_response
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    if not isinstance(data, dict):
        return {}
    return data


def load_ticket_operations_map(
    db: Session,
    *,
    ticket_ids: Iterable[str],
) -> dict[str, list[TicketOperation]]:
    ids = [str(ticket_id) for ticket_id in ticket_ids if str(ticket_id or "").strip()]
    if not ids:
        return {}
    rows = (
        db.query(TicketOperation)
        .filter(TicketOperation.internal_ticket_id.in_(ids))
        .order_by(TicketOperation.created_at.desc(), TicketOperation.id.desc())
        .all()
    )
    operations_by_ticket: dict[str, list[TicketOperation]] = defaultdict(list)
    for row in rows:
        operations_by_ticket[row.internal_ticket_id].append(row)
    return dict(operations_by_ticket)


def ticket_is_closed(ticket: Ticket) -> bool:
    return str(ticket.state or "").strip().lower() in _CLOSED_STATES


def ticket_is_dry_run(ticket: Ticket, operations: list[TicketOperation]) -> bool:
    provider_ticket_id = str(ticket.provider_ticket_id or "").strip().lower()
    if provider_ticket_id.startswith("dryrun-"):
        return True
    return any(_provider_response_data(operation).get("dry_run") is True for operation in operations)


def ticket_backlog_reason(ticket: Ticket, operations: list[TicketOperation]) -> str:
    if ticket_is_dry_run(ticket, operations):
        return "dry_run"
    if str(ticket.state or "").strip().lower() == "error" or ticket.latest_error:
        return "error"
    return "open"


def ticket_can_resync(ticket: Ticket, operations: list[TicketOperation]) -> bool:
    if ticket_is_closed(ticket) or ticket_is_dry_run(ticket, operations):
        return False
    return bool(str(ticket.provider_ticket_id or "").strip()) and (
        str(ticket.state or "").strip().lower() == "error" or ticket.latest_error is not None
    )


def ticket_can_close(ticket: Ticket, operations: list[TicketOperation]) -> bool:
    if ticket_is_closed(ticket):
        return False
    if ticket_is_dry_run(ticket, operations):
        return True
    return bool(str(ticket.provider_ticket_id or "").strip()) and (
        str(ticket.state or "").strip().lower() == "error" or ticket.latest_error is not None
    )


def build_ticket_backlog_response(
    ticket: Ticket,
    monitor: Monitor | None,
    operations: list[TicketOperation],
) -> TicketBacklogResponse:
    return TicketBacklogResponse(
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
        is_dry_run=ticket_is_dry_run(ticket, operations),
        backlog_reason=ticket_backlog_reason(ticket, operations),
        can_close=ticket_can_close(ticket, operations),
        can_resync=ticket_can_resync(ticket, operations),
    )
