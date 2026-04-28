import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from bakery.database import Base
from bakery.models import ProviderConfig
from bakery.providers import get_provider, list_providers
from bakery.providers.bootstrap import bootstrap_providers
from bakery.providers.payloads import provider_credentials_configured


def test_webhook_providers_report_configured_when_webhook_url_is_present() -> None:
    class _WebhookPlugin:
        webhook_url = "https://provider.example/webhook"

    assert provider_credentials_configured("teams", _WebhookPlugin()) is True
    assert provider_credentials_configured("discord", _WebhookPlugin()) is True


def test_webhook_providers_do_not_report_search_support() -> None:
    assert list(get_provider("teams").supported_actions()) == [
        "create",
        "update",
        "close",
        "comment",
    ]
    assert list(get_provider("discord").supported_actions()) == [
        "create",
        "update",
        "close",
        "comment",
    ]


def test_provider_plugin_registry_lists_backend_providers() -> None:
    assert set(list_providers()) == {
        "servicenow",
        "jira",
        "github",
        "pagerduty",
        "rackspace_core",
        "teams",
        "discord",
    }


def test_provider_contract_exposes_registration_manifest() -> None:
    provider = get_provider("jira")

    manifest = provider.registration_manifest()

    assert manifest["contract_version"] == 1
    assert manifest["provider_type"] == "jira"
    assert manifest["actions"] == ["create", "update", "close", "comment", "search"]
    assert manifest["config_schema"]["type"] == "object"
    assert manifest["credential_requirements"] == []


@pytest.mark.asyncio
async def test_provider_bootstrap_registers_provider_manifests() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = session_local()
    try:
        result = await bootstrap_providers(db)
        db.commit()

        rows = db.query(ProviderConfig).all()
        by_provider = {row.provider_type: row for row in rows}
        assert result["status"] == "ready"
        assert result["failures"] == 0
        assert set(by_provider) == set(list_providers())
        jira_config = by_provider["jira"].config_data
        assert jira_config["source"] == "provider_contract"
        assert jira_config["provider_type"] == "jira"
        assert jira_config["bootstrap"]["status"] == "ready"
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
