#!/usr/bin/env python3
"""Provider-native communication renderers for Bakery."""

from __future__ import annotations

import re
from typing import Any

URL_RE = re.compile(r"(https?://[^\s<>\]]+)")
AUTH_HEADER_RE = re.compile(r"(?im)\b(authorization\s*:\s*(?:bearer|basic)\s+)[^\s]+")
SECRET_KV_RE = re.compile(
    r"(?im)\b("
    r"api[_-]?key|access[_-]?token|auth[_-]?token|token|secret|password|"
    r"webhook(?:_url)?|cookie"
    r")\b(\s*[:=]\s*)([^\s,;]+)"
)
QUERY_SECRET_RE = re.compile(
    r"([?&](?:access_token|token|api[_-]?key|apikey|sig|signature|password|secret|webhook_url)=)"
    r"[^&\s]+",
    re.IGNORECASE,
)
WEBHOOK_URL_RE = re.compile(
    r"https?://(?:discord(?:app)?\.com/api/webhooks|hooks\.slack\.com/services|"
    r"outlook\.office\.com/webhook)[^\s]+",
    re.IGNORECASE,
)
URL_CREDENTIALS_RE = re.compile(r"(https?://)([^/\s:@]+):([^/\s@]+)@", re.IGNORECASE)

FULL_STEP_LIMIT = 8
COMPACT_STEP_LIMIT = 3
FULL_STEP_OUTCOME_LIMIT = 180
COMPACT_STEP_OUTCOME_LIMIT = 90
FULL_EXCERPT_LIMIT = 900
COMPACT_EXCERPT_LIMIT = 260
DEVICE_NAME_FIELDS = (
    "affected_device",
    "device_name",
    "device",
    "affected_node",
    "node",
    "k8s_node_name",
    "host_name",
    "node_hostname",
    "hostname",
    "host",
    "service_instance_id",
    "instance",
)
DEVICE_NUMBER_FIELDS = (
    "device_number",
    "device_id",
    "computer_number",
    "computer_id",
    "core_device_number",
    "core_device_id",
    "rackspace_device_number",
    "rackspace_device_id",
    "server_number",
)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _collapse_line(value: Any) -> str:
    return " ".join(_text(value).split()).strip()


def _csv_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [_text(value)] if _text(value) else []


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3].rstrip() + "..."


