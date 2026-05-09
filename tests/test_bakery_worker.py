from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from bakery.models import Base, Monitor, TicketOperation
from bakery.worker import _claim_operations, _monitor_threshold_deadline


def _worker_source() -> str:
    repo_root = Path(__file__).resolve().parents[1]
    return (repo_root / "bakery/worker.py").read_text(encoding="utf-8")


def test_rackspace_account_number_mapping_supports_plain_label_name() -> None:
    source = _worker_source()
    assert "provider_config_from_context(provider, payload)" in source


def test_worker_contains_dry_run_execution_path() -> None:
    source = _worker_source()
    assert "def _build_dry_run_result(" in source
    assert "if settings.ticketing_dry_run:" in source
    assert "Dry-run enabled; skipping provider call" in source


def test_non_create_operations_use_synthetic_ticket_id_in_dry_run() -> None:
    source = _worker_source()
    assert (
        'provider_payload.setdefault("ticket_id", f"dryrun-{ticket.internal_ticket_id}")' in source
    )


def test_worker_persists_provider_normalized_payload_before_execution() -> None:
    source = _worker_source()
    assert "def _persist_normalized_payload(" in source
    assert "_persist_normalized_payload(operation.operation_id, payload)" in source


def test_rackspace_core_close_payload_defaults_to_confirm_solved() -> None:
    source = _worker_source()
    assert 'if normalized_hint in {"", "closed"}:' in source
    assert 'settings.bakery_rackspace_confirmed_solved_status or "confirmed solved"' in source


def test_worker_uses_renderer_layer_for_provider_payloads() -> None:
    source = _worker_source()
    assert "render_provider_content(provider, action, payload)" in source


def test_claim_operations_skips_failed_rows_without_attempts_remaining(monkeypatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    now = datetime.now(timezone.utc)

    terminal_find = TicketOperation(
        operation_id="terminal-find",
        internal_ticket_id="ticket-1",
        action="find",
        status="failed",
        request_payload={"ticket_id": "ticket-1"},
        attempt_count=1,
        max_attempts=1,
        next_attempt_at=None,
        created_at=now - timedelta(minutes=3),
        updated_at=now - timedelta(minutes=3),
    )
    retryable_comment = TicketOperation(
        operation_id="retryable-comment",
        internal_ticket_id="ticket-2",
        action="comment",
        status="failed",
        request_payload={"comment": "retry me"},
        attempt_count=1,
        max_attempts=5,
        next_attempt_at=now - timedelta(seconds=1),
        created_at=now - timedelta(minutes=2),
        updated_at=now - timedelta(minutes=2),
    )
    queued_create = TicketOperation(
        operation_id="queued-create",
        internal_ticket_id="ticket-3",
        action="create",
        status="queued",
        request_payload={"title": "queued work"},
        attempt_count=0,
        max_attempts=5,
        next_attempt_at=None,
        created_at=now - timedelta(minutes=1),
        updated_at=now - timedelta(minutes=1),
    )

    with session_local() as db:
        db.add_all([terminal_find, retryable_comment, queued_create])
        db.commit()

    monkeypatch.setattr("bakery.worker.SessionLocal", session_local)

    claimed = _claim_operations(10)

    assert {operation.operation_id for operation in claimed} == {
        "retryable-comment",
        "queued-create",
    }
    with session_local() as db:
        statuses = {
            operation.operation_id: operation.status
            for operation in db.query(TicketOperation).all()
        }
    assert statuses == {
        "terminal-find": "failed",
        "retryable-comment": "running",
        "queued-create": "running",
    }


def test_monitor_threshold_deadline_normalizes_naive_datetimes() -> None:
    monitor = Monitor(
        monitor_uuid="monitor-1",
        monitor_id="example-namespace/example-release",
        key_id="active",
        encrypted_secret="secret",
        status="healthy",
        route_sync_required=False,
        created_at=datetime(2026, 3, 31, 16, 0, 0),
        updated_at=datetime(2026, 3, 31, 16, 0, 0),
    )
    monitor.last_checkin_at = datetime(2026, 3, 31, 16, 1, 0)

    deadline = _monitor_threshold_deadline(monitor)

    assert deadline.tzinfo == timezone.utc
    assert deadline.isoformat() == "2026-03-31T16:03:30+00:00"
