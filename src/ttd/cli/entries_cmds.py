"""`ttd entries` — list and correct time entries."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from cyclopts import App, Parameter

from ttd.cli.console import info, success
from ttd.cli.errors import cli_exit
from ttd.cli.output import print_entries, print_entry
from ttd.cli.runtime import (
    ensure_db,
    parse_clock_on_date,
    parse_date,
    parse_decimal,
    require_id,
    resolve_client,
    resolve_project,
)
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
            _filter_by_period(
                entries, from_date=period_start, to_date=period_end
            )
        )
    except BaseException as exc:
        cli_exit(exc)


@app.command
async def edit(
    entry_id: UUID,
    *,
    work_date: Annotated[str | None, Parameter(name="--date")] = None,
    hours: Annotated[str | None, Parameter(name="--hours")] = None,
    time_from: Annotated[str | None, Parameter(name="--from")] = None,
    time_to: Annotated[str | None, Parameter(name="--to")] = None,
    note: str | None = None,
    non_billable: Annotated[bool | None, Parameter(name="--no-billable")] = None,
    billable: Annotated[bool | None, Parameter(name="--billable")] = None,
) -> None:
    """Edit a time entry (fields depend on duration vs interval mode)."""
    try:
        await ensure_db()
        entry = await entry_service.get_time_entry(entry_id)
        if non_billable is True and billable is not None:
            from ttd.core.exceptions import ValidationError

            raise ValidationError("Use only one of --billable or --no-billable")
        billable_flag: bool | None = None
        if non_billable is True:
            billable_flag = False
        elif billable is not None:
            billable_flag = billable

        day = parse_date(work_date) if work_date is not None else None

        if entry.entry_mode == EntryMode.DURATION:
            if time_from is not None or time_to is not None:
                from ttd.core.exceptions import ValidationError

                raise ValidationError(
                    "Duration entries use --hours, not --from/--to"
                )
            updated = await entry_service.update_duration_entry(
                entry_id,
                UpdateDurationEntry(
                    work_date=day,
                    billable_hours=parse_decimal(hours) if hours else None,
                    billable=billable_flag,
                    note=note,
                ),
            )
        else:
            if hours is not None:
                from ttd.core.exceptions import ValidationError

                raise ValidationError(
                    "Interval entries use --from/--to, not --hours"
                )
            started = (
                parse_clock_on_date(day or entry.work_date, time_from)
                if time_from
                else None
            )
            ended = (
                parse_clock_on_date(day or entry.work_date, time_to)
                if time_to
                else None
            )
            updated = await entry_service.update_interval_entry(
                entry_id,
                UpdateIntervalEntry(
                    work_date=day,
                    started_at=started,
                    ended_at=ended,
                    billable=billable_flag,
                    note=note,
                ),
            )
        info("Updated entry:")
        print_entry(updated)
    except BaseException as exc:
        cli_exit(exc)


@app.command
async def delete(entry_id: UUID) -> None:
    """Delete a time entry."""
    try:
        await ensure_db()
        await entry_service.delete_time_entry(entry_id)
        success(f"Deleted entry {str(entry_id)[:8]}")
    except BaseException as exc:
        cli_exit(exc)
