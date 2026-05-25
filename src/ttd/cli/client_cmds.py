"""`ttd client` commands."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from cyclopts import App, Parameter

from ttd.cli.console import success
from ttd.cli.errors import cli_exit
from ttd.cli.output import print_clients
from ttd.cli.runtime import ensure_db, parse_decimal
from ttd.core.schemas import CreateClient, UpdateClient
from ttd.core.services import clients as client_service

app = App(name="client", help="Manage clients.")


@app.command
async def add(
    name: str,
    *,
    rate: Annotated[str, Parameter(name="--rate", help="Default hourly rate.")],
    currency: Annotated[str, Parameter(name="--currency")] = "USD",
) -> None:
    """Add a client."""
    try:
        await ensure_db()
        client = await client_service.create_client(
            CreateClient(
                name=name,
                default_hourly_rate=parse_decimal(rate),
                currency=currency,
            )
        )
        success(f"Created client {_short(client.id)} ({client.name})")
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
    client_id: UUID,
    *,
    name: str | None = None,
    rate: Annotated[str | None, Parameter(name="--rate")] = None,
    currency: Annotated[str | None, Parameter(name="--currency")] = None,
) -> None:
    """Update a client."""
    try:
        await ensure_db()
        client = await client_service.update_client(
            client_id,
            UpdateClient(
                name=name,
                default_hourly_rate=parse_decimal(rate) if rate is not None else None,
                currency=currency,
            ),
        )
        success(f"Updated client {_short(client.id)} ({client.name})")
    except BaseException as exc:
        cli_exit(exc)


@app.command
async def delete(client_id: UUID) -> None:
    """Delete a client (only when it has no projects)."""
    try:
        await ensure_db()
        await client_service.delete_client(client_id)
        success(f"Deleted client {_short(client_id)}")
    except BaseException as exc:
        cli_exit(exc)


def _short(client_id: UUID | None) -> str:
    return str(client_id)[:8] if client_id is not None else "--------"
