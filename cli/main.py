"""Main CLI entry point for bakeryctl."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import click

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cli.client import BakeryClient, BakeryClientError, ProviderInfo
from cli.utils import parse_json_object, print_error, print_info, print_output, print_success


def _client(ctx: click.Context) -> BakeryClient:
    return ctx.obj["client"]


def _output_format(ctx: click.Context) -> str:
    return str(ctx.obj["format"])


def _filtered_params(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value not in (None, "", [])}


def _print_monitor_list(
    ctx: click.Context,
    *,
    monitor_uuid: str | None = None,
    environment_label: str | None = None,
    provider_type: str | None = None,
    account_number: str | None = None,
) -> None:
    rows = _client(ctx).report_monitors(
        **_filtered_params(
            {
                "monitor_uuid": monitor_uuid,
                "environment_label": environment_label,
                "provider_type": provider_type,
                "account_number": account_number,
            }
        )
    )
    print_output(rows, _output_format(ctx))


def _resolve_monitor_ref(ctx: click.Context, monitor_ref: str) -> dict[str, Any]:
    rows = _client(ctx).report_monitors(monitor_uuid=monitor_ref)
    if rows:
        return rows[0]

    matches = [
        row
        for row in _client(ctx).report_monitors(limit=1000)
        if row.get("monitor_id") == monitor_ref
    ]
    if not matches:
        raise BakeryClientError(f"Monitor '{monitor_ref}' not found")
    return matches[0]


def _choose_provider(providers: list[ProviderInfo]) -> str:
    if len(providers) == 1:
        return providers[0].name
    click.echo("Enabled auth providers:")
    for provider in providers:
        click.echo(f"  - {provider.name}: {provider.label} ({provider.cli_login_mode})")
    selected = click.prompt(
        "Provider",
        type=click.Choice([provider.name for provider in providers], case_sensitive=False),
    )
    return str(selected)


@click.group()
@click.option(
    "--url",
    "-u",
    envvar="BAKERY_URL",
    default="http://localhost:8000",
    help="Bakery API URL",
)
@click.option(
    "--service-token",
    envvar="BAKERY_SERVICE_TOKEN",
    default="",
    help="Bakery operator service token",
)
@click.option(
    "--format",
    "-f",
    type=click.Choice(["table", "json"]),
    default="table",
    help="Output format",
)
@click.pass_context
def cli(ctx: click.Context, url: str, service_token: str, format: str) -> None:
    """bakeryctl - operator CLI for Bakery."""
    ctx.ensure_object(dict)
    ctx.obj["client"] = BakeryClient(url, service_token=service_token or None)
    ctx.obj["format"] = format


@cli.group()
def auth() -> None:
    """Authenticate bakeryctl sessions."""


@auth.command("providers")
@click.pass_context
def auth_providers(ctx: click.Context) -> None:
    try:
        providers = _client(ctx).get_auth_providers()
        print_output([provider.__dict__ for provider in providers], _output_format(ctx))
    except BakeryClientError as exc:
        print_error(str(exc))
        raise click.Abort() from exc


@auth.command("login")
@click.option("--provider", default=None, help="Auth provider name")
@click.option("--username", default=None, help="Username for password login")
@click.option("--password", default=None, help="Password for password login")
@click.pass_context
def auth_login(
    ctx: click.Context,
    provider: str | None,
    username: str | None,
    password: str | None,
) -> None:
    try:
        providers = _client(ctx).get_auth_providers()
        if not providers:
            raise BakeryClientError("No auth providers are enabled")
        selected = provider or _choose_provider(providers)
        provider_info = next((item for item in providers if item.name == selected), None)
        if provider_info is None:
            raise BakeryClientError(f"Provider '{selected}' is not enabled")
        if provider_info.device_login and not provider_info.password_login:
            start = _client(ctx).start_device_login(selected)
            print_info(
                f"Open {start.verification_uri_complete or start.verification_uri} and approve code {start.user_code}."
            )
            deadline = time.time() + max(start.expires_in, start.interval)
            while time.time() < deadline:
                time.sleep(max(start.interval, 1))
                poll = _client(ctx).poll_device_login(selected, start.device_code)
                status = str(poll.status or "").strip().lower()
                if status == "pending":
                    continue
                if status == "expired":
                    raise BakeryClientError(str(poll.detail or "Device login expired"))
                print_output(
                    poll.session.model_dump(mode="json") if poll.session is not None else {"status": status},
                    _output_format(ctx),
                )
                return
            raise BakeryClientError("Device login timed out before authorization completed")
        final_username = username or click.prompt("Username", type=str)
        final_password = password or click.prompt("Password", type=str, hide_input=True)
        result = _client(ctx).login(selected, final_username, final_password)
        print_output(result.__dict__, _output_format(ctx))
    except BakeryClientError as exc:
        print_error(str(exc))
        raise click.Abort() from exc


@auth.command("logout")
@click.pass_context
def auth_logout(ctx: click.Context) -> None:
    try:
        if _client(ctx).logout():
            print_success("Logged out and cleared the stored session.")
        else:
            print_success("No stored session was present.")
    except BakeryClientError as exc:
        print_error(str(exc))
        raise click.Abort() from exc


@auth.command("whoami")
@click.pass_context
def auth_whoami(ctx: click.Context) -> None:
    try:
        print_output(_client(ctx).whoami().__dict__, _output_format(ctx))
    except BakeryClientError as exc:
        print_error(str(exc))
        raise click.Abort() from exc


@cli.group()
def monitors() -> None:
    """Inspect monitor inventory and events."""


@monitors.command("list")
@click.option("--monitor-uuid", default=None)
@click.option("--environment", "environment_label", default=None)
@click.option("--provider", "provider_type", default=None)
@click.option("--account", "account_number", default=None)
@click.pass_context
def monitors_list(
    ctx: click.Context,
    monitor_uuid: str | None,
    environment_label: str | None,
    provider_type: str | None,
    account_number: str | None,
) -> None:
    try:
        _print_monitor_list(
            ctx,
            monitor_uuid=monitor_uuid,
            environment_label=environment_label,
            provider_type=provider_type,
            account_number=account_number,
        )
    except BakeryClientError as exc:
        print_error(str(exc))
        raise click.Abort() from exc


@monitors.command("get")
@click.argument("monitor_uuid")
@click.pass_context
def monitors_get(ctx: click.Context, monitor_uuid: str) -> None:
    try:
        rows = _client(ctx).report_monitors(monitor_uuid=monitor_uuid)
        if not rows:
            raise BakeryClientError(f"Monitor '{monitor_uuid}' not found")
        print_output(rows[0], _output_format(ctx))
    except BakeryClientError as exc:
        print_error(str(exc))
        raise click.Abort() from exc


@monitors.command("events")
@click.option("--monitor-uuid", default=None)
@click.option("--environment", "environment_label", default=None)
@click.option("--provider", "provider_type", default=None)
@click.option("--account", "account_number", default=None)
@click.option("--limit", default=100, type=int, show_default=True)
@click.pass_context
def monitors_events(
    ctx: click.Context,
    monitor_uuid: str | None,
    environment_label: str | None,
    provider_type: str | None,
    account_number: str | None,
    limit: int,
) -> None:
    try:
        rows = _client(ctx).report_monitor_events(
            **_filtered_params(
                {
                    "monitor_uuid": monitor_uuid,
                    "environment_label": environment_label,
                    "provider_type": provider_type,
                    "account_number": account_number,
                    "limit": limit,
                }
            )
        )
        print_output(rows, _output_format(ctx))
    except BakeryClientError as exc:
        print_error(str(exc))
        raise click.Abort() from exc


@monitors.command("remove")
@click.argument("monitor_refs", nargs=-1, required=True)
@click.option("--yes", "assume_yes", is_flag=True, help="Remove without interactive confirmation")
@click.pass_context
def monitors_remove(
    ctx: click.Context,
    monitor_refs: tuple[str, ...],
    assume_yes: bool,
) -> None:
    try:
        resolved = [_resolve_monitor_ref(ctx, monitor_ref) for monitor_ref in monitor_refs]
        if not assume_yes:
            for monitor in resolved:
                click.confirm(
                    (
                        f"Remove monitor {monitor['monitor_id']} ({monitor['monitor_uuid']}) "
                        "and delete its registry data?"
                    ),
                    abort=True,
                )
        results = [
            _client(ctx).remove_monitor(str(monitor["monitor_uuid"]))
            for monitor in resolved
        ]
        print_output(results[0] if len(results) == 1 else results, _output_format(ctx))
    except BakeryClientError as exc:
        print_error(str(exc))
        raise click.Abort() from exc


@cli.group()
def reports() -> None:
    """Query Bakery operator reports."""


@reports.command("overview")
@click.pass_context
def reports_overview(ctx: click.Context) -> None:
    try:
        print_output(_client(ctx).report_overview(), _output_format(ctx))
    except BakeryClientError as exc:
        print_error(str(exc))
        raise click.Abort() from exc


@reports.command("monitors")
@click.pass_context
def reports_monitors(ctx: click.Context) -> None:
    try:
        _print_monitor_list(ctx)
    except BakeryClientError as exc:
        print_error(str(exc))
        raise click.Abort() from exc


@reports.command("routes")
@click.option("--monitor-uuid", default=None)
@click.option("--environment", "environment_label", default=None)
@click.option("--provider", "provider_type", default=None)
@click.option("--account", "account_number", default=None)
@click.pass_context
def reports_routes(
    ctx: click.Context,
    monitor_uuid: str | None,
    environment_label: str | None,
    provider_type: str | None,
    account_number: str | None,
) -> None:
    try:
        rows = _client(ctx).report_routes(
            **_filtered_params(
                {
                    "monitor_uuid": monitor_uuid,
                    "environment_label": environment_label,
                    "provider_type": provider_type,
                    "account_number": account_number,
                }
            )
        )
        print_output(rows, _output_format(ctx))
    except BakeryClientError as exc:
        print_error(str(exc))
        raise click.Abort() from exc


@reports.command("providers")
@click.pass_context
def reports_providers(ctx: click.Context) -> None:
    try:
        print_output(_client(ctx).report_providers(), _output_format(ctx))
    except BakeryClientError as exc:
        print_error(str(exc))
        raise click.Abort() from exc


@reports.command("operations")
@click.pass_context
def reports_operations(ctx: click.Context) -> None:
    try:
        print_output(_client(ctx).report_operations(), _output_format(ctx))
    except BakeryClientError as exc:
        print_error(str(exc))
        raise click.Abort() from exc


@reports.command("backlog")
@click.pass_context
def reports_backlog(ctx: click.Context) -> None:
    try:
        print_output(_client(ctx).report_backlog(), _output_format(ctx))
    except BakeryClientError as exc:
        print_error(str(exc))
        raise click.Abort() from exc


@cli.group()
def jobs() -> None:
    """Queue and inspect collection jobs."""


@jobs.command("queue")
@click.option("--monitor-uuid", required=True)
@click.option(
    "--collector-type",
    required=True,
    type=click.Choice(["monitor_diagnostics", "cluster_inventory", "ticket_context"]),
)
@click.option("--parameters", default=None, help="JSON object of collector parameters")
@click.option("--reason", default=None, help="Human-readable reason for the job")
@click.pass_context
def jobs_queue(
    ctx: click.Context,
    monitor_uuid: str,
    collector_type: str,
    parameters: str | None,
    reason: str | None,
) -> None:
    try:
        print_output(
            _client(ctx).queue_job(
                monitor_uuid=monitor_uuid,
                collector_type=collector_type,
                parameters=parse_json_object(parameters, "parameters"),
                reason=reason,
            ),
            _output_format(ctx),
        )
    except (BakeryClientError, click.BadParameter) as exc:
        print_error(str(exc))
        raise click.Abort() from exc


@jobs.command("list")
@click.option("--monitor-uuid", default=None)
@click.option("--status", default=None)
@click.option("--collector-type", default=None)
@click.pass_context
def jobs_list(
    ctx: click.Context,
    monitor_uuid: str | None,
    status: str | None,
    collector_type: str | None,
) -> None:
    try:
        rows = _client(ctx).list_jobs(
            **_filtered_params(
                {
                    "monitor_uuid": monitor_uuid,
                    "status": status,
                    "collector_type": collector_type,
                }
            )
        )
        print_output(rows, _output_format(ctx))
    except BakeryClientError as exc:
        print_error(str(exc))
        raise click.Abort() from exc


@jobs.command("get")
@click.argument("job_id")
@click.pass_context
def jobs_get(ctx: click.Context, job_id: str) -> None:
    try:
        print_output(_client(ctx).get_job(job_id), _output_format(ctx))
    except BakeryClientError as exc:
        print_error(str(exc))
        raise click.Abort() from exc


@jobs.command("requeue")
@click.argument("job_id")
@click.pass_context
def jobs_requeue(ctx: click.Context, job_id: str) -> None:
    try:
        print_output(_client(ctx).requeue_job(job_id), _output_format(ctx))
    except BakeryClientError as exc:
        print_error(str(exc))
        raise click.Abort() from exc


@cli.group()
def bootstrap() -> None:
    """Manage monitor bootstrap credentials."""


@bootstrap.command("rotate")
@click.argument("monitor_id")
@click.pass_context
def bootstrap_rotate(ctx: click.Context, monitor_id: str) -> None:
    try:
        print_output(_client(ctx).rotate_bootstrap(monitor_id), _output_format(ctx))
    except BakeryClientError as exc:
        print_error(str(exc))
        raise click.Abort() from exc


def main() -> None:
    try:
        cli(obj={})
    except Exception as exc:  # noqa: BLE001
        print_error(str(exc))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
