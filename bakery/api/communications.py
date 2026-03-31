#!/usr/bin/env python3
"""Provider-agnostic communication API endpoints for Bakery."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from bakery.api.tickets import (
    _enqueue_ticket_action_request,
    create_ticket_request,
    find_ticket_request,
    get_operation,
    get_ticket_operations,
    get_ticket_request,
)
from bakery.auth import MonitorAuthContext, require_monitor_hmac_auth
from bakery.database import get_db
from bakery.schemas import (
    TicketCloseRequest,
    TicketCommentRequest,
    TicketCreateRequest,
    TicketUpdateRequest,
)
from shared.bakery_contract import (
    CommunicationAcceptedResponse,
    CommunicationCloseRequest,
    CommunicationNotifyRequest,
    CommunicationOpenRequest,
    CommunicationOperationListResponse,
    CommunicationOperationResponse,
    CommunicationResponse,
    CommunicationUpdateRequest,
)

router = APIRouter()


def _monitor_uuid(auth: MonitorAuthContext | object) -> str | None:
    return auth.monitor_uuid if isinstance(auth, MonitorAuthContext) else None


async def create_ticket(**kwargs):
    return await create_ticket_request(**kwargs)


async def update_ticket(**kwargs):
    payload = kwargs.pop("payload")
    return _enqueue_ticket_action_request(
        request_payload=payload.model_dump(),
        **kwargs,
    )


async def add_comment(**kwargs):
    payload = kwargs.pop("payload")
    return _enqueue_ticket_action_request(
        request_payload=payload.model_dump(),
        **kwargs,
    )


async def close_ticket(**kwargs):
    payload = kwargs.pop("payload")
    return _enqueue_ticket_action_request(
        request_payload=payload.model_dump(),
        **kwargs,
    )


async def get_ticket(**kwargs):
    return await get_ticket_request(**kwargs)


async def find_ticket(**kwargs):
    return await find_ticket_request(**kwargs)


def _map_accepted(ticket_response) -> CommunicationAcceptedResponse:
    return CommunicationAcceptedResponse(
        communication_id=ticket_response.ticket_id,
        operation_id=ticket_response.operation_id,
        action=ticket_response.action,
        status=ticket_response.status,
        created_at=ticket_response.created_at,
    )


def _map_ticket(ticket_response) -> CommunicationResponse:
    return CommunicationResponse(
        communication_id=ticket_response.ticket_id,
        provider_type=ticket_response.provider_type,
        provider_reference_id=ticket_response.provider_ticket_id,
        state=ticket_response.state,
        latest_error=ticket_response.latest_error,
        created_at=ticket_response.created_at,
        updated_at=ticket_response.updated_at,
        data_source=ticket_response.data_source,
        communication_data=ticket_response.ticket_data,
        last_sync_operation_id=ticket_response.last_sync_operation_id,
        last_sync_at=ticket_response.last_sync_at,
    )


def _map_operation(ticket_response) -> CommunicationOperationResponse:
    return CommunicationOperationResponse(
        operation_id=ticket_response.operation_id,
        communication_id=ticket_response.ticket_id,
        action=ticket_response.action,
        status=ticket_response.status,
        attempt_count=ticket_response.attempt_count,
        max_attempts=ticket_response.max_attempts,
        next_attempt_at=ticket_response.next_attempt_at,
        started_at=ticket_response.started_at,
        completed_at=ticket_response.completed_at,
        last_error=ticket_response.last_error,
        provider_response=ticket_response.provider_response,
        created_at=ticket_response.created_at,
        updated_at=ticket_response.updated_at,
    )


@router.post("/communications", response_model=CommunicationAcceptedResponse, status_code=202)
async def open_communication(
    payload: CommunicationOpenRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    auth: MonitorAuthContext = Depends(require_monitor_hmac_auth),
    db: Session = Depends(get_db),
) -> CommunicationAcceptedResponse:
    accepted = await create_ticket(
        payload=TicketCreateRequest(**payload.model_dump()),
        idempotency_key=idempotency_key or "",
        db=db,
        monitor_uuid=_monitor_uuid(auth),
    )
    return _map_accepted(accepted)


@router.patch(
    "/communications/{communication_id}",
    response_model=CommunicationAcceptedResponse,
    status_code=202,
)
async def update_communication(
    communication_id: str,
    payload: CommunicationUpdateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    auth: MonitorAuthContext = Depends(require_monitor_hmac_auth),
    db: Session = Depends(get_db),
) -> CommunicationAcceptedResponse:
    accepted = await update_ticket(
        db=db,
        ticket_id=communication_id,
        action="update",
        payload=TicketUpdateRequest(**payload.model_dump()),
        idempotency_key=idempotency_key or "",
        monitor_uuid=_monitor_uuid(auth),
    )
    return _map_accepted(accepted)


@router.post(
    "/communications/{communication_id}/notifications",
    response_model=CommunicationAcceptedResponse,
    status_code=202,
)
async def notify_communication(
    communication_id: str,
    payload: CommunicationNotifyRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    auth: MonitorAuthContext = Depends(require_monitor_hmac_auth),
    db: Session = Depends(get_db),
) -> CommunicationAcceptedResponse:
    accepted = await add_comment(
        db=db,
        ticket_id=communication_id,
        action="comment",
        payload=TicketCommentRequest(
            comment=payload.comment or payload.message or "",
            visibility=payload.visibility,
            context=payload.context,
        ),
        idempotency_key=idempotency_key or "",
        monitor_uuid=_monitor_uuid(auth),
    )
    return _map_accepted(accepted)


@router.post(
    "/communications/{communication_id}/close",
    response_model=CommunicationAcceptedResponse,
    status_code=202,
)
async def close_communication(
    communication_id: str,
    payload: CommunicationCloseRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    auth: MonitorAuthContext = Depends(require_monitor_hmac_auth),
    db: Session = Depends(get_db),
) -> CommunicationAcceptedResponse:
    accepted = await close_ticket(
        db=db,
        ticket_id=communication_id,
        action="close",
        payload=TicketCloseRequest(**payload.model_dump()),
        idempotency_key=idempotency_key or "",
        monitor_uuid=_monitor_uuid(auth),
    )
    return _map_accepted(accepted)


@router.get("/communications/{communication_id}", response_model=CommunicationResponse)
async def get_communication(
    communication_id: str,
    auth: MonitorAuthContext = Depends(require_monitor_hmac_auth),
    db: Session = Depends(get_db),
) -> CommunicationResponse:
    ticket = await get_ticket(ticket_id=communication_id, db=db, monitor_uuid=_monitor_uuid(auth))
    return _map_ticket(ticket)


@router.post("/communications/{communication_id}/sync", response_model=CommunicationResponse)
async def sync_communication(
    communication_id: str,
    auth: MonitorAuthContext = Depends(require_monitor_hmac_auth),
    db: Session = Depends(get_db),
) -> CommunicationResponse:
    ticket = await find_ticket(ticket_id=communication_id, db=db, monitor_uuid=_monitor_uuid(auth))
    return _map_ticket(ticket)


@router.get(
    "/communications/{communication_id}/operations",
    response_model=CommunicationOperationListResponse,
)
async def get_communication_operations(
    communication_id: str,
    limit: int = 100,
    auth: MonitorAuthContext = Depends(require_monitor_hmac_auth),
    db: Session = Depends(get_db),
) -> CommunicationOperationListResponse:
    operations = await get_ticket_operations(
        ticket_id=communication_id, limit=limit, auth=auth, db=db
    )
    return CommunicationOperationListResponse(
        communication_id=operations.ticket_id,
        operations=[_map_operation(item) for item in operations.operations],
        count=operations.count,
    )


@router.get(
    "/communications/operations/{operation_id}",
    response_model=CommunicationOperationResponse,
)
async def get_communication_operation(
    operation_id: str,
    auth: MonitorAuthContext = Depends(require_monitor_hmac_auth),
    db: Session = Depends(get_db),
) -> CommunicationOperationResponse:
    operation = await get_operation(operation_id=operation_id, auth=auth, db=db)
    return _map_operation(operation)
