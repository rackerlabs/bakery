from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from bakery.api import communications, tickets as ticket_api
from bakery.database import Base
from bakery.models import Ticket


def _db_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return session_local()


def _seed_ticket(
    db: Session,
    *,
    ticket_id: str,
    provider_type: str,
    provider_ticket_id: str,
    state: str = "open",
) -> Ticket:
    now = datetime.now(timezone.utc)
    ticket = Ticket(
        internal_ticket_id=ticket_id,
        provider_type=provider_type,
        provider_ticket_id=provider_ticket_id,
        state=state,
        created_at=now,
        updated_at=now,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


@pytest.mark.asyncio
async def test_find_ticket_request_persists_confirmed_solved_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _db_session()
    _seed_ticket(
        db,
        ticket_id="ticket-core-1",
        provider_type="rackspace_core",
        provider_ticket_id="260331-02458",
    )

    class _FakeMixer:
        async def process_request(
            self, action: str, payload: dict[str, object]
        ) -> dict[str, object]:
            assert action == "search"
            assert payload == {
                "ticket_number": "260331-02458",
                "attributes": ["number", "subject", "status.name", "is_closed", "is_closeable"],
            }
            return {
                "success": True,
                "data": {
                    "results": [
                        {
                            "number": "260331-02458",
                            "status.name": "Confirm Solved",
                        }
                    ]
                },
            }

    monkeypatch.setattr(ticket_api, "get_mixer", lambda provider: _FakeMixer())

    response = await ticket_api.find_ticket_request("ticket-core-1", db=db, monitor_uuid=None)
    cached = await ticket_api.get_ticket_request("ticket-core-1", db=db, monitor_uuid=None)
    ticket = db.query(Ticket).filter(Ticket.internal_ticket_id == "ticket-core-1").first()

    assert response.data_source == "provider"
    assert response.state == "confirmed_solved"
    assert cached.state == "confirmed_solved"
    assert ticket is not None
    assert ticket.state == "confirmed_solved"
    assert ticket.latest_error is None


@pytest.mark.asyncio
async def test_sync_communication_maps_resolved_provider_state_to_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _db_session()
    _seed_ticket(
        db,
        ticket_id="ticket-pd-1",
        provider_type="pagerduty",
        provider_ticket_id="PD123",
    )

    class _FakeMixer:
        async def process_request(
            self, action: str, payload: dict[str, object]
        ) -> dict[str, object]:
            assert action == "search"
            assert payload["statuses"] == ["triggered", "acknowledged", "resolved"]
            return {
                "success": True,
                "data": {
                    "results": [
                        {
                            "id": "PD123",
                            "status": "resolved",
                        }
                    ]
                },
            }

    monkeypatch.setattr(ticket_api, "get_mixer", lambda provider: _FakeMixer())

    synced = await communications.sync_communication(
        communication_id="ticket-pd-1",
        auth=object(),
        db=db,
    )
    cached = await communications.get_communication(
        communication_id="ticket-pd-1",
        auth=object(),
        db=db,
    )
    ticket = db.query(Ticket).filter(Ticket.internal_ticket_id == "ticket-pd-1").first()

    assert synced.state == "closed"
    assert synced.data_source == "provider"
    assert cached.state == "closed"
    assert ticket is not None
    assert ticket.state == "closed"
