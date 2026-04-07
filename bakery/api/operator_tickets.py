#!/usr/bin/env python3
"""Operator-authenticated ticket inspection and backlog management APIs."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from bakery.api.tickets import (
    _enqueue_ticket_action_request,
    _load_owned_ticket,
    _load_ticket_operations,
    _op_response,
    close_ticket_locally,
    find_ticket_request,
    get_ticket_request,
)
from bakery.database import get_db
from bakery.operator_auth import AuthContext, has_permission, require_operator
from bakery.schemas import (
    OperationAcceptedResponse,
    TicketCloseRequest,
    TicketOperationListResponse,
    TicketResponse,
)
from bakery.ticket_backlog import ticket_can_close, ticket_can_resync, ticket_is_dry_run

router = APIRouter()


def require_backlog_manager(context: AuthContext = Depends(require_operator)) -> AuthContext:
    if not has_permission(context, "manage_backlog"):
        raise HTTPException(status_code=403, detail="Backlog management access required")
    return context


def _owned_ticket(db: Session, ticket_id: str):
    return _load_owned_ticket(db, ticket_id, monitor_uuid=None, enforce_monitor=False)


@router.get("/operator/tickets/{ticket_id}", response_model=TicketResponse)
async def get_operator_ticket(
    ticket_id: str,
    _context: AuthContext = Depends(require_backlog_manager),
    db: Session = Depends(get_db),
) -> TicketResponse:
    return await get_ticket_request(ticket_id, db=db, monitor_uuid=None)


@router.get("/operator/tickets/{ticket_id}/operations", response_model=TicketOperationListResponse)
async def get_operator_ticket_operations(
    ticket_id: str,
    limit: int = 100,
    _context: AuthContext = Depends(require_backlog_manager),
    db: Session = Depends(get_db),
) -> TicketOperationListResponse:
    _owned_ticket(db, ticket_id)
    operations = _load_ticket_operations(db, ticket_id, limit=limit)
    return TicketOperationListResponse(
        ticket_id=ticket_id,
        operations=[_op_response(operation) for operation in operations],
        count=len(operations),
    )


@router.post("/operator/tickets/{ticket_id}/find", response_model=TicketResponse)
async def find_operator_ticket(
    ticket_id: str,
    _context: AuthContext = Depends(require_backlog_manager),
    db: Session = Depends(get_db),
) -> TicketResponse:
    ticket = _owned_ticket(db, ticket_id)
    operations = _load_ticket_operations(db, ticket_id, limit=500)
    if not ticket_can_resync(ticket, operations):
        raise HTTPException(status_code=409, detail="Ticket is not eligible for resync")
    return await find_ticket_request(ticket_id, db=db, monitor_uuid=None)


@router.post(
    "/operator/tickets/{ticket_id}/close",
    response_model=OperationAcceptedResponse,
    status_code=202,
)
async def close_operator_ticket(
    ticket_id: str,
    payload: TicketCloseRequest,
    _context: AuthContext = Depends(require_backlog_manager),
    db: Session = Depends(get_db),
) -> OperationAcceptedResponse:
    ticket = _owned_ticket(db, ticket_id)
    operations = _load_ticket_operations(db, ticket_id, limit=500)
    if not ticket_can_close(ticket, operations):
        raise HTTPException(status_code=409, detail="Ticket is not eligible for close")
    request_payload = payload.model_dump(exclude_none=True)
    if ticket_is_dry_run(ticket, operations):
        return close_ticket_locally(db, ticket=ticket, request_payload=request_payload)
    return _enqueue_ticket_action_request(
        db,
        ticket_id,
        "close",
        request_payload,
        str(uuid.uuid4()),
        monitor_uuid=None,
        validate_route=False,
        enforce_monitor=False,
    )
