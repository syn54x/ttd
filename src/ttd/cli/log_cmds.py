"""`ttd log` — fast retroactive time capture."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from cyclopts import App, Parameter

from ttd.cli.console import info
from ttd.cli.errors import cli_exit
from ttd.cli.output import print_entry
from ttd.cli.runtime import (
    ensure_db,
    parse_clock_on_date,
    parse_date,
    parse_decimal,
    require_id,
    resolve_client,
    resolve_project,
)
from ttd.core.schemas import CreateDurationEntry, CreateIntervalEntry
from ttd.core.services import time_entries as entry_service

app = App(name="log", help="Log retroactive time on a project.")


@app.default
async def log_entry(
    *,
    client: Annotated[str | None, Parameter(name="--client")] = None,
    project: Annotated[str | None, Parameter(name="--project")] = None,
    project_id: Annotated[
        str | None, Parameter(name="--project-id", help="Project UUID.")
    ] = None,
    work_date: Annotated[
        str | None,
        Parameter(name="--date", help="Work date (YYYY-MM-DD). Defaults to today."),
    ] = None,
    hours: Annotated[
        str | None, Parameter(name="--hours", help="Duration in hours.")
    ] = None,
    time_from: Annotated[
        str | None, Parameter(name="--from", help="Interval start (HH:MM UTC).")
    ] = None,
    time_to: Annotated[
        str | None, Parameter(name="--to", help="Interval end (HH:MM UTC).")
    ] = None,
    note: str | None = None,
    non_billable: Annotated[bool, Parameter(name="--no-billable")] = False,
) -> None:
    """Log time by duration (--hours) or interval (--from/--to)."""
    try:
        await ensure_db()
        pid = UUID(project_id) if project_id is not None else None
        owner = (
            await resolve_client(client_id=None, client_name=client)
            if client is not None
            else None
        )
        resolved = await resolve_project(
            project_id=pid,
            client=owner,
            project_name=project,
        )
        day = parse_date(work_date) if work_date is not None else date.today()
        billable = not non_billable

        if hours is not None:
            if time_from is not None or time_to is not None:
                from ttd.core.exceptions import ValidationError

                raise ValidationError("Use --hours or --from/--to, not both")
            entry = await entry_service.create_duration_entry(
                CreateDurationEntry(
                    project_id=require_id(resolved.id, "project"),
                    work_date=day,
                    billable_hours=parse_decimal(hours),
                    billable=billable,
                    note=note,
                )
            )
        elif time_from is not None and time_to is not None:
            started = parse_clock_on_date(day, time_from)
            ended = parse_clock_on_date(day, time_to)
            entry = await entry_service.create_interval_entry(
                CreateIntervalEntry(
                    project_id=require_id(resolved.id, "project"),
                    work_date=day,
                    started_at=started,
                    ended_at=ended,
                    billable=billable,
                    note=note,
                )
            )
        else:
            from ttd.core.exceptions import ValidationError

            raise ValidationError("Provide --hours or both --from and --to")

        info("Logged entry:")
        print_entry(entry)
    except BaseException as exc:
        cli_exit(exc)
