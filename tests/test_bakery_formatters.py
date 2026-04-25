from __future__ import annotations

from copy import deepcopy

from bakery.formatters import provider_config_from_context, render_provider_content


def _target_down_payload() -> dict:
    return {
        "context": {
            "_canonical": {
                "schema_version": 1,
                "event": {
                    "name": "fallback_create",
                    "operation": "open",
                    "managed": True,
                    "source": "poundcake",
                },
                "route": {
                    "label": "Primary route",
                    "execution_target": "rackspace_core",
                    "destination_target": "primary",
                    "provider_config": {},
                },
                "order": {
                    "id": 258,
                    "req_id": "c68371eb-464e-449a-9259-95196c6accf9",
                },
                "alert": {
                    "group_name": "target-down",
                    "severity": "warning",
                    "status": "firing",
                    "fingerprint": "bc0617eb89973e9e",
                    "instance": "",
                    "starts_at": "2026-04-22T19:34:09Z",
                    "ends_at": None,
                    "labels": {
                        "alertname": "target-down-warning",
                        "group_name": "target-down",
                        "job": "default/rabbitmq-cluster-operator",
                        "namespace": "rabbitmq-system",
                        "severity": "warning",
                    },
                    "annotations": {
                        "summary": "One or more targets are unreachable.",
                        "description": (
                            "100% of the default/rabbitmq-cluster-operator/ targets in "
                            "rabbitmq-system namespace are down. "
                            "This warning alert fires after 10m."
                        ),
                    },
                    "generator_url": (
                        "http://kube-prometheus-stack-prometheus.monitoring:9090/graph"
                        "?g0.expr=100+%2A+%28count+by+%28cluster%2C+job%2C+namespace%2C+service%29+"
                        "%28up+%3D%3D+0%29+%2F+count+by+%28cluster%2C+job%2C+namespace%2C+service%29+"
                        "%28up%29%29+%3E+10&g0.tab=1"
                    ),
                },
                "links": [
                    {
                        "label": "Source",
                        "url": (
                            "http://kube-prometheus-stack-prometheus.monitoring:9090/graph"
                            "?g0.expr=100+%2A+%28count+by+%28cluster%2C+job%2C+namespace%2C+service%29+"
                            "%28up+%3D%3D+0%29+%2F+count+by+%28cluster%2C+job%2C+namespace%2C+service%29+"
                            "%28up%29%29+%3E+10&g0.tab=1"
                        ),
                    },
                    {"label": "Runbook", "url": "default_runbook_url"},
                    {"label": "Dashboard", "url": "default_dashboard_url"},
                ],
                "text": {
                    "headline": "Alert requires attention",
                    "summary": (
                        "PoundCake did not find a matching workflow for this alert and "
                        "opened a communication for human response."
                    ),
                    "detail": "No matching workflow is configured for this alert.",
                    "resolution": "",
                },
                "remediation": {
                    "summary": {
                        "total": 0,
                        "succeeded": 0,
                        "failed": 0,
                        "skipped": 0,
                        "incomplete": 0,
                    },
                    "steps": [],
                    "before_excerpt": "",
                    "after_excerpt": "",
                    "failure_excerpt": "",
                    "latest_completed_step": None,
                },
            }
        }
    }


