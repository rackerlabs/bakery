from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from bakery.api import communications
from bakery.schemas import (
    OperationAcceptedResponse,
    TicketCloseRequest,
    TicketCommentRequest,
    TicketCreateRequest,
    TicketUpdateRequest,
)
from shared.bakery_contract import (
    CommunicationNotifyRequest,
    CommunicationResponse,
)


@pytest.mark.asyncio
async def test_open_communication_maps_ticket_create_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    create_ticket = AsyncMock(
        return_value=OperationAcceptedResponse(
            ticket_id="comm-1",
            operation_id="op-1",
            action="create",
            status="queued",
            created_at=now,
        )
    )
    monkeypatch.setattr(communications, "create_ticket", create_ticket)

    response = await communications.open_communication(
        payload=communications.CommunicationOpenRequest(
            title="Disk alert",
            description="details",
            message="Manual attention may be required.",
            source="poundcake",
        ),
        idempotency_key="idem-1",
        db=None,
    )

    assert response.communication_id == "comm-1"
    assert response.operation_id == "op-1"
    assert response.action == "create"

    sent_payload = create_ticket.await_args.kwargs["payload"]
    assert isinstance(sent_payload, TicketCreateRequest)
    assert sent_payload.message == "Manual attention may be required."
    assert sent_payload.source == "poundcake"


@pytest.mark.asyncio
async def test_update_communication_maps_ticket_update_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    update_ticket = AsyncMock(
        return_value=OperationAcceptedResponse(
            ticket_id="comm-7",
            operation_id="op-7",
            action="update",
            status="queued",
            created_at=now,
        )
    )
    monkeypatch.setattr(communications, "update_ticket", update_ticket)

    response = await communications.update_communication(
        communication_id="comm-7",
        payload=communications.CommunicationUpdateRequest(
            title="Updated title",
            description="Updated description",
            state="acknowledged",
        ),
        idempotency_key="idem-7",
        db=None,
    )

    assert response.communication_id == "comm-7"

    sent_payload = update_ticket.await_args.kwargs["payload"]
    assert isinstance(sent_payload, TicketUpdateRequest)
    assert sent_payload.title == "Updated title"
    assert sent_payload.state == "acknowledged"


@pytest.mark.asyncio
async def test_notify_communication_maps_message_to_comment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    add_comment = AsyncMock(
        return_value=OperationAcceptedResponse(
            ticket_id="comm-2",
            operation_id="op-2",
            action="comment",
            status="queued",
            created_at=now,
        )
    )
    monkeypatch.setattr(communications, "add_comment", add_comment)

    response = await communications.notify_communication(
        communication_id="comm-2",
        payload=CommunicationNotifyRequest(comment="manual action required"),
        idempotency_key="idem-2",
        db=None,
    )

    assert response.communication_id == "comm-2"

    sent_payload = add_comment.await_args.kwargs["payload"]
    assert isinstance(sent_payload, TicketCommentRequest)
    assert sent_payload.comment == "manual action required"


@pytest.mark.asyncio
async def test_close_communication_maps_managed_payload_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    close_ticket = AsyncMock(
        return_value=OperationAcceptedResponse(
            ticket_id="comm-9",
            operation_id="op-9",
            action="close",
            status="queued",
            created_at=now,
        )
    )
    monkeypatch.setattr(communications, "close_ticket", close_ticket)

    response = await communications.close_communication(
        communication_id="comm-9",
        payload=communications.CommunicationCloseRequest(
            title="Alert resolved",
            description="Bakery is closing this communication.",
            message="Alert resolved after successful auto-remediation.",
            source="poundcake",
            state="closed",
            context={"route_label": "Rackspace Core"},
        ),
        idempotency_key="idem-9",
        db=None,
    )

    assert response.communication_id == "comm-9"

    sent_payload = close_ticket.await_args.kwargs["payload"]
    assert isinstance(sent_payload, TicketCloseRequest)
    assert sent_payload.title == "Alert resolved"
    assert sent_payload.message == "Alert resolved after successful auto-remediation."
    assert sent_payload.source == "poundcake"


def test_communication_response_supports_agnostic_metadata() -> None:
    now = datetime.now(timezone.utc)
    payload = CommunicationResponse(
        communication_id="comm-3",
        provider_type="rackspace_core",
        provider_reference_id="240101-00001",
        state="open",
        latest_error=None,
        created_at=now,
        updated_at=now,
        data_source="local_cache",
        communication_data={"title": "Disk alert"},
        last_sync_operation_id="op-3",
        last_sync_at=now,
    )

    assert payload.communication_data == {"title": "Disk alert"}
    assert payload.provider_reference_id == "240101-00001"
