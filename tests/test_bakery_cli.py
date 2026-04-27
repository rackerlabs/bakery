from __future__ import annotations

import sys
from pathlib import Path

from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cli import main as cli_main
from cli.client import BakeryClientError
from cli.main import cli


def test_bakeryctl_help_exposes_operator_command_groups() -> None:
    runner = CliRunner()

    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "auth" in result.output
    assert "monitors" in result.output
    assert "reports" in result.output
    assert "jobs" in result.output
    assert "bootstrap" in result.output


class _FakeClient:
    instances: list["_FakeClient"] = []
    fail_remove = False

    def __init__(self, *_args, **_kwargs) -> None:
        self.removed: list[str] = []
        self.report_calls: list[dict[str, object]] = []
        self.instances.append(self)

    def report_monitors(self, **params):
        self.report_calls.append(params)
        monitor_one = {
            "monitor_uuid": "monitor-uuid-1",
            "monitor_id": "alpha-monitor",
            "status": "unreachable",
            "environment_label": "prod",
            "region": None,
            "cluster_name": "cluster-a",
            "namespace": "rackspace",
            "release_name": "poundcake",
            "tags": [],
            "route_sync_required": False,
            "route_count": 0,
            "outage_route_count": 0,
            "last_checkin_at": None,
            "unreachable_at": None,
            "created_at": "2026-04-01T00:00:00Z",
            "updated_at": "2026-04-01T00:00:00Z",
            "last_seen_payload": None,
        }
        monitor_two = {
            **monitor_one,
            "monitor_uuid": "monitor-uuid-2",
            "monitor_id": "beta-monitor",
        }
        if params.get("monitor_uuid") == "monitor-uuid-1":
            return [monitor_one]
        if params.get("monitor_uuid"):
            return []
        if params.get("limit") == 1000:
            return [monitor_one, monitor_two]
        return []

    def remove_monitor(self, monitor_uuid: str):
        if self.fail_remove:
            raise BakeryClientError("remove failed")
        self.removed.append(monitor_uuid)
        return {
            "monitor_uuid": monitor_uuid,
            "monitor_id": "removed-monitor",
            "removed_at": "2026-04-27T14:00:00Z",
            "removed_by": "operator:admin",
            "affected_counts": {"monitors": 1},
        }


def _install_fake_client(monkeypatch) -> type[_FakeClient]:
    _FakeClient.instances = []
    _FakeClient.fail_remove = False
    monkeypatch.setattr(cli_main, "BakeryClient", _FakeClient)
    return _FakeClient


def test_bakeryctl_monitors_help_exposes_remove_command() -> None:
    runner = CliRunner()

    result = runner.invoke(cli, ["monitors", "--help"])

    assert result.exit_code == 0
    assert "remove" in result.output


def test_bakeryctl_monitors_remove_resolves_uuid_and_monitor_id(monkeypatch) -> None:
    fake_client = _install_fake_client(monkeypatch)
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "--format",
            "json",
            "monitors",
            "remove",
            "monitor-uuid-1",
            "beta-monitor",
            "--yes",
        ],
    )

    assert result.exit_code == 0
    assert fake_client.instances[-1].removed == ["monitor-uuid-1", "monitor-uuid-2"]
    assert '"monitor_uuid": "monitor-uuid-1"' in result.output
    assert '"monitor_uuid": "monitor-uuid-2"' in result.output


def test_bakeryctl_monitors_remove_requires_confirmation(monkeypatch) -> None:
    fake_client = _install_fake_client(monkeypatch)
    runner = CliRunner()

    result = runner.invoke(cli, ["monitors", "remove", "monitor-uuid-1"], input="n\n")

    assert result.exit_code != 0
    assert fake_client.instances[-1].removed == []
    assert "Remove monitor alpha-monitor" in result.output


def test_bakeryctl_monitors_remove_surfaces_api_errors(monkeypatch) -> None:
    fake_client = _install_fake_client(monkeypatch)
    fake_client.fail_remove = True
    runner = CliRunner()

    result = runner.invoke(cli, ["monitors", "remove", "monitor-uuid-1", "--yes"])

    assert result.exit_code != 0
    assert "remove failed" in result.output