def _remediation_payload() -> dict:
    return {
        "context": {
            "_canonical": {
                "schema_version": 1,
                "event": {
                    "name": "escalation_open",
                    "operation": "open",
                    "managed": True,
                    "source": "poundcake",
                },
                "route": {
                    "label": "Primary route",
                    "execution_target": "rackspace_core",
                    "destination_target": "primary",
                    "provider_config": {},
                },
                "order": {"id": 7, "req_id": "REQ-7"},
                "alert": {
                    "group_name": "filesystem-response",
                    "severity": "warning",
                    "status": "firing",
                    "fingerprint": "fp-7",
                    "instance": "host7",
                    "starts_at": "2026-03-13T12:00:00Z",
                    "ends_at": None,
                    "labels": {"alertname": "DiskFull"},
                    "annotations": {
                        "summary": "Filesystem almost full",
                        "description": "Usage exceeded the alert threshold.",
                    },
                    "generator_url": "https://prometheus.example/graph?g0.expr=disk",
                },
                "links": [
                    {"label": "Source", "url": "https://prometheus.example/graph?g0.expr=disk"},
                    {"label": "Runbook", "url": "https://docs.example.com/runbooks/filesystem"},
                ],
                "text": {
                    "headline": "Alert requires attention",
                    "summary": "PoundCake escalated this alert.",
                    "detail": "Automated remediation failed. See https://docs.example.com/runbooks/filesystem",
                    "resolution": "",
                },
                "remediation": {
                    "summary": {
                        "total": 2,
                        "succeeded": 1,
                        "failed": 1,
                        "skipped": 0,
                        "incomplete": 0,
                    },
                    "steps": [
                        {
                            "task_key": "step_1_cleanup_var",
                            "status": "succeeded",
                            "outcome": "Freed 12 GB on /var",
                        },
                        {
                            "task_key": "step_2_verify_var",
                            "status": "failed",
                            "outcome": "Permission denied while validating free space",
                        },
                    ],
                    "before_excerpt": "stdout:\nDisk usage before cleanup was 95% on /var",
                    "after_excerpt": "",
                    "failure_excerpt": (
                        "Authorization: Bearer secret-token\n\n"
                        "stderr:\nPermission denied while validating free space"
                    ),
                    "latest_completed_step": {
                        "task_key": "step_1_cleanup_var",
                        "status": "succeeded",
                        "outcome": "Freed 12 GB on /var",
                    },
                },
            }
        }
    }


def test_render_provider_content_rackspace_core_uses_operator_first_sections() -> None:
    rendered = render_provider_content("rackspace_core", "create", _target_down_payload())

    assert rendered["subject"].startswith("Alert requires attention")
    assert "[b]Current State[/b]" in rendered["body"]
    assert "[b]Problem[/b]" in rendered["body"]
    assert "[b]Affected Scope[/b]" in rendered["body"]
    assert "[b]Links[/b]" in rendered["body"]
    assert "[b]Identifiers[/b]" in rendered["body"]
    assert "[b]Operator Guidance[/b]" not in rendered["body"]
    assert "[b]Remediation[/b]" not in rendered["body"]
    assert "[b]Alert Summary:[/b] One or more targets are unreachable." in rendered["body"]
    assert (
        "[b]Impact:[/b] 100% of the default/rabbitmq-cluster-operator/ targets in "
        "rabbitmq-system namespace are down. This warning alert fires after 10m."
    ) in rendered["body"]
    assert (
        "[b]Automation Context:[/b] PoundCake did not find a matching workflow for this "
        "alert and opened a communication for human response. "
        "No matching workflow is configured for this alert."
    ) in rendered["body"]
    assert "[b]Namespace:[/b] rabbitmq-system" in rendered["body"]
    assert "[b]Job:[/b] default/rabbitmq-cluster-operator" in rendered["body"]
    assert "[b]Service:[/b]" not in rendered["body"]
    assert (
        "[b]Source:[/b] [url=http://kube-prometheus-stack-prometheus.monitoring" in rendered["body"]
    )
    assert "[b]Runbook:[/b] [url=default_runbook_url]Runbook[/url]" in rendered["body"]
    assert "[b]Dashboard:[/b] [url=default_dashboard_url]Dashboard[/url]" in rendered["body"]
    assert "[b]Alert Rule:[/b] target-down-warning" in rendered["body"]
    assert "[b]Alert Group:[/b] target-down" in rendered["body"]
    assert rendered["severity"] == "warning"

    heading_positions = [
        rendered["body"].index("[b]Current State[/b]"),
        rendered["body"].index("[b]Problem[/b]"),
        rendered["body"].index("[b]Affected Scope[/b]"),
        rendered["body"].index("[b]Links[/b]"),
        rendered["body"].index("[b]Identifiers[/b]"),
    ]
    assert heading_positions == sorted(heading_positions)


def test_render_provider_content_jira_returns_adf_comment() -> None:
    rendered = render_provider_content("jira", "comment", _target_down_payload())

    assert rendered["comment"]["type"] == "doc"
    assert rendered["comment"]["version"] == 1


