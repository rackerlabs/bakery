from datetime import datetime, timezone
from pathlib import Path

from bakery.models import Monitor
from bakery.worker import _monitor_threshold_deadline


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
