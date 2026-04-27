"""Regression tests for the Bakery operator reporting APIs."""

from __future__ import annotations

import importlib
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from bakery.api import tickets as ticket_api
from bakery.auth import require_bootstrap_admin_access
from bakery.database import Base, get_db
from bakery.models import (
    CollectionJob,
    Monitor,
    MonitorBootstrapCredential,
    MonitorEvent,
    MonitorOutageRouteState,
    MonitorRouteCatalogEntry,
    Ticket,
    TicketOperation,
)
from bakery.operator_auth import AuthContext, require_operator, require_reader


def _load_app(monkeypatch):
    sys.modules.pop("bakery.main", None)
    fake_structlog = types.SimpleNamespace(
        configure=lambda **kwargs: None,
        get_logger=lambda *args, **kwargs: types.SimpleNamespace(
            info=lambda *a, **k: None,
            error=lambda *a, **k: None,
        ),
        stdlib=types.SimpleNamespace(
            filter_by_level=object(),
            add_logger_name=object(),
            add_log_level=object(),
            PositionalArgumentsFormatter=lambda *a, **k: object(),
            BoundLogger=object,
            LoggerFactory=lambda *a, **k: object(),
        ),
        processors=types.SimpleNamespace(
            TimeStamper=lambda *a, **k: object(),
            StackInfoRenderer=lambda *a, **k: object(),
            format_exc_info=object(),
            UnicodeDecoder=lambda *a, **k: object(),
            JSONRenderer=lambda *a, **k: object(),
        ),
    )
    monkeypatch.setitem(sys.modules, "structlog", fake_structlog)
    return importlib.import_module("bakery.main").app


def _auth_context() -> AuthContext:
    return AuthContext(
        provider="local",
        subject_id="user-123",
        username="operator",
        display_name="Operator",
        groups=[],
        role="admin",
        principal_type="user",
        permissions=["read", "queue_jobs", "manage_backlog"],
        session_id="session-123",
        expires_at="2030-01-01T00:00:00Z",
    )


