"""Regression tests for Bakery runtime version reporting."""

from __future__ import annotations

from bakery.config import Settings as BakerySettings
from shared.version import __version__, resolve_version


def test_resolve_version_uses_first_configured_env_var(monkeypatch) -> None:
    monkeypatch.setenv("PRIMARY_VERSION", "0.1.10")
    monkeypatch.setenv("SECONDARY_VERSION", "0.1.9")

    assert resolve_version("PRIMARY_VERSION", "SECONDARY_VERSION") == "0.1.10"


def test_resolve_version_falls_back_to_repo_version(monkeypatch) -> None:
    monkeypatch.delenv("PRIMARY_VERSION", raising=False)
    monkeypatch.delenv("SECONDARY_VERSION", raising=False)

    assert resolve_version("PRIMARY_VERSION", "SECONDARY_VERSION") == __version__


def test_bakery_settings_app_version_uses_runtime_env(monkeypatch) -> None:
    monkeypatch.setenv("BAKERY_APP_VERSION", "0.1.10")

    settings = BakerySettings()

    assert settings.app_version == "0.1.10"


def test_bakery_settings_app_version_falls_back_to_repo_version(monkeypatch) -> None:
    monkeypatch.delenv("BAKERY_APP_VERSION", raising=False)

    settings = BakerySettings()

    assert settings.app_version == __version__
