"""Output helpers for bakeryctl."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
from typing import Any

import click


def to_plain_data(data: Any) -> Any:
    if hasattr(data, "model_dump"):
        return to_plain_data(data.model_dump(mode="json", by_alias=True))
    if is_dataclass(data) and not isinstance(data, type):
        return {key: to_plain_data(value) for key, value in asdict(data).items()}
    if isinstance(data, dict):
        return {key: to_plain_data(value) for key, value in data.items()}
    if isinstance(data, (list, tuple)):
        return [to_plain_data(item) for item in data]
    return data


def _table_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"), sort_keys=True)
    if value is None:
        return "-"
    return str(value)


def format_table(data: Any) -> str:
    plain = to_plain_data(data)
    if isinstance(plain, dict):
        if not plain:
            return "No data"
        width = max(len(str(key)) for key in plain)
        return "\n".join(f"{str(key).ljust(width)}  {_table_value(value)}" for key, value in plain.items())
    if isinstance(plain, list):
        if not plain:
            return "No items"
        if not isinstance(plain[0], dict):
            return "\n".join(str(item) for item in plain)
        keys = list(plain[0].keys())
        widths = {key: len(str(key)) for key in keys}
        rows: list[dict[str, str]] = []
        for item in plain:
            row: dict[str, str] = {}
            for key in keys:
                rendered = _table_value(item.get(key))
                if len(rendered) > 72:
                    rendered = rendered[:69] + "..."
                row[key] = rendered
                widths[key] = max(widths[key], len(rendered))
            rows.append(row)
        header = "  ".join(str(key).ljust(widths[key]) for key in keys)
        separator = "  ".join("-" * widths[key] for key in keys)
        body = ["  ".join(row[key].ljust(widths[key]) for key in keys) for row in rows]
        return "\n".join([header, separator, *body])
    return str(plain)


def print_output(data: Any, output_format: str) -> None:
    plain = to_plain_data(data)
    if output_format == "json":
        click.echo(json.dumps(plain, indent=2, sort_keys=False))
        return
    click.echo(format_table(plain))


def print_error(message: str) -> None:
    click.echo(click.style(f"ERROR: {message}", fg="red"), err=True)


def print_info(message: str) -> None:
    click.echo(click.style(f"INFO: {message}", fg="blue"))


def print_success(message: str) -> None:
    click.echo(click.style(f"OK: {message}", fg="green"))


def parse_json_object(value: str | None, label: str) -> dict[str, Any] | None:
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise click.BadParameter(f"{label} must be valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise click.BadParameter(f"{label} must decode to a JSON object")
    return parsed