def _dedupe_preserve(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(value)
    return unique


def _redact_sensitive_text(text: str) -> str:
    if not text:
        return ""

    text = AUTH_HEADER_RE.sub(r"\1[REDACTED]", text)
    text = SECRET_KV_RE.sub(r"\1\2[REDACTED]", text)
    text = QUERY_SECRET_RE.sub(r"\1[REDACTED]", text)
    text = WEBHOOK_URL_RE.sub("[REDACTED_WEBHOOK_URL]", text)
    text = URL_CREDENTIALS_RE.sub(r"\1[REDACTED]@", text)
    return text


def _sanitize_multiline_text(value: Any, limit: int) -> str:
    raw = _redact_sensitive_text(_text(value)).replace("\r\n", "\n")
    if not raw:
        return ""
    lines = [line.rstrip() for line in raw.split("\n")]
    normalized: list[str] = []
    pending_blank = False
    for line in lines:
        if line.strip():
            normalized.append(line.strip())
            pending_blank = False
            continue
        if normalized and not pending_blank:
            normalized.append("")
            pending_blank = True
    return _truncate("\n".join(normalized).strip(), limit)


def _sanitize_line(value: Any, limit: int) -> str:
    sanitized = _collapse_line(_redact_sensitive_text(_text(value)))
    return _truncate(sanitized, limit)


def _compose_field_value(*values: Any, limit: int) -> str:
    parts = _dedupe_preserve([_sanitize_line(value, limit) for value in values])
    return _truncate(" ".join(parts).strip(), limit)


def _append_field(
    fields: list[tuple[str, str]],
    label: str,
    value: Any,
    *,
    limit: int,
) -> None:
    rendered = _sanitize_line(value, limit)
    if not rendered:
        return
    if any(
        existing_label.casefold() == label.casefold() and existing.casefold() == rendered.casefold()
        for existing_label, existing in fields
    ):
        return
    fields.append((label, rendered))


def _pluralize(count: int, singular: str, plural: str | None = None) -> str:
    if count == 1:
        return f"{count} {singular}"
    return f"{count} {plural or singular + 's'}"


def _auto_link_bbcode(text: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        url = match.group(1)
        return f"[url={url}]{url}[/url]"

    return URL_RE.sub(_replace, text)


def _auto_link_markdown(text: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        url = match.group(1)
        return f"[{url}]({url})"

    return URL_RE.sub(_replace, text)


def _dedupe_links(links: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, str]] = []
    for link in links:
        label = _text(link.get("label"))
        url = _text(link.get("url"))
        if not url:
            continue
        key = (label.lower(), url)
        if key in seen:
            continue
        seen.add(key)
        unique.append({"label": label or url, "url": url})
    return unique


def _device_from_labels(labels: dict[str, Any]) -> dict[str, str]:
    name = ""
    source_label = ""
    for key in DEVICE_NAME_FIELDS:
        value = _text(labels.get(key))
        if value:
            name = value
            source_label = key
            break
    number = ""
    for key in DEVICE_NUMBER_FIELDS:
        value = _text(labels.get(key))
        if value:
            number = value
            break
    if not name and not number:
        return {}
    return {
        "name": name,
        "hostname": name,
        "number": number,
        "source_label": source_label,
    }


def _split_text_with_urls(text: str) -> list[tuple[str, bool]]:
    if not text:
        return []
    parts: list[tuple[str, bool]] = []
    cursor = 0
    for match in URL_RE.finditer(text):
        start, end = match.span()
        if start > cursor:
            parts.append((text[cursor:start], False))
        parts.append((match.group(1), True))
        cursor = end
    if cursor < len(text):
        parts.append((text[cursor:], False))
    return [(segment, is_url) for segment, is_url in parts if segment]


def _build_fallback_canonical(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    labels = context.get("labels") if isinstance(context.get("labels"), dict) else {}
    annotations = context.get("annotations") if isinstance(context.get("annotations"), dict) else {}
    route_label = _text(context.get("route_label"))
    links: list[dict[str, str]] = []
    generator_url = _text(context.get("generatorURL") or payload.get("generatorURL"))
    if generator_url:
        links.append({"label": "Source", "url": generator_url})
    for key, label in (
        ("runbook_url", "Runbook"),
        ("dashboard_url", "Dashboard"),
        ("playbook_url", "Playbook"),
        ("investigation_url", "Investigation"),
        ("silence_url", "Silence"),
    ):
        url = _text(annotations.get(key) or context.get(key) or payload.get(key))
        if url:
            links.append({"label": label, "url": url})

    device = _device_from_labels(labels)

    return {
        "schema_version": 1,
        "event": {
            "name": _text(context.get("event_name")),
            "operation": action,
            "managed": False,
            "source": _text(payload.get("source") or context.get("source") or "poundcake"),
        },
        "route": {
            "id": _text(context.get("route_id")),
            "label": route_label,
            "execution_target": _text(context.get("provider_type")),
            "destination_target": _text(context.get("destination_target")),
            "provider_config": (
                context.get("provider_config")
                if isinstance(context.get("provider_config"), dict)
                else {}
            ),
        },
        "order": {
            "id": context.get("order_id"),
            "req_id": _text(context.get("req_id")),
            "processing_status": _text(context.get("processing_status")),
            "alert_status": _text(context.get("alert_status")),
            "remediation_outcome": _text(context.get("remediation_outcome")),
            "counter": context.get("counter"),
            "clear_timeout_sec": context.get("clear_timeout_sec"),
            "clear_deadline_at": _text(context.get("clear_deadline_at")),
            "clear_timed_out_at": _text(context.get("clear_timed_out_at")),
            "auto_close_eligible": bool(context.get("auto_close_eligible", False)),
        },
        "alert": {
            "group_name": _text(labels.get("group_name") or labels.get("alertname")),
            "severity": _text(payload.get("severity") or labels.get("severity") or "unknown"),
            "status": _text(context.get("alert_status")),
            "fingerprint": _text(context.get("fingerprint")),
            "instance": _text(device.get("name") or labels.get("instance")),
            "starts_at": _text(context.get("starts_at")),
            "ends_at": _text(context.get("ends_at")),
            "labels": labels,
            "annotations": annotations,
            "generator_url": generator_url,
        },
        "device": device,
        "links": _dedupe_links(links),
        "text": {
            "headline": _text(
                payload.get("title") or payload.get("message") or payload.get("comment")
            ),
            "summary": _text(payload.get("description") or annotations.get("summary")),
            "detail": _text(
                payload.get("message")
                or payload.get("comment")
                or payload.get("resolution_notes")
                or annotations.get("description")
            ),
            "resolution": _text(payload.get("resolution_notes") or payload.get("comment")),
        },
        "remediation": {
            "summary": {"total": 0, "succeeded": 0, "failed": 0, "skipped": 0, "incomplete": 0},
            "steps": [],
            "before_excerpt": "",
            "after_excerpt": "",
            "failure_excerpt": "",
            "latest_completed_step": None,
        },
    }


def canonical_from_payload(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    canonical = context.get("_canonical")
    if isinstance(canonical, dict):
        return canonical
    return _build_fallback_canonical(action, payload)


def device_context_from_payload(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    canonical = canonical_from_payload(action, payload)
    device = canonical.get("device") if isinstance(canonical.get("device"), dict) else {}
    if device:
        return {key: value for key, value in device.items() if value not in (None, "", [])}
    alert = canonical.get("alert") if isinstance(canonical.get("alert"), dict) else {}
    labels = alert.get("labels") if isinstance(alert.get("labels"), dict) else {}
    return _device_from_labels(labels)


def provider_config_from_context(provider: str, payload: dict[str, Any]) -> dict[str, Any]:
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    provider_config = (
        dict(context.get("provider_config"))
        if isinstance(context.get("provider_config"), dict)
        else {}
    )
    legacy_context = {
        "rackspace_core": (
            (
                "account_number",
                context.get("account_number")
                or context.get("accountNumber")
                or context.get("coreAccountID")
                or context.get("rackspace_com_coreAccountID"),
            ),
            ("queue", context.get("queue") or context.get("coreQueue")),
            ("subcategory", context.get("subcategory") or context.get("coreSubcategory")),
            ("source", context.get("source")),
            ("visibility", context.get("visibility")),
        ),
        "servicenow": (
            ("urgency", context.get("urgency") or context.get("serviceNowUrgency")),
            ("impact", context.get("impact") or context.get("serviceNowImpact")),
        ),
        "jira": (
            ("project_key", context.get("project_key") or context.get("jiraProjectKey")),
            ("issue_type", context.get("issue_type") or context.get("jiraIssueType")),
            ("transition_id", context.get("transition_id")),
        ),
        "github": (
            ("owner", context.get("owner") or context.get("githubOwner")),
            ("repo", context.get("repo") or context.get("githubRepo")),
            ("labels", context.get("labels") or context.get("githubLabels")),
            ("assignees", context.get("assignees") or context.get("githubAssignees")),
        ),
        "pagerduty": (
            ("service_id", context.get("service_id") or context.get("pagerDutyServiceId")),
            ("from_email", context.get("from_email") or context.get("pagerDutyFromEmail")),
            ("urgency", context.get("urgency") or context.get("pagerDutyUrgency")),
        ),
    }
    for key, value in legacy_context.get(provider, ()):
        if key in provider_config or value in (None, "", []):
            continue
        provider_config[key] = value
    if "labels" in provider_config:
        provider_config["labels"] = _csv_list(provider_config["labels"])
    if "assignees" in provider_config:
        provider_config["assignees"] = _csv_list(provider_config["assignees"])
    return provider_config


def _known_links(canonical: dict[str, Any]) -> list[dict[str, str]]:
    raw_links = canonical.get("links") if isinstance(canonical.get("links"), list) else []
    normalized = [
        {"label": _text(item.get("label")), "url": _text(item.get("url"))}
        for item in raw_links
        if isinstance(item, dict)
    ]
    return _dedupe_links(normalized)


def _title_from_canonical(canonical: dict[str, Any]) -> str:
    text = canonical.get("text") if isinstance(canonical.get("text"), dict) else {}
    alert = canonical.get("alert") if isinstance(canonical.get("alert"), dict) else {}
    headline = _text(text.get("headline"))
    summary = _text(
        alert.get("annotations", {}).get("summary")
        if isinstance(alert.get("annotations"), dict)
        else ""
    )
    base = summary or _text(alert.get("group_name")) or headline or "PoundCake communication"
    instance = _text(alert.get("instance"))
    if instance:
        base = f"{base} ({instance})"
    if headline and headline.lower() not in base.lower():
        base = f"{headline}: {base}"
    return _truncate(base, 255)


def _severity_color(severity: str) -> int:
    normalized = severity.lower()
    if normalized == "critical":
        return 0xD92D20
    if normalized in {"warning", "high"}:
        return 0xF79009
    if normalized in {"info", "low"}:
        return 0x2E90FA
    return 0x667085


def _discord_embed_color(model: dict[str, Any]) -> int:
    event_name = _text(model.get("event_name")).lower()
    alert_status = _text(model.get("alert_status")).lower()
    operation = _text(model.get("operation")).lower()
    remediation_outcome = _text(model.get("remediation_outcome")).lower()

    if operation == "close":
        return 0x12B76A
    if alert_status == "resolved":
        return 0x12B76A
    if event_name.startswith("resolved_") or event_name in {"fallback_notify", "alert_resolved"}:
        return 0x12B76A
    if remediation_outcome == "succeeded" and event_name.endswith("_close"):
        return 0x12B76A
    return _severity_color(model["severity"])


def _pretty_status(value: Any) -> str:
    normalized = _collapse_line(value).lower().replace("_", " ")
    if normalized == "incomplete":
        return "in progress"
    return normalized


def _remediation_summary_line(summary: dict[str, Any]) -> str:
    total = int(summary.get("total") or 0)
    if total <= 0:
        return ""
    parts = [f"{_pluralize(total, 'step')} recorded"]
    for key in ("succeeded", "failed", "skipped", "incomplete"):
        count = int(summary.get(key) or 0)
        if count:
            if key == "incomplete":
                parts.append(f"{count} in progress")
            else:
                parts.append(_pluralize(count, key))
    return ": ".join((parts[0], ", ".join(parts[1:]))) if len(parts) > 1 else parts[0]


def _step_line(step: dict[str, Any], *, outcome_limit: int) -> str:
    label = _sanitize_line(step.get("task_key") or "step", 120)
    status = _pretty_status(step.get("status"))
    outcome = _sanitize_line(step.get("outcome"), outcome_limit)
    parts = [item for item in (label, status) if item]
    line = " - ".join(parts)
    if outcome and outcome.lower() not in line.lower():
        line = f"{line} - {outcome}" if line else outcome
    return f"- {line}".strip()


def _latest_step_line(step: dict[str, Any] | None, *, outcome_limit: int) -> str:
    if not isinstance(step, dict):
        return ""
    rendered = _step_line(step, outcome_limit=outcome_limit).removeprefix("- ").strip()
    if not rendered:
        return ""
    return f"Latest completed step: {rendered}"


def _pick_remediation_excerpts(
    remediation: dict[str, Any],
    *,
    remediation_outcome: str,
    action: str,
    excerpt_limit: int,
) -> dict[str, str]:
    failure_excerpt = _sanitize_multiline_text(remediation.get("failure_excerpt"), excerpt_limit)
    before_excerpt = _sanitize_multiline_text(remediation.get("before_excerpt"), excerpt_limit)
    after_excerpt = _sanitize_multiline_text(remediation.get("after_excerpt"), excerpt_limit)
    normalized_outcome = remediation_outcome.lower()
    normalized_action = action.lower()

    if failure_excerpt and normalized_outcome not in {"succeeded", "success"}:
        return {"failure_excerpt": failure_excerpt}
    if normalized_outcome in {"succeeded", "success"} or normalized_action == "close":
        excerpts: dict[str, str] = {}
        if before_excerpt:
            excerpts["before_excerpt"] = before_excerpt
        if after_excerpt:
            excerpts["after_excerpt"] = after_excerpt
        return excerpts
    if failure_excerpt:
        return {"failure_excerpt": failure_excerpt}
    if before_excerpt and normalized_action == "comment":
        return {"before_excerpt": before_excerpt}
    return {}


def _build_remediation_model(
    canonical: dict[str, Any],
    action: str,
    *,
    compact: bool,
) -> dict[str, Any]:
    remediation = (
        canonical.get("remediation") if isinstance(canonical.get("remediation"), dict) else {}
    )
    order = canonical.get("order") if isinstance(canonical.get("order"), dict) else {}
    summary = remediation.get("summary") if isinstance(remediation.get("summary"), dict) else {}
    raw_steps = remediation.get("steps") if isinstance(remediation.get("steps"), list) else []
    latest_completed_step = (
        remediation.get("latest_completed_step")
        if isinstance(remediation.get("latest_completed_step"), dict)
        else None
    )

    step_limit = COMPACT_STEP_LIMIT if compact else FULL_STEP_LIMIT
    outcome_limit = COMPACT_STEP_OUTCOME_LIMIT if compact else FULL_STEP_OUTCOME_LIMIT
    excerpt_limit = COMPACT_EXCERPT_LIMIT if compact else FULL_EXCERPT_LIMIT

    step_lines = [
        _step_line(step, outcome_limit=outcome_limit)
        for step in raw_steps[:step_limit]
        if isinstance(step, dict)
    ]
    hidden_steps = max(len(raw_steps) - len(step_lines), 0)
    if hidden_steps:
        step_lines.append(f"- ... {_pluralize(hidden_steps, 'more step')}")

    excerpts = _pick_remediation_excerpts(
        remediation,
        remediation_outcome=_text(order.get("remediation_outcome")),
        action=action,
        excerpt_limit=excerpt_limit,
    )

    return {
        "summary": _remediation_summary_line(summary),
        "latest": (
            _latest_step_line(latest_completed_step, outcome_limit=outcome_limit)
            if action == "comment"
            else ""
        ),
        "steps": step_lines,
        "before_excerpt": excerpts.get("before_excerpt", ""),
        "after_excerpt": excerpts.get("after_excerpt", ""),
        "failure_excerpt": excerpts.get("failure_excerpt", ""),
    }


def _field_sections(model: dict[str, Any]) -> list[tuple[str, list[tuple[str, str]]]]:
    return [
        ("Current State", model["current_state"]),
        ("Problem", model["problem"]),
        ("Affected Scope", model["affected_scope"]),
        ("Operator Guidance", model["operator_guidance"]),
    ]


def _section_model(canonical: dict[str, Any], action: str, *, compact: bool) -> dict[str, Any]:
    text = canonical.get("text") if isinstance(canonical.get("text"), dict) else {}
    alert = canonical.get("alert") if isinstance(canonical.get("alert"), dict) else {}
    annotations = alert.get("annotations") if isinstance(alert.get("annotations"), dict) else {}
    labels = alert.get("labels") if isinstance(alert.get("labels"), dict) else {}
    order = canonical.get("order") if isinstance(canonical.get("order"), dict) else {}
    event = canonical.get("event") if isinstance(canonical.get("event"), dict) else {}
    device = device_context_from_payload(action, {"context": {"_canonical": canonical}})

    headline = _sanitize_line(_text(text.get("headline")) or _title_from_canonical(canonical), 255)
    current_state: list[tuple[str, str]] = []
    _append_field(current_state, "Severity", alert.get("severity"), limit=64)
    _append_field(current_state, "Status", alert.get("status"), limit=64)
    _append_field(current_state, "Started", alert.get("starts_at"), limit=64)
    _append_field(current_state, "Ended", alert.get("ends_at"), limit=64)

    problem: list[tuple[str, str]] = []
    alert_summary = _sanitize_line(annotations.get("summary"), 500)
    impact = _sanitize_line(annotations.get("description"), 500)
    _append_field(problem, "Alert Summary", alert_summary, limit=500)
    _append_field(problem, "Impact", impact, limit=500)

    automation_context = _compose_field_value(text.get("summary"), text.get("detail"), limit=500)
    resolution = _compose_field_value(text.get("resolution"), limit=500)
    if action == "close":
        if resolution:
            _append_field(problem, "Resolution", resolution, limit=500)
        elif automation_context:
            _append_field(problem, "Resolution", automation_context, limit=500)
    elif automation_context:
        _append_field(problem, "Automation Context", automation_context, limit=500)

    affected_scope: list[tuple[str, str]] = []
    _append_field(affected_scope, "Affected Device", device.get("name"), limit=255)
    _append_field(affected_scope, "Core Device Number", device.get("number"), limit=64)
    _append_field(affected_scope, "Cluster", labels.get("cluster"), limit=255)
    _append_field(affected_scope, "Namespace", labels.get("namespace"), limit=255)
    _append_field(affected_scope, "Job", labels.get("job"), limit=255)
    _append_field(affected_scope, "Service", labels.get("service"), limit=255)
    _append_field(
        affected_scope,
        "Instance",
        alert.get("instance") or labels.get("instance"),
        limit=255,
    )

    operator_guidance: list[tuple[str, str]] = []
    _append_field(
        operator_guidance, "Suggested Action", annotations.get("suggested_action"), limit=500
    )
    _append_field(
        operator_guidance, "Customer Impact", annotations.get("customer_impact"), limit=500
    )

    links = _known_links(canonical)
    identifiers: list[tuple[str, str]] = []
    _append_field(identifiers, "Alert Rule", labels.get("alertname"), limit=255)
    _append_field(identifiers, "Alert Group", alert.get("group_name"), limit=255)
    _append_field(identifiers, "Fingerprint", alert.get("fingerprint"), limit=255)
    _append_field(identifiers, "Order", order.get("id"), limit=64)
    _append_field(identifiers, "Request", order.get("req_id"), limit=128)

    return {
        "headline": headline,
        "title": _sanitize_line(_title_from_canonical(canonical), 255),
        "current_state": current_state,
        "problem": problem,
        "affected_scope": affected_scope,
        "operator_guidance": operator_guidance,
        "links": links,
        "identifiers": identifiers,
        "severity": _text(alert.get("severity") or "unknown"),
        "alert_status": _text(alert.get("status")),
        "event_name": _text(event.get("name")),
        "operation": _text(event.get("operation") or action),
        "remediation_outcome": _text(order.get("remediation_outcome")),
        "remediation": _build_remediation_model(canonical, action, compact=compact),
    }


def _markdown_code_text(text: str) -> str:
    return text.replace("```", "'''")


def _bbcode_code_text(text: str) -> str:
    return text.replace("[code]", "[ code]").replace("[/code]", "[/ code]")


def _plain_field_line(label: str, value: str) -> str:
    return f"{label}: {value}"


def _markdown_field_line(label: str, value: str) -> str:
    return f"- **{label}:** {_auto_link_markdown(value)}"


def _bbcode_field_line(label: str, value: str) -> str:
    return f"[b]{label}:[/b] {_auto_link_bbcode(value)}"


def _plain_link_line(item: dict[str, str]) -> str:
    return f"{item['label']}: {item['url']}"


def _markdown_link_line(item: dict[str, str]) -> str:
    return f"- **{item['label']}:** [{item['label']}]({item['url']})"


def _bbcode_link_line(item: dict[str, str]) -> str:
    return f"[b]{item['label']}:[/b] [url={item['url']}]{item['label']}[/url]"


def _render_plain_sections(model: dict[str, Any]) -> str:
    remediation = model["remediation"]
    parts = [model["headline"]]
    for heading, fields in _field_sections(model):
        if not fields:
            continue
        parts.append("")
        parts.append(heading)
        parts.extend(_plain_field_line(label, value) for label, value in fields)
    if remediation["summary"] or remediation["latest"] or remediation["steps"]:
        parts.append("")
        parts.append("Remediation")
        if remediation["summary"]:
            parts.append(remediation["summary"])
        if remediation["latest"]:
            parts.append(remediation["latest"])
        parts.extend(remediation["steps"])
    for heading, body in (
        ("Failure excerpt", remediation["failure_excerpt"]),
        ("Before remediation excerpt", remediation["before_excerpt"]),
        ("After remediation excerpt", remediation["after_excerpt"]),
    ):
        if body:
            parts.append("")
            parts.append(heading)
            parts.append(body)
    if model["links"]:
        parts.append("")
        parts.append("Links")
        parts.extend(_plain_link_line(item) for item in model["links"])
    if model["identifiers"]:
        parts.append("")
        parts.append("Identifiers")
        parts.extend(_plain_field_line(label, value) for label, value in model["identifiers"])
    return "\n".join(part for part in parts if part is not None).strip()


def _render_markdown_sections(model: dict[str, Any]) -> str:
    remediation = model["remediation"]
    parts = [f"## {model['headline']}"]
    for heading, fields in _field_sections(model):
        if not fields:
            continue
        parts.append("")
        parts.append(f"### {heading}")
        parts.extend(_markdown_field_line(label, value) for label, value in fields)
    if remediation["summary"] or remediation["latest"] or remediation["steps"]:
        parts.append("")
        parts.append("### Remediation")
        if remediation["summary"]:
            parts.append(remediation["summary"])
        if remediation["latest"]:
            parts.append(remediation["latest"])
        parts.extend(remediation["steps"])
    for heading, body in (
        ("Failure excerpt", remediation["failure_excerpt"]),
        ("Before remediation excerpt", remediation["before_excerpt"]),
        ("After remediation excerpt", remediation["after_excerpt"]),
    ):
        if body:
            parts.append("")
            parts.append(f"### {heading}")
            parts.append(f"```text\n{_markdown_code_text(body)}\n```")
    if model["links"]:
        parts.append("")
        parts.append("### Links")
        parts.extend(_markdown_link_line(item) for item in model["links"])
    if model["identifiers"]:
        parts.append("")
        parts.append("### Identifiers")
        parts.extend(_markdown_field_line(label, value) for label, value in model["identifiers"])
    return "\n".join(parts).strip()


def _render_bbcode_sections(model: dict[str, Any]) -> str:
    remediation = model["remediation"]
    parts = [f"[b]{_auto_link_bbcode(model['headline'])}[/b]"]
    for heading, fields in _field_sections(model):
        if not fields:
            continue
        parts.append("")
        parts.append(f"[b]{heading}[/b]")
        parts.extend(_bbcode_field_line(label, value) for label, value in fields)
    if remediation["summary"] or remediation["latest"] or remediation["steps"]:
        parts.append("")
        parts.append("[b]Remediation[/b]")
        if remediation["summary"]:
            parts.append(_auto_link_bbcode(remediation["summary"]))
        if remediation["latest"]:
            parts.append(_auto_link_bbcode(remediation["latest"]))
        parts.extend(_auto_link_bbcode(line) for line in remediation["steps"])
    for heading, body in (
        ("Failure excerpt", remediation["failure_excerpt"]),
        ("Before remediation excerpt", remediation["before_excerpt"]),
        ("After remediation excerpt", remediation["after_excerpt"]),
    ):
        if body:
            parts.append("")
            parts.append(f"[b]{heading}[/b]")
            parts.append(f"[code]{_bbcode_code_text(body)}[/code]")
    if model["links"]:
        parts.append("")
        parts.append("[b]Links[/b]")
        parts.extend(_bbcode_link_line(item) for item in model["links"])
    if model["identifiers"]:
        parts.append("")
        parts.append("[b]Identifiers[/b]")
        parts.extend(_bbcode_field_line(label, value) for label, value in model["identifiers"])
    return "\n".join(parts).strip()


def _adf_text_nodes(text: str) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for segment, is_url in _split_text_with_urls(text):
        if is_url:
            nodes.append(
                {
                    "type": "text",
                    "text": segment,
                    "marks": [{"type": "link", "attrs": {"href": segment}}],
                }
            )
        else:
            nodes.append({"type": "text", "text": segment})
    return nodes or [{"type": "text", "text": text}]


def _adf_paragraph(text: str) -> dict[str, Any]:
    return {"type": "paragraph", "content": _adf_text_nodes(text)}


def _adf_labeled_paragraph(label: str, value: str) -> dict[str, Any]:
    return {
        "type": "paragraph",
        "content": [
            {"type": "text", "text": f"{label}: ", "marks": [{"type": "strong"}]},
            *_adf_text_nodes(value),
        ],
    }


def _adf_code_block(text: str) -> dict[str, Any]:
    return {"type": "codeBlock", "attrs": {}, "content": [{"type": "text", "text": text}]}


def _adf_link_list_item(item: dict[str, str]) -> dict[str, Any]:
    return {
        "type": "listItem",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": f"{item['label']}: ",
                        "marks": [{"type": "strong"}],
                    },
                    {
                        "type": "text",
                        "text": item["label"],
                        "marks": [{"type": "link", "attrs": {"href": item["url"]}}],
                    },
                ],
            }
        ],
    }


def _render_adf_sections(model: dict[str, Any]) -> dict[str, Any]:
    remediation = model["remediation"]
    content: list[dict[str, Any]] = [
        {"type": "heading", "attrs": {"level": 2}, "content": _adf_text_nodes(model["headline"])}
    ]
    for heading, fields in _field_sections(model):
        if not fields:
            continue
        content.append(
            {"type": "heading", "attrs": {"level": 3}, "content": _adf_text_nodes(heading)}
        )
        content.extend(_adf_labeled_paragraph(label, value) for label, value in fields)
    if remediation["summary"] or remediation["latest"] or remediation["steps"]:
        content.append(
            {"type": "heading", "attrs": {"level": 3}, "content": _adf_text_nodes("Remediation")}
        )
        if remediation["summary"]:
            content.append(_adf_paragraph(remediation["summary"]))
        if remediation["latest"]:
            content.append(_adf_paragraph(remediation["latest"]))
        if remediation["steps"]:
            content.append(
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [_adf_paragraph(line.removeprefix("- ").strip())],
                        }
                        for line in remediation["steps"]
                    ],
                }
            )
    for heading, body in (
        ("Failure excerpt", remediation["failure_excerpt"]),
        ("Before remediation excerpt", remediation["before_excerpt"]),
        ("After remediation excerpt", remediation["after_excerpt"]),
    ):
        if body:
            content.append(
                {"type": "heading", "attrs": {"level": 3}, "content": _adf_text_nodes(heading)}
            )
            content.append(_adf_code_block(body))
    if model["links"]:
        content.append(
            {"type": "heading", "attrs": {"level": 3}, "content": _adf_text_nodes("Links")}
        )
        content.append(
            {
                "type": "bulletList",
                "content": [_adf_link_list_item(item) for item in model["links"]],
            }
        )
    if model["identifiers"]:
        content.append(
            {"type": "heading", "attrs": {"level": 3}, "content": _adf_text_nodes("Identifiers")}
        )
        content.extend(
            _adf_labeled_paragraph(label, value) for label, value in model["identifiers"]
        )
    return {"type": "doc", "version": 1, "content": content}


