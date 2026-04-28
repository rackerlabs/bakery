"""Bakery application route regression tests."""

from __future__ import annotations

import importlib
import sys
import types

from fastapi.testclient import TestClient


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


def test_bakery_openapi_exposes_communications_and_tickets(monkeypatch) -> None:
    app = _load_app(monkeypatch)
    openapi = app.openapi()
    paths = set(openapi.get("paths", {}))
    tags = {tag["name"] for tag in openapi.get("tags", [])}

    assert "/api/v1/communications" in paths
    assert "/api/v1/tickets" in paths
    assert "/api/v1/reports/overview" in paths
    assert "/api/v1/reports/filter-options" in paths
    assert "/api/v1/reports/monitors/{monitor_uuid}/detail" in paths
    assert "/api/v1/admin/monitors/{monitor_uuid}" in paths
    assert "/api/v1/collection-jobs" in paths
    assert "/api/v1/collection-jobs/collectors" in paths
    assert "/api/v1/operator/tickets/{ticket_id}" in paths
    assert "/api/v1/providers/bootstrap" in paths
    assert "/api/v1/auth/providers" in paths
    assert "/api/v1/settings" in paths
    assert any(path.startswith("/api/v1/tickets") for path in paths)
    assert "communications" in tags
    assert "tickets" in tags
    assert "operator-tickets" in tags
    assert "reports" in tags
    assert "collection-jobs" in tags
    assert "auth" in tags
    assert "settings" in tags


def test_root_endpoint_reports_standalone_service(monkeypatch) -> None:
    app = _load_app(monkeypatch)
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["service"] == "Bakery"
    assert response.json()["description"] == "Standalone communication integration service"