def test_render_provider_content_github_returns_labeled_markdown_sections() -> None:
    rendered = render_provider_content("github", "comment", _target_down_payload())

    assert "## Alert requires attention" in rendered["comment"]
    assert "### Current State" in rendered["comment"]
    assert "### Problem" in rendered["comment"]
    assert "### Affected Scope" in rendered["comment"]
    assert "### Links" in rendered["comment"]
    assert "### Identifiers" in rendered["comment"]
    assert "### Operator Guidance" not in rendered["comment"]
    assert "### Remediation" not in rendered["comment"]
    assert "- **Alert Summary:** One or more targets are unreachable." in rendered["comment"]
    assert (
        "- **Automation Context:** PoundCake did not find a matching workflow for this alert "
        "and opened a communication for human response. "
        "No matching workflow is configured for this alert."
    ) in rendered["comment"]
    assert "- **Namespace:** rabbitmq-system" in rendered["comment"]
    assert "- **Job:** default/rabbitmq-cluster-operator" in rendered["comment"]
    assert "- **Runbook:** [Runbook](default_runbook_url)" in rendered["comment"]
    assert "- **Dashboard:** [Dashboard](default_dashboard_url)" in rendered["comment"]
    assert "- **Alert Rule:** target-down-warning" in rendered["comment"]
    assert "- **Alert Group:** target-down" in rendered["comment"]


def test_render_provider_content_discord_returns_operator_first_embed_payload() -> None:
    rendered = render_provider_content("discord", "create", _target_down_payload())

    assert rendered["message"] == "Alert requires attention"
    assert rendered["embeds"][0]["title"]
    assert rendered["embeds"][0]["color"] == 0xF79009
    assert (
        "**Alert Summary:** One or more targets are unreachable."
        in rendered["embeds"][0]["description"]
    )
    assert (
        "**Impact:** 100% of the default/rabbitmq-cluster-operator/"
        in rendered["embeds"][0]["description"]
    )
    field_names = [field["name"] for field in rendered["embeds"][0]["fields"]]
    assert "Current State" in field_names
    assert "Affected Scope" in field_names
    assert "Links" in field_names
    assert "Identifiers" in field_names
    assert "Operator Guidance" not in field_names
    assert "Remediation" not in field_names

    scope_field = next(
        field for field in rendered["embeds"][0]["fields"] if field["name"] == "Affected Scope"
    )
    assert "**Namespace:** rabbitmq-system" in scope_field["value"]
    assert "**Job:** default/rabbitmq-cluster-operator" in scope_field["value"]
    assert "**Service:**" not in scope_field["value"]

    links_field = next(
        field for field in rendered["embeds"][0]["fields"] if field["name"] == "Links"
    )
    assert "Runbook: default_runbook_url" in links_field["value"]


def test_render_provider_content_rackspace_core_close_uses_resolution_and_hides_empty_remediation() -> (
    None
):
    payload = deepcopy(_target_down_payload())
    payload["context"]["_canonical"]["event"]["name"] = "fallback_notify"
    payload["context"]["_canonical"]["event"]["operation"] = "close"
    payload["context"]["_canonical"]["alert"]["status"] = "resolved"
    payload["context"]["_canonical"]["alert"]["ends_at"] = "2026-04-22T20:14:09Z"
    payload["context"]["_canonical"]["text"]["headline"] = "Alert cleared"
    payload["context"]["_canonical"]["text"][
        "summary"
    ] = "PoundCake observed that the alert cleared and is updating the communication."
    payload["context"]["_canonical"]["text"][
        "detail"
    ] = "No matching workflow is configured for this alert."
    payload["context"]["_canonical"]["text"]["resolution"] = "Closing communication."

    rendered = render_provider_content("rackspace_core", "close", payload)

    assert "[b]Ended:[/b] 2026-04-22T20:14:09Z" in rendered["close_notes"]
    assert "[b]Resolution:[/b] Closing communication." in rendered["close_notes"]
    assert "[b]Automation Context:[/b]" not in rendered["close_notes"]
    assert "[b]Remediation[/b]" not in rendered["close_notes"]
    assert "[b]Before remediation excerpt[/b]" not in rendered["close_notes"]
    assert "[b]After remediation excerpt[/b]" not in rendered["close_notes"]