def _render_discord_message(model: dict[str, Any]) -> dict[str, Any]:
    remediation = model["remediation"]
    content = _truncate(model["headline"], 1800)
    description_lines = [f"**{label}:** {value}" for label, value in model["problem"]]
    description = _truncate("\n".join(description_lines).strip(), 3500)
    fields: list[dict[str, Any]] = []
    for heading, entries, inline in (
        ("Current State", model["current_state"], True),
        ("Affected Scope", model["affected_scope"], True),
        ("Operator Guidance", model["operator_guidance"], False),
    ):
        if entries:
            fields.append(
                {
                    "name": heading,
                    "value": _truncate(
                        "\n".join(f"**{label}:** {value}" for label, value in entries),
                        1000,
                    ),
                    "inline": inline,
                }
            )
    remediation_lines: list[str] = []
    if remediation["summary"]:
        remediation_lines.append(remediation["summary"])
    if remediation["latest"]:
        remediation_lines.append(remediation["latest"])
    remediation_lines.extend(line.removeprefix("- ").strip() for line in remediation["steps"])
    if remediation_lines:
        fields.append(
            {
                "name": "Remediation",
                "value": _truncate("\n".join(remediation_lines), 1000),
                "inline": False,
            }
        )
    excerpt_label = ""
    excerpt_body = ""
    for label, body in (
        ("Failure excerpt", remediation["failure_excerpt"]),
        ("After remediation excerpt", remediation["after_excerpt"]),
        ("Before remediation excerpt", remediation["before_excerpt"]),
    ):
        if body:
            excerpt_label = label
            excerpt_body = body
            break
    if excerpt_body:
        fields.append(
            {
                "name": excerpt_label,
                "value": _truncate(excerpt_body, 1000),
                "inline": False,
            }
        )
    if model["links"]:
        fields.append(
            {
                "name": "Links",
                "value": _truncate(
                    "\n".join(_plain_link_line(item) for item in model["links"]),
                    1000,
                ),
                "inline": False,
            }
        )
    if model["identifiers"]:
        fields.append(
            {
                "name": "Identifiers",
                "value": _truncate(
                    "\n".join(f"**{label}:** {value}" for label, value in model["identifiers"]),
                    1000,
                ),
                "inline": False,
            }
        )
    return {
        "message": content,
        "content": content,
        "embeds": [
            {
                "title": _truncate(model["title"], 256),
                "description": description or _truncate(model["headline"], 1024),
                "color": _discord_embed_color(model),
                "fields": fields,
            }
        ],
    }


