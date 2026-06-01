"""`ttd log` — fast retroactive time capture."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from cyclopts import App, Parameter

from ttd.cli import collect
from ttd.cli.console import info
from ttd.cli.errors import cli_exit, cli_exit_cancelled
from ttd.cli.inputs import LogEntryInput, parse_optional_uuid
from ttd.cli.interactive import RunMode, format_missing_fields, resolve_run_mode
from ttd.cli.output import print_entry
from ttd.cli.parameters import InteractiveOpt
from ttd.cli.runtime import (
    ensure_db,
    parse_decimal,
    require_id,
    resolve_client,
    resolve_project,
)
from ttd.core.exceptions import ValidationError
from ttd.core.schemas import CreateDurationEntry, CreateIntervalEntry
from ttd.core.services import time_entries as entry_service
from ttd.core.time import parse_interval_parts, parse_interval_phrase, parse_work_date

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
        Parameter(
            name="--date",
            help="Work date (YYYY-MM-DD, today, yesterday, …). Defaults to today.",
        ),
    ] = None,
    when: Annotated[
        str | None,
        Parameter(
            name="--when",
            help="Natural-language interval (e.g. 'today 8am to 5pm').",
        ),
    ] = None,
    hours: Annotated[
        str | None, Parameter(name="--hours", help="Duration in hours.")
    ] = None,
    time_from: Annotated[
        str | None,
        Parameter(
            name="--from",
            help="Interval start (9am, 09:00, …). Use with --to; optional --date.",
        ),
    ] = None,
    time_to: Annotated[
        str | None,
        Parameter(
            name="--to",
            help="Interval end (5pm, 17:00, …). Use with --from; optional --date.",
        ),
    ] = None,
    note: str | None = None,
    non_billable: Annotated[bool, Parameter(name="--no-billable")] = False,
    interactive: InteractiveOpt = False,
) -> None:
    """Log time by duration (--hours) or interval (--when or --from/--to).

    Run `ttd log` with no arguments for guided prompts.
    """
    try:
        await ensure_db()
        values = LogEntryInput(
            client=client,
            project=project,
            project_id=parse_optional_uuid(project_id),
            work_date=work_date,
            when=when,
            hours=hours,
            time_from=time_from,
            time_to=time_to,
            note=note,
            non_billable=True if non_billable else None,
        )
        mode, missing = resolve_run_mode(
            subcommand=("log",),
            interactive_flag=interactive,
            provided=values.as_provided(),
            required_for_run=values.required_for_run(),
        )
        if mode == RunMode.ERROR:
            raise ValidationError(format_missing_fields(missing))
        if mode == RunMode.INTERACTIVE:
            values = await collect.collect_log_entry(values)

        owner = (
            await resolve_client(client_id=None, client_name=values.client)
            if values.client is not None
            else None
        )
        resolved = await resolve_project(
            project_id=values.project_id,
            client=owner,
            project_name=values.project,
        )
        billable = True if values.non_billable is None else not values.non_billable
        has_interval_parts = values.time_from is not None or values.time_to is not None
        has_when = values.when is not None

        if values.hours is not None:
            if has_when or has_interval_parts:
                raise ValidationError("Use --hours or an interval, not both")
            day = (
                parse_work_date(values.work_date)
                if values.work_date is not None
                else date.today()
            )
            entry = await entry_service.create_duration_entry(
                CreateDurationEntry(
                    project_id=require_id(resolved.id, "project"),
                    work_date=day,
                    billable_hours=parse_decimal(values.hours),
                    billable=billable,
                    note=values.note,
                )
            )
        elif has_when:
            if has_interval_parts:
                raise ValidationError("Use --when or --from/--to, not both")
            if values.work_date is not None:
                raise ValidationError("Use --when alone or --date with --from/--to")
            interval = parse_interval_phrase(values.when)
            entry = await entry_service.create_interval_entry(
                CreateIntervalEntry(
                    project_id=require_id(resolved.id, "project"),
                    work_date=interval.work_date,
                    started_at=interval.started_at,
                    ended_at=interval.ended_at,
                    billable=billable,
                    note=values.note,
                )
            )
        elif values.time_from is not None and values.time_to is not None:
            interval = parse_interval_parts(
                work_date=values.work_date,
                time_from=values.time_from,
                time_to=values.time_to,
            )
            entry = await entry_service.create_interval_entry(
                CreateIntervalEntry(
                    project_id=require_id(resolved.id, "project"),
                    work_date=interval.work_date,
                    started_at=interval.started_at,
                    ended_at=interval.ended_at,
                    billable=billable,
                    note=values.note,
                )
            )
        elif has_interval_parts:
            raise ValidationError("Provide both --from and --to")
        else:
            raise ValidationError("Provide --hours, --when, or both --from and --to")

        info("Logged entry:")
        print_entry(entry)
    except KeyboardInterrupt:
        cli_exit_cancelled()
    except BaseException as exc:
        cli_exit(exc)
