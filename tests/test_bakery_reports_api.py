"""Regression tests for the Bakery operator reporting APIs."""

from __future__ import annotations

import importlib
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from bakery.database import Base, get_db
from bakery.models import (
    CollectionJob,
    Monitor,
    MonitorEvent,
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
        permissions=["read", "queue_jobs"],
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
        region="ord",
        cluster_name="cluster-a",
        namespace="rackspace",
        release_name="poundcake",
        tags_json=["primary", "ord"],
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
        region="dfw",
        cluster_name="cluster-b",
        namespace="example-stage",
        release_name="poundcake-stage",
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
        job for job in payload["latest_successful_jobs"] if job["collector_type"] == "monitor_diagnostics"
    )
    assert latest_diagnostics["job_id"] == "job-monitor-new"
    assert payload["operation_analytics"][0]["status"] == "failed"
    assert payload["backlog"][0]["ticket_id"] == "ticket-123"