def render_provider_content(provider: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    canonical = canonical_from_payload(action, payload)
    model = _section_model(canonical, action, compact=provider in {"teams", "discord"})
    source = _text(payload.get("source") or canonical.get("event", {}).get("source") or "poundcake")
    visibility = _text(
        payload.get("visibility")
        or canonical.get("route", {}).get("provider_config", {}).get("visibility")
    )

    if provider == "rackspace_core":
        rendered = _render_bbcode_sections(model)
        if action == "create":
            return {
                "subject": model["title"],
                "body": rendered,
                "source": source,
                "severity": _text(canonical.get("alert", {}).get("severity")),
            }
        if action == "comment":
            return {"comment": rendered, "source": source, "visibility": visibility}
        if action == "close":
            return {"close_notes": rendered, "source": source, "visibility": visibility}
        return {}

    if provider == "jira":
        rendered = _render_adf_sections(model)
        if action == "create":
            return {
                "title": model["title"],
                "description": rendered,
            }
        if action == "comment":
            return {"comment": rendered}
        if action == "close":
            return {"close_notes": rendered}
        return {}

    if provider == "github":
        rendered = _render_markdown_sections(model)
        if action == "create":
            return {"title": model["title"], "description": rendered}
        if action == "comment":
            return {"comment": rendered}
        if action == "close":
            return {"close_notes": rendered}
        return {}

    if provider == "servicenow":
        rendered = _render_plain_sections(model)
        if action == "create":
            return {
                "title": model["title"],
                "description": rendered,
            }
        if action == "comment":
            return {"comment": rendered}
        if action == "close":
            return {"close_notes": rendered}
        return {}

    if provider == "pagerduty":
        rendered = _render_plain_sections(model)
        if action == "create":
            return {"title": model["title"], "description": rendered}
        if action == "comment":
            return {"comment": rendered}
        if action == "close":
            return {"close_notes": rendered}
        return {}

    if provider == "teams":
        rendered = _render_plain_sections(model)
        return {"message": rendered}

    if provider == "discord":
        return _render_discord_message(model)

    return {}