def test_render_provider_content_rackspace_core_redacts_failure_excerpt() -> None:
    rendered = render_provider_content("rackspace_core", "create", _remediation_payload())

    assert "[b]Remediation[/b]" in rendered["body"]
    assert "[b]Failure excerpt[/b]" in rendered["body"]
    assert "secret-token" not in rendered["body"]
    assert "[REDACTED]" in rendered["body"]


def test_render_provider_content_discord_resolved_messages_use_green_embed() -> None:
    payload = deepcopy(_remediation_payload())
    payload["context"]["_canonical"]["event"]["name"] = "resolved_success_close"
    payload["context"]["_canonical"]["event"]["operation"] = "close"
    payload["context"]["_canonical"]["order"]["remediation_outcome"] = "succeeded"
    payload["context"]["_canonical"]["alert"]["severity"] = "critical"
    payload["context"]["_canonical"]["alert"]["status"] = "resolved"
    payload["context"]["_canonical"]["alert"]["ends_at"] = "2026-03-13T12:03:00Z"
    payload["context"]["_canonical"]["text"]["headline"] = "Alert resolved"
    payload["context"]["_canonical"]["text"]["resolution"] = "Closing communication after recovery."
    payload["context"]["_canonical"]["remediation"]["summary"]["failed"] = 0
    payload["context"]["_canonical"]["remediation"]["summary"]["succeeded"] = 2
    payload["context"]["_canonical"]["remediation"][
        "after_excerpt"
    ] = "stdout:\nDisk usage after cleanup was 40% on /var"
    payload["context"]["_canonical"]["remediation"]["failure_excerpt"] = ""
    payload["context"]["_canonical"]["remediation"]["steps"][1]["status"] = "succeeded"
    payload["context"]["_canonical"]["remediation"]["steps"][1][
        "outcome"
    ] = "Confirmed disk recovery on /var"
    payload["context"]["_canonical"]["remediation"]["latest_completed_step"] = {
        "task_key": "step_2_verify_var",
        "status": "succeeded",
        "outcome": "Confirmed disk recovery on /var",
    }

    rendered = render_provider_content("discord", "close", payload)

    assert rendered["embeds"][0]["color"] == 0x12B76A
    field_names = [field["name"] for field in rendered["embeds"][0]["fields"]]
    assert "After remediation excerpt" in field_names


def test_render_provider_content_servicenow_close_includes_before_and_after_excerpts() -> None:
    payload = deepcopy(_remediation_payload())
    payload["context"]["_canonical"]["event"]["name"] = "resolved_success_close"
    payload["context"]["_canonical"]["event"]["operation"] = "close"
    payload["context"]["_canonical"]["order"]["remediation_outcome"] = "succeeded"
    payload["context"]["_canonical"]["text"]["resolution"] = "Closing communication after recovery."
    payload["context"]["_canonical"]["remediation"]["summary"]["failed"] = 0
    payload["context"]["_canonical"]["remediation"]["summary"]["succeeded"] = 2
    payload["context"]["_canonical"]["remediation"][
        "after_excerpt"
    ] = "stdout:\nDisk usage after cleanup was 40% on /var"
    payload["context"]["_canonical"]["remediation"]["failure_excerpt"] = ""
    payload["context"]["_canonical"]["remediation"]["steps"][1]["status"] = "succeeded"
    payload["context"]["_canonical"]["remediation"]["steps"][1][
        "outcome"
    ] = "Confirmed disk recovery on /var"

    rendered = render_provider_content("servicenow", "close", payload)

    assert "Remediation" in rendered["close_notes"]
    assert "Before remediation excerpt" in rendered["close_notes"]
    assert "After remediation excerpt" in rendered["close_notes"]


def test_provider_config_from_context_prefers_route_provider_config() -> None:
    payload = {
        "context": {
            "provider_config": {"owner": "rackerlabs", "repo": "poundcake"},
            "githubOwner": "legacy-owner",
            "githubRepo": "legacy-repo",
        }
    }

    config = provider_config_from_context("github", payload)

    assert config["owner"] == "rackerlabs"
    assert config["repo"] == "poundcake"
