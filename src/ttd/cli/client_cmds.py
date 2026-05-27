"""`ttd client` commands."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from cyclopts import App, Parameter

from ttd.cli import collect
from ttd.cli.console import success
from ttd.cli.errors import cli_exit, cli_exit_cancelled
from ttd.cli.inputs import ClientAddInput, ClientDeleteInput, ClientUpdateInput
from ttd.cli.interactive import RunMode, format_missing_fields, resolve_run_mode
from ttd.cli.output import print_clients
from ttd.cli.parameters import InteractiveOpt
from ttd.cli.runtime import ensure_db, parse_decimal
from ttd.core.exceptions import ValidationError
from ttd.core.schemas import CreateClient, UpdateClient
from ttd.core.services import clients as client_service

app = App(name="client", help="Manage clients.")


@app.command
async def add(
    name: Annotated[str | None, Parameter(help="Client name.")] = None,
    *,
    rate: Annotated[
        str | None, Parameter(name="--rate", help="Default hourly rate.")
    ] = None,
    currency: Annotated[str | None, Parameter(name="--currency")] = None,
    interactive: InteractiveOpt = False,
) -> None:
    """Add a client.

    Run with no arguments for guided prompts, or pass flags for scripting.
    Use -i to prompt for any missing fields.
    """
    try:
        await ensure_db()
        values = ClientAddInput(name=name, rate=rate, currency=currency)
        mode, missing = resolve_run_mode(
            subcommand=("client", "add"),
            interactive_flag=interactive,
            provided=values.as_provided(),
            required_for_run=("name", "rate"),
        )
        if mode == RunMode.ERROR:
            raise ValidationError(format_missing_fields(missing))
        if mode == RunMode.INTERACTIVE:
            values = await collect.collect_client_add(values)
            if values.currency is None:
                values.currency = "USD"

        if values.name is None or values.rate is None:
            raise ValidationError(format_missing_fields(["name", "rate"]))

        client = await client_service.create_client(
            CreateClient(
                name=values.name,
                default_hourly_rate=parse_decimal(values.rate),
                currency=values.currency or "USD",
            )
        )
        success(f"Created client {_short(client.id)} ({client.name})")
    except KeyboardInterrupt:
        cli_exit_cancelled()
    except BaseException as exc:
        cli_exit(exc)


@app.command(name="list")
async def list_clients() -> None:
    """List clients."""
    try:
        await ensure_db()
        print_clients(await client_service.list_clients())
    except BaseException as exc:
        cli_exit(exc)


@app.command
async def update(
    client_id: Annotated[UUID | None, Parameter(help="Client UUID.")] = None,
    *,
    name: str | None = None,
    rate: Annotated[str | None, Parameter(name="--rate")] = None,
    currency: Annotated[str | None, Parameter(name="--currency")] = None,
    interactive: InteractiveOpt = False,
) -> None:
    """Update a client. No args opens guided prompts; -i fills missing fields."""
    try:
        await ensure_db()
        values = ClientUpdateInput(
            client_id=client_id,
            name=name,
            rate=rate,
            currency=currency,
        )
        mode, missing = resolve_run_mode(
            subcommand=("client", "update"),
            interactive_flag=interactive,
            provided=values.as_provided(),
            required_for_run=(),
        )
        if mode == RunMode.ERROR:
            raise ValidationError(format_missing_fields(missing))
        if mode == RunMode.INTERACTIVE:
            values = await collect.collect_client_update(values)

        client = await client_service.update_client(
            values.require_client_id(),
            UpdateClient(
                name=values.name,
                default_hourly_rate=(
                    parse_decimal(values.rate) if values.rate is not None else None
                ),
                currency=values.currency,
            ),
        )
        success(f"Updated client {_short(client.id)} ({client.name})")
    except KeyboardInterrupt:
        cli_exit_cancelled()
    except BaseException as exc:
        cli_exit(exc)


@app.command
async def delete(
    client_id: Annotated[UUID | None, Parameter(help="Client UUID.")] = None,
    *,
    interactive: InteractiveOpt = False,
) -> None:
    """Delete a client (only when it has no projects). No args opens guided prompts."""
    try:
        await ensure_db()
        values = ClientDeleteInput(client_id=client_id)
        mode, missing = resolve_run_mode(
            subcommand=("client", "delete"),
            interactive_flag=interactive,
            provided=values.as_provided(),
            required_for_run=("client_id",),
        )
        if mode == RunMode.ERROR:
            raise ValidationError(format_missing_fields(missing))
        if mode == RunMode.INTERACTIVE:
            values = await collect.collect_client_delete(values)
            if values.cancelled:
                cli_exit_cancelled()

        cid = values.client_id
        if cid is None:
            raise ValidationError("Client is required (use -i or --client-id).")
        await client_service.delete_client(cid)
        success(f"Deleted client {_short(cid)}")
    except KeyboardInterrupt:
        cli_exit_cancelled()
    except BaseException as exc:
        cli_exit(exc)


def _short(client_id: UUID | None) -> str:
    return str(client_id)[:8] if client_id is not None else "--------"
