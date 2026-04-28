"""Shared provider payload normalization and validation helpers."""

from __future__ import annotations

from typing import Any

from bakery.config import settings
from bakery.formatters import (
    device_context_from_payload,
    provider_config_from_context,
    render_provider_content,
)


def _is_non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if _is_non_empty(value):
            return value
    return None


def build_provider_payload(
    action: str,
    *,
    provider: str,
    internal_ticket_id: str | None,
    provider_ticket_id: str | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Build provider-native payload from Bakery's canonical ticket payload."""
    provider = str(provider or settings.active_provider or "").strip().lower()
    raw_context = payload.get("context")
    context: dict[str, Any] = raw_context if isinstance(raw_context, dict) else {}
    provider_payload = provider_config_from_context(provider, payload)

    for key in ("source", "visibility"):
        if context.get(key) is not None and key not in provider_payload:
            provider_payload[key] = context.get(key)
    if provider == "rackspace_core":
        device_context = device_context_from_payload(action, payload)
        if device_context:
            provider_payload.setdefault("device_context", device_context)

    if action == "create":
        provider_payload.update(render_provider_content(provider, action, payload))
        provider_payload.setdefault("title", payload.get("title", ""))
        provider_payload.setdefault("description", payload.get("description", ""))
        if payload.get("severity") is not None:
            provider_payload.setdefault("severity", payload.get("severity"))
        if payload.get("category") is not None:
            provider_payload.setdefault("category", payload.get("category"))
        if payload.get("source") is not None:
            provider_payload.setdefault("source", payload.get("source"))

        if provider == "rackspace_core":
            provider_payload.setdefault("subject", payload.get("title", ""))
            provider_payload.setdefault("body", payload.get("description", ""))
            if settings.rackspace_core_default_queue:
                provider_payload.setdefault("queue", settings.rackspace_core_default_queue)
            if settings.rackspace_core_default_subcategory:
                provider_payload.setdefault(
                    "subcategory", settings.rackspace_core_default_subcategory
                )
        return provider_payload

    if provider_ticket_id:
        provider_payload.setdefault("ticket_id", provider_ticket_id)
    elif provider in {"teams", "discord"} and internal_ticket_id:
        provider_payload.setdefault("ticket_id", internal_ticket_id)
    elif settings.ticketing_dry_run and internal_ticket_id:
        provider_payload.setdefault("ticket_id", f"dryrun-{internal_ticket_id}")
    else:
        raise ValueError("Provider ticket id is not available yet for this ticket")

    if action == "update":
        if provider in {"teams", "discord"}:
            provider_payload.update(render_provider_content(provider, action, payload))
            provider_payload.setdefault(
                "message",
                _first_non_empty(
                    provider_payload.get("message"),
                    payload.get("message"),
                    payload.get("comment"),
                    payload.get("description"),
                    payload.get("title"),
                )
                or "PoundCake communication update.",
            )
            return provider_payload
        updates = provider_payload.get("updates")
        if not updates:
            updates = {}
            for field in ("title", "description", "severity", "category", "state"):
                if payload.get(field) is not None:
                    updates[field] = payload.get(field)
            if updates:
                provider_payload["updates"] = updates
        if provider == "rackspace_core" and updates:
            provider_payload.setdefault("attributes", updates)
        return provider_payload

    if action == "comment":
        provider_payload.update(render_provider_content(provider, action, payload))
        if provider in {"teams", "discord"}:
            provider_payload.setdefault(
                "message",
                _first_non_empty(
                    provider_payload.get("message"),
                    payload.get("comment"),
                    payload.get("message"),
                    payload.get("description"),
                    payload.get("title"),
                )
                or "PoundCake communication update.",
            )
            return provider_payload
        provider_payload.setdefault("comment", payload.get("comment", ""))
        if payload.get("visibility") is not None:
            provider_payload.setdefault("visibility", payload.get("visibility"))
        if payload.get("source") is not None:
            provider_payload.setdefault("source", payload.get("source"))
        return provider_payload

    if action == "close":
        provider_payload.update(render_provider_content(provider, action, payload))
        if provider in {"teams", "discord"}:
            provider_payload.setdefault(
                "message",
                _first_non_empty(
                    provider_payload.get("message"),
                    payload.get("message"),
                    payload.get("comment"),
                    payload.get("resolution_notes"),
                    payload.get("description"),
                    payload.get("title"),
                )
                or "PoundCake communication closed.",
            )
            return provider_payload
        if provider == "rackspace_core":
            status_hint = _first_non_empty(provider_payload.get("status"), payload.get("state"))
            normalized_hint = str(status_hint or "").strip().lower().replace("_", " ")
            if normalized_hint in {"", "closed"}:
                status_hint = (
                    settings.bakery_rackspace_confirmed_solved_status or "confirmed solved"
                )
            provider_payload.setdefault("status", str(status_hint).replace("_", " "))
        if payload.get("resolution_notes") is not None:
            provider_payload.setdefault("close_notes", payload.get("resolution_notes"))
        if payload.get("resolution_code") is not None:
            provider_payload.setdefault("resolution_code", payload.get("resolution_code"))
        if payload.get("state") is not None:
            provider_payload.setdefault("state", payload.get("state"))
        if payload.get("source") is not None:
            provider_payload.setdefault("source", payload.get("source"))
        return provider_payload

    raise ValueError(f"Unsupported action: {action}")


def missing_provider_fields(provider: str, action: str, payload: dict[str, Any]) -> list[str]:
    """Return provider-specific missing fields for a normalized payload."""

    def missing(*fields: str) -> list[str]:
        out: list[str] = []
        for field in fields:
            value = payload.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                out.append(field)
        return out

    provider = str(provider or "").strip().lower()
    if provider == "rackspace_core":
        if action == "create":
            return missing("account_number", "queue", "subcategory", "subject", "body")
        if action == "update":
            errors = missing("ticket_id")
            has_updates = _is_non_empty(payload.get("attributes")) or _is_non_empty(
                payload.get("updates")
            )
            if not has_updates:
                errors.append("attributes|updates")
            return errors
        if action == "close":
            return missing("ticket_id")
        if action == "comment":
            return missing("ticket_id", "comment")
        return []

    if provider == "servicenow":
        if action in {"update", "close"}:
            return missing("ticket_id")
        if action == "comment":
            return missing("ticket_id", "comment")
        return []

    if provider == "jira":
        if action == "create":
            return missing("project_key")
        if action in {"update", "close"}:
            return missing("ticket_id")
        if action == "comment":
            return missing("ticket_id", "comment")
        return []

    if provider == "github":
        if action == "create":
            return missing("owner", "repo")
        if action in {"update", "close"}:
            return missing("owner", "repo", "ticket_id")
        if action == "comment":
            return missing("owner", "repo", "ticket_id", "comment")
        return []

    if provider == "pagerduty":
        if action == "create":
            return missing("service_id", "from_email")
        if action in {"update", "close"}:
            return missing("ticket_id", "from_email")
        if action == "comment":
            return missing("ticket_id", "from_email", "comment")
        return []

    if provider in {"teams", "discord"}:
        if action in {"create", "update", "close", "comment"}:
            return missing("message")
        return []

    return []


def provider_credentials_configured(provider_type: str, provider: Any) -> bool:
    """Return whether a provider has non-empty configured credentials."""
    if provider_type == "servicenow":
        return bool(
            getattr(provider, "base_url", None)
            and getattr(provider, "username", None)
            and getattr(provider, "password", None)
        )
    if provider_type == "jira":
        return bool(
            getattr(provider, "base_url", None)
            and getattr(provider, "username", None)
            and getattr(provider, "api_token", None)
        )
    if provider_type == "github":
        return bool(getattr(provider, "token", None))
    if provider_type == "pagerduty":
        return bool(getattr(provider, "api_key", None))
    if provider_type in {"teams", "discord"}:
        return bool(getattr(provider, "webhook_url", None))
    if provider_type == "rackspace_core":
        return bool(
            getattr(provider, "base_url", None)
            and getattr(provider, "username", None)
            and getattr(provider, "password", None)
        )
    return False