def _seed_reporting_data(db: Session) -> None:
    now = datetime.now(timezone.utc)
    monitor_one = Monitor(
        monitor_uuid="monitor-uuid-1",
        monitor_id="alpha-monitor",
        key_id="key-1",
        encrypted_secret="secret-1",
        status="healthy",
        route_sync_required=False,
        environment_label="prod",
        region="region-a",
        cluster_name="cluster-a",
        namespace="example-namespace",
        release_name="example-release",
        tags_json=["primary", "region-a"],
        last_checkin_at=now - timedelta(minutes=2),
        created_at=now - timedelta(days=2),
        updated_at=now - timedelta(minutes=1),
        last_seen_payload={"version": "2.0.183"},
    )
    monitor_two = Monitor(
        monitor_uuid="monitor-uuid-2",
        monitor_id="beta-monitor",
        key_id="key-2",
        encrypted_secret="secret-2",
        status="unreachable",
        route_sync_required=True,
        environment_label="stage",
        region="region-b",
        cluster_name="cluster-b",
        namespace="example-stage",
        release_name="example-release-stage",
        tags_json=["stage"],
        last_checkin_at=now - timedelta(hours=3),
        unreachable_at=now - timedelta(hours=2),
        created_at=now - timedelta(days=2),
        updated_at=now - timedelta(hours=2),
    )
    db.add_all([monitor_one, monitor_two])

    db.add_all(
        [
            MonitorRouteCatalogEntry(
                monitor_uuid=monitor_one.monitor_uuid,
                scope="workload",
                owner_key="region-a/example-namespace",
                route_id="servicenow-ticket",
                label="ServiceNow create",
                execution_target="ticket",
                provider_type="servicenow",
                destination_target="incident-create",
                account_number="123456",
                queue="servicenow.create",
                subcategory="incident",
                enabled=True,
                outage_enabled=True,
                position=1,
                created_at=now - timedelta(days=1),
                updated_at=now - timedelta(minutes=5),
            ),
            MonitorRouteCatalogEntry(
                monitor_uuid=monitor_two.monitor_uuid,
                scope="workload",
                owner_key="region-b/example-stage",
                route_id="jira-ticket",
                label="Jira create",
                execution_target="ticket",
                provider_type="jira",
                destination_target="issue-create",
                account_number="654321",
                queue="jira.create",
                subcategory="issue",
                enabled=True,
                outage_enabled=False,
                position=1,
                created_at=now - timedelta(days=1),
                updated_at=now - timedelta(hours=1),
            ),
        ]
    )

    db.add(
        MonitorEvent(
            monitor_uuid=monitor_one.monitor_uuid,
            event_type="heartbeat_received",
            payload={"status": "healthy"},
            created_at=now - timedelta(minutes=3),
        )
    )
    db.add(
        MonitorOutageRouteState(
            monitor_uuid=monitor_one.monitor_uuid,
            scope="workload",
            owner_key="region-a/example-namespace",
            route_id="servicenow-ticket",
            ticket_id="ticket-123",
            last_state="healthy",
            created_at=now - timedelta(hours=1),
            updated_at=now - timedelta(hours=1),
        )
    )
    db.add(
        MonitorBootstrapCredential(
            monitor_id=monitor_one.monitor_id,
            key_id="bootstrap",
            encrypted_secret="encrypted-bootstrap-secret",
            created_at=now - timedelta(days=2),
            updated_at=now - timedelta(days=2),
        )
    )

    db.add(
        Ticket(
            internal_ticket_id="ticket-123",
            provider_type="servicenow",
            provider_ticket_id="INC00123",
            monitor_uuid=monitor_one.monitor_uuid,
            state="open",
            latest_error="Awaiting provider retry",
            created_at=now - timedelta(hours=6),
            updated_at=now - timedelta(minutes=8),
        )
    )
    db.add(
        Ticket(
            internal_ticket_id="ticket-dryrun",
            provider_type="rackspace_core",
            provider_ticket_id="dryrun-ticket-dryrun",
            monitor_uuid=monitor_one.monitor_uuid,
            state="open",
            latest_error=None,
            created_at=now - timedelta(hours=2),
            updated_at=now - timedelta(minutes=6),
        )
    )
    db.add(
        TicketOperation(
            operation_id="op-123",
            internal_ticket_id="ticket-123",
            action="create",
            status="failed",
            request_payload={"summary": "test"},
            attempt_count=1,
            max_attempts=5,
            created_at=now - timedelta(minutes=12),
            updated_at=now - timedelta(minutes=8),
            last_error="provider timeout",
        )
    )
    db.add(
        TicketOperation(
            operation_id="op-dryrun-create",
            internal_ticket_id="ticket-dryrun",
            action="create",
            status="succeeded",
            request_payload={"title": "Dry-run ticket"},
            normalized_payload={"title": "Dry-run ticket"},
            provider_response={
                "success": True,
                "ticket_id": "dryrun-ticket-dryrun",
                "data": {"dry_run": True, "source": "worker"},
            },
            attempt_count=1,
            max_attempts=1,
            created_at=now - timedelta(hours=2),
            updated_at=now - timedelta(hours=2),
            completed_at=now - timedelta(hours=2),
        )
    )

    db.add_all(
        [
            CollectionJob(
                job_id="job-monitor-old",
                monitor_uuid=monitor_one.monitor_uuid,
                monitor_id=monitor_one.monitor_id,
                collector_type="monitor_diagnostics",
                status="succeeded",
                parameters={},
                requested_by="operator",
                created_at=now - timedelta(hours=4),
                updated_at=now - timedelta(hours=4),
                started_at=now - timedelta(hours=4),
                completed_at=now - timedelta(hours=4) + timedelta(minutes=1),
                result={
                    "collector_type": "monitor_diagnostics",
                    "monitor_id": monitor_one.monitor_id,
                    "app_version": "2.0.183",
                    "collected_at": (now - timedelta(hours=4) + timedelta(minutes=1)).isoformat(),
                    "health": {"status": "healthy", "components": {"api": {"status": "healthy"}}},
                },
            ),
            CollectionJob(
                job_id="job-monitor-new",
                monitor_uuid=monitor_one.monitor_uuid,
                monitor_id=monitor_one.monitor_id,
                collector_type="monitor_diagnostics",
                status="succeeded",
                parameters={},
                requested_by="operator",
                created_at=now - timedelta(hours=1),
                updated_at=now - timedelta(hours=1),
                started_at=now - timedelta(hours=1),
                completed_at=now - timedelta(hours=1) + timedelta(minutes=2),
                result={
                    "collector_type": "monitor_diagnostics",
                    "monitor_id": monitor_one.monitor_id,
                    "app_version": "2.0.184",
                    "collected_at": (now - timedelta(hours=1) + timedelta(minutes=2)).isoformat(),
                    "health": {"status": "healthy", "components": {"api": {"status": "healthy"}}},
                },
            ),
            CollectionJob(
                job_id="job-ticket-context",
                monitor_uuid=monitor_one.monitor_uuid,
                monitor_id=monitor_one.monitor_id,
                collector_type="ticket_context",
                status="succeeded",
                parameters={"bakery_ticket_id": "ticket-123", "limit": 20},
                requested_by="operator",
                created_at=now - timedelta(minutes=45),
                updated_at=now - timedelta(minutes=45),
                started_at=now - timedelta(minutes=45),
                completed_at=now - timedelta(minutes=43),
                result={
                    "collected_at": (now - timedelta(minutes=43)).isoformat(),
                    "orders": [{"order_id": "INC00123", "state": "open"}],
                    "communications": [{"ticket_id": "ticket-123", "message": "queued"}],
                    "dishes": [{"id": "dish-1", "state": "pending"}],
                },
            ),
            CollectionJob(
                job_id="job-failed",
                monitor_uuid=monitor_one.monitor_uuid,
                monitor_id=monitor_one.monitor_id,
                collector_type="cluster_inventory",
                status="failed",
                parameters={"namespace": "rackspace", "limit": 25},
                requested_by="operator",
                reason="validate inventory path",
                created_at=now - timedelta(minutes=20),
                updated_at=now - timedelta(minutes=18),
                started_at=now - timedelta(minutes=20),
                completed_at=now - timedelta(minutes=18),
                error="collector crashed",
            ),
        ]
    )

    db.commit()


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = session_local()
    _seed_reporting_data(session)

    app = _load_app(monkeypatch)

    def _override_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_reader] = _auth_context
    app.dependency_overrides[require_operator] = _auth_context

    with TestClient(app) as test_client:
        yield test_client

    session.close()
    Base.metadata.drop_all(bind=engine)


