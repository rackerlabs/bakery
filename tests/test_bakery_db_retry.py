from __future__ import annotations

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from bakery.database import (
    RECORD_CHANGED_MYSQL_ERRNO,
    commit_with_record_changed_retry_async,
    is_record_changed_error,
)


def _record_changed_operational_error() -> OperationalError:
    return OperationalError(
        "UPDATE tickets SET updated_at=%(updated_at)s WHERE tickets.id = %(tickets_id)s",
        {},
        Exception(RECORD_CHANGED_MYSQL_ERRNO, "Record has changed since last read in table 'tickets'"),
    )


def test_is_record_changed_error_detects_mariadb_errno() -> None:
    assert is_record_changed_error(_record_changed_operational_error())


def test_is_record_changed_error_ignores_other_operational_errors() -> None:
    other = OperationalError("SELECT 1", {}, Exception(1205, "Lock wait timeout exceeded"))
    assert not is_record_changed_error(other)


@pytest.mark.asyncio
async def test_commit_with_record_changed_retry_async_retries_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    class _FakeSession:
        rollbacks = 0

        def rollback(self) -> None:
            self.rollbacks += 1

    db = _FakeSession()

    async def _fast_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("bakery.database.asyncio.sleep", _fast_sleep)

    def persist() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _record_changed_operational_error()
        return "ok"

    result = await commit_with_record_changed_retry_async(db, persist)  # type: ignore[arg-type]

    assert result == "ok"
    assert attempts == 2
    assert db.rollbacks == 1


@pytest.mark.asyncio
async def test_commit_with_record_changed_retry_async_reraises_after_max_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeSession:
        def rollback(self) -> None:
            return None

    db = _FakeSession()

    async def _fast_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("bakery.database.asyncio.sleep", _fast_sleep)

    def persist() -> str:
        raise _record_changed_operational_error()

    with pytest.raises(OperationalError):
        await commit_with_record_changed_retry_async(  # type: ignore[arg-type]
            db,
            persist,
            max_attempts=3,
        )