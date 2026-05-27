"""`ttd entries` — list and correct time entries."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from cyclopts import App, Parameter

from ttd.cli import collect
from ttd.cli.console import info, success
from ttd.cli.errors import cli_exit, cli_exit_cancelled
from ttd.cli.inputs import EntryDeleteInput, EntryEditInput, billable_flag
from ttd.cli.interactive import RunMode, format_missing_fields, resolve_run_mode
from ttd.cli.output import print_entries, print_entry
from ttd.cli.parameters import InteractiveOpt
from ttd.cli.runtime import (
    ensure_db,
    parse_clock_on_date,
    parse_date,
    parse_decimal,
    require_id,
    resolve_client,
    resolve_project,
)
from ttd.core.exceptions import ValidationError
from ttd.core.models.enums import EntryMode
from ttd.core.models.time_entry import TimeEntry
from ttd.core.schemas import UpdateDurationEntry, UpdateIntervalEntry
from ttd.core.services import time_entries as entry_service

app = App(name="entries", help="List and edit time entries.")


def _filter_by_period(
    entries: list[TimeEntry],
    *,
    from_date: date | None,
    to_date: date | None,
) -> list[TimeEntry]:
    filtered = entries
    if from_date is not None:
        filtered = [e for e in filtered if e.work_date >= from_date]
    if to_date is not None:
        filtered = [e for e in filtered if e.work_date <= to_date]
    return filtered


@app.command(name="list")
async def list_entries(
    *,
    client: Annotated[str | None, Parameter(name="--client")] = None,
    project: Annotated[str | None, Parameter(name="--project")] = None,
    project_id: Annotated[UUID | None, Parameter(name="--project-id")] = None,
    from_date: Annotated[
        str | None, Parameter(name="--from", help="Start date (YYYY-MM-DD).")
    ] = None,
    to_date: Annotated[
        str | None, Parameter(name="--to", help="End date (YYYY-MM-DD).")
    ] = None,
) -> None:
    """List entries for a project, optionally filtered by work date."""
    try:
        await ensure_db()
        owner = (
            await resolve_client(client_id=None, client_name=client)
            if client is not None
            else None
        )
        resolved = await resolve_project(
            project_id=project_id,
            client=owner,
            project_name=project,
        )
        entries = await entry_service.list_time_entries_for_project(
            require_id(resolved.id, "project")
        )
        period_start = parse_date(from_date) if from_date is not None else None
        period_end = parse_date(to_date) if to_date is not None else None
        print_entries(
            _filter_by_period(entries, from_date=period_start, to_date=period_end)
        )
    except BaseException as exc:
        cli_exit(exc)


@app.command
async def edit(
    entry_id: Annotated[UUID | None, Parameter(help="Entry UUID.")] = None,
    *,
    work_date: Annotated[str | None, Parameter(name="--date")] = None,
    hours: Annotated[str | None, Parameter(name="--hours")] = None,
    time_from: Annotated[str | None, Parameter(name="--from")] = None,
    time_to: Annotated[str | None, Parameter(name="--to")] = None,
    note: str | None = None,
    non_billable: Annotated[bool | None, Parameter(name="--no-billable")] = None,
    billable: Annotated[bool | None, Parameter(name="--billable")] = None,
    interactive: InteractiveOpt = False,
) -> None:
    """Edit a time entry. No args runs guided prompts."""
    try:
        await ensure_db()
        values = EntryEditInput(
            entry_id=entry_id,
            work_date=work_date,
            hours=hours,
            time_from=time_from,
            time_to=time_to,
            note=note,
            non_billable=non_billable,
            billable=billable,
        )
        mode, missing = resolve_run_mode(
            subcommand=("entries", "edit"),
            interactive_flag=interactive,
            provided=values.as_provided(),
            required_for_run=(),
        )
        if mode == RunMode.ERROR:
            raise ValidationError(format_missing_fields(missing))
        if mode == RunMode.INTERACTIVE:
            values = await collect.collect_entry_edit(values)

        entry_id_val = values.require_entry_id()
        entry = await entry_service.get_time_entry(entry_id_val)
        billable_flag_val = billable_flag(
            non_billable=values.non_billable,
            billable=values.billable,
        )

        day = parse_date(values.work_date) if values.work_date is not None else None

        if entry.entry_mode == EntryMode.DURATION:
            if values.time_from is not None or values.time_to is not None:
                raise ValidationError("Duration entries use --hours, not --from/--to")
            updated = await entry_service.update_duration_entry(
                entry_id_val,
                UpdateDurationEntry(
                    work_date=day,
                    billable_hours=(
                        parse_decimal(values.hours) if values.hours else None
                    ),
                    billable=billable_flag_val,
                    note=values.note,
                ),
            )
        else:
            if values.hours is not None:
                raise ValidationError("Interval entries use --from/--to, not --hours")
            started = (
                parse_clock_on_date(day or entry.work_date, values.time_from)
                if values.time_from
                else None
            )
            ended = (
                parse_clock_on_date(day or entry.work_date, values.time_to)
                if values.time_to
                else None
            )
            updated = await entry_service.update_interval_entry(
                entry_id_val,
                UpdateIntervalEntry(
                    work_date=day,
                    started_at=started,
                    ended_at=ended,
                    billable=billable_flag_val,
                    note=values.note,
                ),
            )
        info("Updated entry:")
        print_entry(updated)
    except KeyboardInterrupt:
        cli_exit_cancelled()
    except BaseException as exc:
        cli_exit(exc)


@app.command
async def delete(
    entry_id: Annotated[UUID | None, Parameter(help="Entry UUID.")] = None,
    *,
    interactive: InteractiveOpt = False,
) -> None:
    """Delete a time entry. No args runs guided prompts."""
    try:
        await ensure_db()
        values = EntryDeleteInput(entry_id=entry_id)
        mode, missing = resolve_run_mode(
            subcommand=("entries", "delete"),
            interactive_flag=interactive,
            provided=values.as_provided(),
            required_for_run=("entry_id",),
        )
        if mode == RunMode.ERROR:
            raise ValidationError(format_missing_fields(missing))
        if mode == RunMode.INTERACTIVE:
            values = await collect.collect_entry_delete(values)
            if values.cancelled:
                cli_exit_cancelled()

        eid = values.entry_id
        if eid is None:
            raise ValidationError("Entry is required.")
        await entry_service.delete_time_entry(eid)
        success(f"Deleted entry {str(eid)[:8]}")
    except KeyboardInterrupt:
        cli_exit_cancelled()
    except BaseException as exc:
        cli_exit(exc)
