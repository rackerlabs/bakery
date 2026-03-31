from __future__ import annotations

import sys
from pathlib import Path

from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
