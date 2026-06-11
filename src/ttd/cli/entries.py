"""`ttd entry …` commands."""

import json
from datetime import date, datetime, timedelta
from typing import Annotated

from cyclopts import Parameter

from ttd.cli._output import console, success, table
from ttd.cli._run import TtdApp, with_db
from ttd.config.loader import get_settings
from ttd.core.errors import TtdError
from ttd.core.money import format_hours
from ttd.services import entries as svc
from ttd.storage.models import enum_value

app = TtdApp(name="entry", help="List and edit time entries.")


def _parse_date(raw: str | None) -> date | None:
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise TtdError(f"Dates must be YYYY-MM-DD (got '{raw}')") from exc


def _period(
    week: bool, month: bool, date_from: str | None, date_to: str | None
) -> tuple[date | None, date | None]:
    today = date.today()
    if week:
        start = today - timedelta(days=today.weekday())
        return start, start + timedelta(days=6)
    if month:
        return today.replace(day=1), today
    return _parse_date(date_from), _parse_date(date_to)


@app.command(name="list")
@with_db
async def list_(
    *,
    project: Annotated[str | None, Parameter(name=["--project", "-p"])] = None,
    client: str | None = None,
    date_from: Annotated[str | None, Parameter(name="--from")] = None,
    date_to: Annotated[str | None, Parameter(name="--to")] = None,
    week: Annotated[bool, Parameter(help="This week")] = False,
    month: Annotated[bool, Parameter(help="This month")] = False,
    as_json: Annotated[bool, Parameter(name="--json")] = False,
) -> None:
    """List entries, newest day last."""
    start, end = _period(week, month, date_from, date_to)
    rows = await svc.list_entries(
        project_slug=project, client_slug=client, date_from=start, date_to=end
    )
    if as_json:
        payload = [
            {
                "id": str(r.entry.id),
                "client": r.client.slug,
                "project": r.project.slug,
                "date": r.entry.work_date.isoformat(),
                "start": r.entry.started_at.isoformat() if r.entry.started_at else None,
                "end": r.entry.ended_at.isoformat() if r.entry.ended_at else None,
                "seconds": r.entry.seconds,
                "note": r.entry.note,
                "tags": r.entry.tags,
                "billable": r.entry.billable,
                "source": enum_value(r.entry.source),
                "invoiced": r.entry.invoice_id is not None,
            }
            for r in rows
        ]
        console.print_json(json.dumps(payload))
        return
    if not rows:
        console.print('[muted]No entries — `ttd log "today 9am to 5pm"`[/muted]')
        return
    t = table("ID", "Date", "Project", "Time", "Hours", "Note")
    last_day = None
    total = 0
    for r in rows:
        e = r.entry
        total += e.seconds
        day = e.work_date.strftime("%a %b %-d")
        when = (
            f"{e.started_at:%-I:%M%p}–{e.ended_at:%-I:%M%p}".lower()
            if e.started_at and e.ended_at
            else "[muted]—[/muted]"
        )
        flags = ("" if e.billable else " [muted](nb)[/muted]") + (
            " [accent]·inv[/accent]" if e.invoice_id else ""
        )
        t.add_row(
            str(e.id)[:8],
            day if day != last_day else "",
            f"{r.client.slug}/{r.project.slug}",
            when,
            format_hours(e.seconds) + flags,
            e.note,
        )
        last_day = day
    console.print(t)
    console.print(f"Total: [bold]{format_hours(total)}[/bold]")


@app.command(name="edit")
@with_db
async def edit(
    uid: Annotated[str, Parameter(help="Entry id (prefix ok, from `ttd entry list`)")],
    *,
    time: Annotated[str | None, Parameter(help='New time, e.g. "9-11:30"')] = None,
    note: Annotated[str | None, Parameter(name=["--note", "-n"])] = None,
    tags: str | None = None,
    project: Annotated[str | None, Parameter(name=["--project", "-p"])] = None,
    client: str | None = None,
    billable: bool | None = None,
) -> None:
    """Edit an entry (refuses if it's on an invoice)."""
    entry = await svc.edit_entry(
        uid,
        now=datetime.now(),
        spec=time,
        note=note,
        tags=tags,
        billable=billable,
        project_slug=project,
        client_slug=client,
        settings=get_settings(),
    )
    success(f"Updated entry {str(entry.id)[:8]}")


@app.command(name="rm")
@with_db
async def rm(uid: str) -> None:
    """Delete an entry (refuses if it's on an invoice)."""
    entry = await svc.delete_entry(uid)
    success(f"Deleted entry {str(entry.id)[:8]} ({format_hours(entry.seconds)})")