def test_collection_job_collectors_endpoint_returns_catalog_metadata(client: TestClient) -> None:
    response = client.get("/api/v1/collection-jobs/collectors")

    assert response.status_code == 200
    payload = response.json()
    assert [item["collector_type"] for item in payload] == [
        "cluster_inventory",
        "monitor_diagnostics",
        "ticket_context",
    ]
    cluster_inventory = next(
        item for item in payload if item["collector_type"] == "cluster_inventory"
    )
    assert cluster_inventory["label"] == "Cluster inventory"
    assert cluster_inventory["default_parameters"]["limit"] == 50
    assert cluster_inventory["parameters"][0]["name"] == "namespace"
    assert "all cluster nodes" in cluster_inventory["description"]


def test_report_filter_options_endpoint_returns_human_friendly_filter_data(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/reports/filter-options")

    assert response.status_code == 200
    payload = response.json()
    assert payload["environment_labels"] == ["prod", "stage"]
    assert payload["provider_types"] == ["jira", "servicenow"]
    assert payload["account_numbers"] == ["123456", "654321"]
    assert payload["monitors"][0]["monitor_id"] == "alpha-monitor"
    assert payload["monitors"][1]["status"] == "unreachable"


def test_monitor_detail_endpoint_returns_recent_activity_and_latest_successes(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/reports/monitors/monitor-uuid-1/detail")

    assert response.status_code == 200
    payload = response.json()
    assert payload["monitor"]["monitor_id"] == "alpha-monitor"
    assert len(payload["recent_events"]) == 1
    assert payload["recent_events"][0]["event_type"] == "heartbeat_received"
    assert len(payload["recent_routes"]) == 1
    assert payload["recent_routes"][0]["label"] == "ServiceNow create"
    assert {job["job_id"] for job in payload["recent_jobs"]} == {
        "job-failed",
        "job-ticket-context",
        "job-monitor-new",
        "job-monitor-old",
    }
    assert {job["collector_type"] for job in payload["latest_successful_jobs"]} == {
        "monitor_diagnostics",
        "ticket_context",
    }
    latest_diagnostics = next(
        job
        for job in payload["latest_successful_jobs"]
        if job["collector_type"] == "monitor_diagnostics"
    )
    assert latest_diagnostics["job_id"] == "job-monitor-new"
    assert {item["status"] for item in payload["operation_analytics"]} == {"failed", "succeeded"}
    assert {item["ticket_id"] for item in payload["backlog"]} == {
        "ticket-123",
        "ticket-dryrun",
    }


def test_admin_monitor_delete_removes_registry_rows_and_detaches_tickets(
    client: TestClient,
) -> None:
    app = client.app

    def _admin_access() -> str:
        return "operator:admin"

    app.dependency_overrides[require_bootstrap_admin_access] = _admin_access
    try:
        response = client.delete("/api/v1/admin/monitors/monitor-uuid-1")
    finally:
        app.dependency_overrides.pop(require_bootstrap_admin_access, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["monitor_uuid"] == "monitor-uuid-1"
    assert payload["monitor_id"] == "alpha-monitor"
    assert payload["removed_by"] == "operator:admin"
    assert payload["affected_counts"] == {
        "route_catalog_entries": 1,
        "outage_route_states": 1,
        "monitor_events": 1,
        "collection_jobs": 4,
        "bootstrap_credentials": 1,
        "tickets_detached": 2,
        "monitors": 1,
    }

    monitors = client.get("/api/v1/reports/monitors")
    assert monitors.status_code == 200
    assert [item["monitor_id"] for item in monitors.json()] == ["beta-monitor"]

    overview = client.get("/api/v1/reports/overview")
    assert overview.status_code == 200
    assert overview.json()["monitors_total"] == 1
    assert overview.json()["monitors_unreachable"] == 1

    filters = client.get("/api/v1/reports/filter-options")
    assert filters.status_code == 200
    assert [item["monitor_id"] for item in filters.json()["monitors"]] == ["beta-monitor"]

    db = next(client.app.dependency_overrides[get_db]())
    assert db.query(Monitor).filter(Monitor.monitor_uuid == "monitor-uuid-1").first() is None
    assert (
        db.query(MonitorRouteCatalogEntry)
        .filter(MonitorRouteCatalogEntry.monitor_uuid == "monitor-uuid-1")
        .count()
        == 0
    )
    assert (
        db.query(MonitorOutageRouteState)
        .filter(MonitorOutageRouteState.monitor_uuid == "monitor-uuid-1")
        .count()
        == 0
    )
    assert db.query(MonitorEvent).filter(MonitorEvent.monitor_uuid == "monitor-uuid-1").count() == 0
    assert (
        db.query(CollectionJob).filter(CollectionJob.monitor_uuid == "monitor-uuid-1").count() == 0
    )
    assert (
        db.query(MonitorBootstrapCredential)
        .filter(MonitorBootstrapCredential.monitor_id == "alpha-monitor")
        .count()
        == 0
    )
    assert (
        db.query(Ticket).filter(Ticket.internal_ticket_id == "ticket-123").one().monitor_uuid
        is None
    )
    assert (
        db.query(Ticket).filter(Ticket.internal_ticket_id == "ticket-dryrun").one().monitor_uuid
        is None
    )
    assert (
        db.query(TicketOperation).filter(TicketOperation.internal_ticket_id == "ticket-123").count()
        == 1
    )


def test_admin_monitor_delete_returns_404_for_missing_monitor(client: TestClient) -> None:
    app = client.app

    def _admin_access() -> str:
        return "operator:admin"

    app.dependency_overrides[require_bootstrap_admin_access] = _admin_access
    try:
        response = client.delete("/api/v1/admin/monitors/not-a-monitor")
    finally:
        app.dependency_overrides.pop(require_bootstrap_admin_access, None)

    assert response.status_code == 404
    assert response.json()["detail"] == "Monitor not found"


def test_admin_monitor_delete_requires_admin_access(client: TestClient) -> None:
    app = client.app

    def _denied_access() -> str:
        raise HTTPException(status_code=403, detail="Admin access required")

    app.dependency_overrides[require_bootstrap_admin_access] = _denied_access
    try:
        response = client.delete("/api/v1/admin/monitors/monitor-uuid-1")
    finally:
        app.dependency_overrides.pop(require_bootstrap_admin_access, None)

    assert response.status_code == 403


def test_backlog_report_classifies_dry_run_rows_and_actions(client: TestClient) -> None:
    response = client.get("/api/v1/reports/backlog")

    assert response.status_code == 200
    payload = response.json()
    by_ticket = {item["ticket_id"]: item for item in payload}
    assert by_ticket["ticket-dryrun"]["is_dry_run"] is True
    assert by_ticket["ticket-dryrun"]["backlog_reason"] == "dry_run"
    assert by_ticket["ticket-dryrun"]["can_close"] is True
    assert by_ticket["ticket-dryrun"]["can_resync"] is False
    assert by_ticket["ticket-123"]["is_dry_run"] is False
    assert by_ticket["ticket-123"]["backlog_reason"] == "error"
    assert by_ticket["ticket-123"]["can_close"] is True
    assert by_ticket["ticket-123"]["can_resync"] is True


def test_operator_ticket_close_closes_dry_run_ticket_and_removes_it_from_backlog(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/operator/tickets/ticket-dryrun/close",
        json={"resolution_notes": "Synthetic dry-run ticket retired", "state": "closed"},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["ticket_id"] == "ticket-dryrun"
    assert payload["action"] == "close"
    assert payload["status"] == "succeeded"

    backlog = client.get("/api/v1/reports/backlog")
    assert backlog.status_code == 200
    assert {item["ticket_id"] for item in backlog.json()} == {"ticket-123"}


def test_operator_ticket_find_resyncs_errored_provider_ticket(
    client: TestClient, monkeypatch
) -> None:
    class _FakeMixer:
        async def process_request(
            self, action: str, payload: dict[str, object]
        ) -> dict[str, object]:
            assert action == "search"
            assert payload["query"] == "number=INC00123"
            return {
                "success": True,
                "data": {"results": [{"number": "INC00123", "state": "2"}]},
            }

    monkeypatch.setattr(ticket_api, "get_mixer", lambda provider: _FakeMixer())

    response = client.post("/api/v1/operator/tickets/ticket-123/find")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ticket_id"] == "ticket-123"
    assert payload["data_source"] == "provider"
    assert payload["latest_error"] is None

    backlog = client.get("/api/v1/reports/backlog")
    assert backlog.status_code == 200
    by_ticket = {item["ticket_id"]: item for item in backlog.json()}
    assert by_ticket["ticket-123"]["can_resync"] is False
    assert by_ticket["ticket-123"]["backlog_reason"] == "open"


def test_operator_ticket_endpoints_require_backlog_management_permission(
    client: TestClient,
) -> None:
    app = client.app

    def _reader_context() -> AuthContext:
        return AuthContext(
            provider="local",
            subject_id="reader-1",
            username="reader",
            display_name="Reader",
            groups=[],
            role="reader",
            principal_type="user",
            permissions=["read"],
            session_id="session-reader",
            expires_at="2030-01-01T00:00:00Z",
        )

    app.dependency_overrides[require_operator] = _reader_context
    try:
        response = client.get("/api/v1/operator/tickets/ticket-123")
    finally:
        app.dependency_overrides[require_operator] = _auth_context

    assert response.status_code == 403
