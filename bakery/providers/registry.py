"""Registry for Bakery providers."""

from __future__ import annotations

from bakery.providers.discord import DiscordProvider
from bakery.providers.github import GitHubProvider
from bakery.providers.jira import JiraProvider
from bakery.providers.pagerduty import PagerDutyProvider
from bakery.providers.rackspace_core import RackspaceCoreProvider
from bakery.providers.servicenow import ServiceNowProvider
from bakery.providers.teams import TeamsProvider
from bakery.providers.base import Provider

_PROVIDER_REGISTRY: dict[str, Provider] = {
    "servicenow": ServiceNowProvider(),
    "jira": JiraProvider(),
    "github": GitHubProvider(),
    "pagerduty": PagerDutyProvider(),
    "rackspace_core": RackspaceCoreProvider(),
    "teams": TeamsProvider(),
    "discord": DiscordProvider(),
}


def get_provider(provider_type: str) -> Provider:
    normalized = (provider_type or "").strip().lower()
    provider = _PROVIDER_REGISTRY.get(normalized)
    if provider is None:
        raise ValueError(
            f"Unknown provider type: {provider_type}. "
            f"Available: {', '.join(_PROVIDER_REGISTRY.keys())}"
        )
    return provider


def list_providers() -> list[str]:
    return list(_PROVIDER_REGISTRY.keys())
