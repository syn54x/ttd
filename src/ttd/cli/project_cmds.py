"""`ttd project` commands."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from cyclopts import App, Parameter

from ttd.cli import collect
from ttd.cli.console import success
from ttd.cli.errors import cli_exit, cli_exit_cancelled
from ttd.cli.inputs import ProjectAddInput, ProjectDeleteInput, ProjectUpdateInput
from ttd.cli.interactive import RunMode, format_missing_fields, resolve_run_mode
from ttd.cli.output import print_projects
from ttd.cli.parameters import InteractiveOpt
from ttd.cli.runtime import ensure_db, parse_decimal, require_id, resolve_client
from ttd.cli.sort import PROJECT_SORTS, sort_items
from ttd.core.exceptions import ValidationError
from ttd.core.models.enums import BillingMode
from ttd.core.schemas import CreateProject, UpdateProject
from ttd.core.services import projects as project_service

app = App(name="project", help="Manage projects.")


def _parse_billing_mode(value: str) -> BillingMode:
    normalized = value.strip().lower().replace("-", "_")
    try:
        return BillingMode(normalized)
    except ValueError as exc:
        raise ValidationError(
            f"Invalid billing mode '{value}'; use hourly or fixed_price"
        ) from exc


@app.command
async def add(
    name: Annotated[str | None, Parameter(help="Project name.")] = None,
    *,
    client: Annotated[
        str | None, Parameter(name="--client", help="Client name.")
    ] = None,
    billing_mode: Annotated[
        str | None, Parameter(name="--billing-mode", help="hourly or fixed_price.")
    ] = None,
    rate: Annotated[str | None, Parameter(name="--rate")] = None,
    currency: Annotated[str | None, Parameter(name="--currency")] = None,
    contract_total: Annotated[str | None, Parameter(name="--contract-total")] = None,
    soft_max_hours: Annotated[str | None, Parameter(name="--soft-max-hours")] = None,
    rounding_minutes: Annotated[
        int | None,
        Parameter(name="--rounding-minutes", help="Export round-up minutes."),
    ] = None,
    interactive: InteractiveOpt = False,
) -> None:
    """Add a project. No args runs guided prompts; -i fills missing fields."""
    try:
        await ensure_db()
        values = ProjectAddInput(
            name=name,
            client=client,
            billing_mode=billing_mode,
            rate=rate,
            currency=currency,
            contract_total=contract_total,
            soft_max_hours=soft_max_hours,
        )
        mode, missing = resolve_run_mode(
            subcommand=("project", "add"),
            interactive_flag=interactive,
            provided=values.as_provided(),
            required_for_run=("name", "client"),
        )
        if mode == RunMode.ERROR:
            raise ValidationError(format_missing_fields(missing))
        if mode == RunMode.INTERACTIVE:
            values = await collect.collect_project_add(values)

        if values.client is None or values.name is None:
            raise ValidationError(format_missing_fields(["name", "client"]))

        owner = await resolve_client(client_id=None, client_name=values.client)
        mode_enum = _parse_billing_mode(values.billing_mode or "hourly")
        project = await project_service.create_project(
            CreateProject(
                client_id=require_id(owner.id, "client"),
                name=values.name,
                billing_mode=mode_enum,
                hourly_rate=(
                    parse_decimal(values.rate) if values.rate is not None else None
                ),
                currency=values.currency,
                contract_total=(
                    parse_decimal(values.contract_total)
                    if values.contract_total is not None
                    else None
                ),
                soft_max_hours=(
                    parse_decimal(values.soft_max_hours)
                    if values.soft_max_hours is not None
                    else None
                ),
                rounding_increment_minutes=rounding_minutes,
            )
        )
        success(f"Created project {_short(project.id)} ({project.name})")
    except KeyboardInterrupt:
        cli_exit_cancelled()
    except BaseException as exc:
        cli_exit(exc)


@app.command(name="list")
async def list_projects(
    *,
    client: Annotated[str | None, Parameter(name="--client")] = None,
    client_id: Annotated[UUID | None, Parameter(name="--client-id")] = None,
    sort: Annotated[
        str | None,
        Parameter(
            name="--sort",
            help=(
                "Sort field; prefix with '-' for descending "
                "(default: name). Fields: client, id, mode, name."
            ),
        ),
    ] = None,
) -> None:
    """List projects for a client."""
    try:
        await ensure_db()
        owner = await resolve_client(client_id=client_id, client_name=client)
        projects = await project_service.list_projects_for_client(
            require_id(owner.id, "client")
        )
        print_projects(
            sort_items(
                projects,
                allowed=PROJECT_SORTS,
                sort=sort,
                default="name",
            )
        )
    except BaseException as exc:
        cli_exit(exc)


@app.command
async def update(
    project_id: Annotated[UUID | None, Parameter(help="Project UUID.")] = None,
    *,
    name: str | None = None,
    rate: Annotated[str | None, Parameter(name="--rate")] = None,
    currency: Annotated[str | None, Parameter(name="--currency")] = None,
    contract_total: Annotated[str | None, Parameter(name="--contract-total")] = None,
    soft_max_hours: Annotated[str | None, Parameter(name="--soft-max-hours")] = None,
    clear_rate_override: Annotated[
        bool, Parameter(name="--clear-rate-override")
    ] = False,
    rounding_minutes: Annotated[
        int | None,
        Parameter(name="--rounding-minutes", help="Export round-up minutes."),
    ] = None,
    clear_rounding: Annotated[
        bool, Parameter(name="--clear-rounding", help="Remove rounding increment.")
    ] = False,
    interactive: InteractiveOpt = False,
) -> None:
    """Update a project. No args runs guided prompts."""
    try:
        await ensure_db()
        values = ProjectUpdateInput(
            project_id=project_id,
            name=name,
            rate=rate,
            currency=currency,
            contract_total=contract_total,
            soft_max_hours=soft_max_hours,
            clear_rate_override=clear_rate_override,
        )
        mode, missing = resolve_run_mode(
            subcommand=("project", "update"),
            interactive_flag=interactive,
            provided=values.as_provided(),
            required_for_run=(),
        )
        if mode == RunMode.ERROR:
            raise ValidationError(format_missing_fields(missing))
        if mode == RunMode.INTERACTIVE:
            values = await collect.collect_project_update(values)

        project = await project_service.update_project(
            values.require_project_id(),
            UpdateProject(
                name=values.name,
                hourly_rate=(
                    parse_decimal(values.rate) if values.rate is not None else None
                ),
                currency=values.currency,
                contract_total=(
                    parse_decimal(values.contract_total)
                    if values.contract_total is not None
                    else None
                ),
                soft_max_hours=(
                    parse_decimal(values.soft_max_hours)
                    if values.soft_max_hours is not None
                    else None
                ),
                clear_rate_override=values.clear_rate_override,
                rounding_increment_minutes=rounding_minutes,
                clear_rounding_increment=clear_rounding,
            ),
        )
        success(f"Updated project {_short(project.id)} ({project.name})")
    except KeyboardInterrupt:
        cli_exit_cancelled()
    except BaseException as exc:
        cli_exit(exc)


@app.command
async def delete(
    project_id: Annotated[UUID | None, Parameter(help="Project UUID.")] = None,
    *,
    interactive: InteractiveOpt = False,
) -> None:
    """Delete a project when it has no entries. No args runs guided prompts."""
    try:
        await ensure_db()
        values = ProjectDeleteInput(project_id=project_id)
        mode, missing = resolve_run_mode(
            subcommand=("project", "delete"),
            interactive_flag=interactive,
            provided=values.as_provided(),
            required_for_run=("project_id",),
        )
        if mode == RunMode.ERROR:
            raise ValidationError(format_missing_fields(missing))
        if mode == RunMode.INTERACTIVE:
            values = await collect.collect_project_delete(values)
            if values.cancelled:
                cli_exit_cancelled()

        pid = values.project_id
        if pid is None:
            raise ValidationError("Project is required.")
        await project_service.delete_project(pid)
        success(f"Deleted project {_short(pid)}")
    except KeyboardInterrupt:
        cli_exit_cancelled()
    except BaseException as exc:
        cli_exit(exc)


def _short(project_id: UUID | None) -> str:
    return str(project_id)[:8] if project_id is not None else "--------"
