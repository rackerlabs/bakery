"""Regression tests for split Bakery UI deployments."""

from __future__ import annotations

import importlib
import sys
import types

from fastapi.testclient import TestClient

from bakery.api import operator_auth as operator_auth_api
from bakery.api.operator_auth import _normalize_next_target
from bakery.config import settings
from bakery.database import get_db
from bakery.operator_auth import AuthContext, require_reader


class _FakeDbSession:
    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        pass


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
        permissions=["read", "queue_jobs", "manage_auth", "manage_bootstrap"],
        session_id="sess-123",
        expires_at="2030-01-01T00:00:00Z",
    )


def test_login_sets_cross_site_cookie_for_split_ui(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ui_public_url", "https://bakery-ui.example.net/")
    app = _load_app(monkeypatch)
    app.dependency_overrides[get_db] = lambda: _FakeDbSession()

    async def _fake_authenticate_password_provider(*args):
        return object()

    monkeypatch.setattr(
        operator_auth_api,
        "authenticate_password_provider",
        _fake_authenticate_password_provider,
    )
    monkeypatch.setattr(
        operator_auth_api, "build_login_context", lambda db, identity: _auth_context()
    )

    def _fake_create_session(db, context, *, ttl_seconds):
        context.session_id = "sess-123"
        context.expires_at = "2030-01-01T00:00:00Z"
        return context

    monkeypatch.setattr(operator_auth_api, "create_session", _fake_create_session)

    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/login",
        json={"provider": "local", "username": "operator", "password": "secret"},
        headers={"Origin": "https://bakery-ui.example.net"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://bakery-ui.example.net"
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "samesite=none" in response.headers["set-cookie"].lower()
    assert "secure" in response.headers["set-cookie"].lower()


def test_login_keeps_lax_cookie_for_legacy_same_host_ui(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ui_public_url", "")
    app = _load_app(monkeypatch)
    app.dependency_overrides[get_db] = lambda: _FakeDbSession()

    async def _fake_authenticate_password_provider(*args):
        return object()

    monkeypatch.setattr(
        operator_auth_api,
        "authenticate_password_provider",
        _fake_authenticate_password_provider,
    )
    monkeypatch.setattr(
        operator_auth_api, "build_login_context", lambda db, identity: _auth_context()
    )

    def _fake_create_session(db, context, *, ttl_seconds):
        context.session_id = "sess-legacy"
        return context

    monkeypatch.setattr(operator_auth_api, "create_session", _fake_create_session)

    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/login",
        json={"provider": "local", "username": "operator", "password": "secret"},
        headers={"x-forwarded-proto": "https"},
    )

    assert response.status_code == 200
    assert "samesite=lax" in response.headers["set-cookie"].lower()


def test_auth_me_allows_configured_ui_origin(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ui_public_url", "https://bakery-ui.example.net")
    app = _load_app(monkeypatch)
    app.dependency_overrides[require_reader] = _auth_context

    client = TestClient(app)
    client.cookies.set("session_token", "sess-123")
    response = client.get(
        "/api/v1/auth/me",
        headers={"Origin": "https://bakery-ui.example.net"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://bakery-ui.example.net"
    assert response.json()["username"] == "operator"


def test_cors_does_not_allow_unconfigured_origin(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ui_public_url", "https://bakery-ui.example.net")
    app = _load_app(monkeypatch)
    client = TestClient(app)

    response = client.get("/api/v1/settings", headers={"Origin": "https://evil.example.org"})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_normalize_next_target_allows_only_the_configured_ui_url(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ui_public_url", "https://bakery-ui.example.net/")

    assert (
        _normalize_next_target("https://bakery-ui.example.net") == "https://bakery-ui.example.net"
    )
    assert _normalize_next_target("https://evil.example.org") == "https://bakery-ui.example.net"
    assert _normalize_next_target("/reports") == "/reports"
