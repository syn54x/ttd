"""`ttd project` commands."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from cyclopts import App, Parameter

from ttd.cli.console import success
from ttd.cli.errors import cli_exit
from ttd.cli.output import print_projects
from ttd.cli.runtime import ensure_db, parse_decimal, require_id, resolve_client
from ttd.core.models.enums import BillingMode
from ttd.core.schemas import CreateProject, UpdateProject
from ttd.core.services import projects as project_service

app = App(name="project", help="Manage projects.")


@app.command
async def add(
    name: str,
    *,
    client: Annotated[str, Parameter(name="--client", help="Client name.")],
    billing_mode: Annotated[
        str, Parameter(name="--billing-mode", help="hourly or fixed_price.")
    ] = "hourly",
    rate: Annotated[str | None, Parameter(name="--rate")] = None,
    currency: Annotated[str | None, Parameter(name="--currency")] = None,
    contract_total: Annotated[
        str | None, Parameter(name="--contract-total")
    ] = None,
    soft_max_hours: Annotated[
        str | None, Parameter(name="--soft-max-hours")
    ] = None,
) -> None:
    """Add a project under a client."""
    try:
        await ensure_db()
        owner = await resolve_client(client_id=None, client_name=client)
        mode = _parse_billing_mode(billing_mode)
        project = await project_service.create_project(
            CreateProject(
                client_id=require_id(owner.id, "client"),
                name=name,
                billing_mode=mode,
                hourly_rate=parse_decimal(rate) if rate is not None else None,
                currency=currency,
                contract_total=(
                    parse_decimal(contract_total)
                    if contract_total is not None
                    else None
                ),
                soft_max_hours=(
                    parse_decimal(soft_max_hours)
                    if soft_max_hours is not None
                    else None
                ),
            )
        )
        success(f"Created project {_short(project.id)} ({project.name})")
    except BaseException as exc:
        cli_exit(exc)


@app.command(name="list")
async def list_projects(
    *,
    client: Annotated[str | None, Parameter(name="--client")] = None,
    client_id: Annotated[UUID | None, Parameter(name="--client-id")] = None,
) -> None:
    """List projects for a client."""
    try:
        await ensure_db()
        owner = await resolve_client(client_id=client_id, client_name=client)
        projects = await project_service.list_projects_for_client(
            require_id(owner.id, "client")
        )
        print_projects(projects)
    except BaseException as exc:
        cli_exit(exc)


@app.command
async def update(
    project_id: UUID,
    *,
    name: str | None = None,
    rate: Annotated[str | None, Parameter(name="--rate")] = None,
    currency: Annotated[str | None, Parameter(name="--currency")] = None,
    contract_total: Annotated[
        str | None, Parameter(name="--contract-total")
    ] = None,
    soft_max_hours: Annotated[
        str | None, Parameter(name="--soft-max-hours")
    ] = None,
    clear_rate_override: Annotated[
        bool, Parameter(name="--clear-rate-override")
    ] = False,
) -> None:
    """Update a project."""
    try:
        await ensure_db()
        project = await project_service.update_project(
            project_id,
            UpdateProject(
                name=name,
                hourly_rate=parse_decimal(rate) if rate is not None else None,
                currency=currency,
                contract_total=(
                    parse_decimal(contract_total)
                    if contract_total is not None
                    else None
                ),
                soft_max_hours=(
                    parse_decimal(soft_max_hours)
                    if soft_max_hours is not None
                    else None
                ),
                clear_rate_override=clear_rate_override,
            ),
        )
        success(f"Updated project {_short(project.id)} ({project.name})")
    except BaseException as exc:
        cli_exit(exc)


@app.command
async def delete(project_id: UUID) -> None:
    """Delete a project (only when it has no time entries)."""
    try:
        await ensure_db()
        await project_service.delete_project(project_id)
        success(f"Deleted project {_short(project_id)}")
    except BaseException as exc:
        cli_exit(exc)


def _parse_billing_mode(value: str) -> BillingMode:
    normalized = value.strip().lower().replace("-", "_")
    try:
        return BillingMode(normalized)
    except ValueError as exc:
        from ttd.core.exceptions import ValidationError

        raise ValidationError(
            f"Invalid billing mode '{value}'; use hourly or fixed_price"
        ) from exc


def _short(project_id: UUID | None) -> str:
    return str(project_id)[:8] if project_id is not None else "--------"
