"""Regression tests for Bakery operator-auth session persistence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from bakery.operator_auth import get_session, pop_state


class _FakeQuery:
    def __init__(self, row):
        self._row = row

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._row


class _FakeDb:
    def __init__(self, row):
        self._row = row
        self.deleted = []
        self.flushed = False

    def query(self, model):
        return _FakeQuery(self._row)

    def delete(self, row) -> None:
        self.deleted.append(row)

    def flush(self) -> None:
        self.flushed = True


def test_get_session_accepts_naive_expiry_from_database() -> None:
    row = SimpleNamespace(
        provider="local",
        subject_id="bakery-admin",
        username="bakery-admin",
        display_name="bakery-admin",
        role="admin",
        principal_type="user",
        principal_id=None,
        is_superuser=True,
        groups_json=[],
        permissions_json=["read", "superuser"],
        session_id="sess-123",
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=15)).replace(tzinfo=None),
    )
    db = _FakeDb(row)

    context = get_session(db, "sess-123")

    assert context is not None
    assert context.session_id == "sess-123"
    assert context.expires_at.endswith("+00:00")
    assert db.deleted == []


def test_pop_state_accepts_naive_expiry_from_database() -> None:
    row = SimpleNamespace(
        payload_json={"next": "https://api.ord.jakelab.info"},
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).replace(tzinfo=None),
    )
    db = _FakeDb(row)

    payload = pop_state(db, kind="oidc_state", state_key="state-123")

    assert payload == {"next": "https://api.ord.jakelab.info"}
    assert db.deleted == [row]
    assert db.flushed is True
