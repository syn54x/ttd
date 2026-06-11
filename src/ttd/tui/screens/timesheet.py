"""Timesheet: day/week/month spans, day-grouped entries, add/edit/delete."""

from datetime import date, datetime, timedelta
from typing import ClassVar, Literal, cast

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.coordinate import Coordinate
from textual.widgets import DataTable, Label

from ttd.cli._pickers import describe_timespec, split_project_choice, validate_timespec
from ttd.config.loader import get_settings
from ttd.core.errors import TtdError
from ttd.core.money import format_hours
from ttd.reporting import periods
from ttd.services import entries as entry_svc
from ttd.tui._data import hours_for_row, project_options, split_and_log
from ttd.tui.screens._base import TtdScreen
from ttd.tui.widgets.forms import FormField, FormModal
from ttd.tui.widgets.modals import ConfirmModal, QuickLogModal

Span = Literal["day", "week", "month"]


def _entry_spec(entry) -> str:
    """Reconstruct an unambiguous, round-trippable time spec for an entry."""
    if entry.started_at and entry.ended_at:
        return f"{entry.work_date} {entry.started_at:%H:%M} to {entry.ended_at:%H:%M}"
    h, rem = divmod(entry.seconds, 3600)
    duration = f"{h}h{rem // 60}m" if h else f"{rem // 60}m"
    return f"{entry.work_date} {duration}"


class TimesheetScreen(TtdScreen):
    nav_id = "timesheet"

    BINDINGS: ClassVar = [
        *TtdScreen.BINDINGS,
        ("d", "span('day')", "day"),
        ("w", "span('week')", "week"),
        ("m", "span('month')", "month"),
        ("left_square_bracket", "shift(-1)", "prev"),
        ("right_square_bracket", "shift(1)", "next"),
        ("g", "today", "today"),
        ("a", "add_entry", "add"),
        ("e", "edit_entry", "edit"),
        ("x", "delete_entry", "delete"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.span: Span = "day"
        self.anchor_date: date = date.today()

    def compose_content(self) -> ComposeResult:
        with Vertical(id="timesheet"):
            yield Label("", id="day-title", classes="section-title")
            yield DataTable(id="day-table", cursor_type="row")
            yield Label("", id="day-total", classes="muted")

    def setup(self) -> None:
        table = self.query_one("#day-table", DataTable)
        table.add_columns("date", "project", "time", "hours", "note", "flags")

    def _period(self) -> periods.Period:
        if self.span == "day":
            return periods.day_period(self.anchor_date)
        if self.span == "week":
            return periods.week_period(self.anchor_date, get_settings().display.week_start)
        return periods.month_period(self.anchor_date)

    async def render_data(self) -> None:
        period = self._period()
        rows = await entry_svc.list_entries(date_from=period.start, date_to=period.end)
        table = self.query_one("#day-table", DataTable)
        table.clear()
        total = 0
        last_day = None
        for r in rows:
            total += r.entry.seconds
            flags = []
            if not r.entry.billable:
                flags.append("nb")
            if r.entry.invoice_id is not None:
                flags.append("inv")
            day_label = r.entry.work_date.strftime("%a %b %-d")
            table.add_row(
                day_label if day_label != last_day else "",
                f"{r.client.slug}/{r.project.slug}",
                hours_for_row(r.entry),
                format_hours(r.entry.seconds),
                r.entry.note,
                ",".join(flags),
                key=str(r.entry.id),
            )
            last_day = day_label
        title = period.label
        if self.span == "day":
            days_ago = (date.today() - self.anchor_date).days
            title += {0: " · today", 1: " · yesterday"}.get(days_ago, "")
        self.query_one("#day-title", Label).update(f"{title}  [dim]({self.span})[/dim]")
        self.query_one("#day-total", Label).update(
            f"{len(rows)} entr{'y' if len(rows) == 1 else 'ies'} · {format_hours(total)}"
            "   [dim]d/w/m span · \\[ ] prev/next · g today · a add · e edit · x delete[/dim]"
        )

    async def action_span(self, span: str) -> None:
        if span in ("day", "week", "month"):
            self.span = cast("Span", span)
        await self.refresh_data()

    async def action_shift(self, delta: int) -> None:
        if self.span == "day":
            self.anchor_date += timedelta(days=delta)
        elif self.span == "week":
            self.anchor_date += timedelta(days=7 * delta)
        else:
            first = self.anchor_date.replace(day=1)
            if delta > 0:
                self.anchor_date = (first + timedelta(days=32)).replace(day=1)
            else:
                self.anchor_date = (first - timedelta(days=1)).replace(day=1)
        await self.refresh_data()

    async def action_today(self) -> None:
        self.anchor_date = date.today()
        await self.refresh_data()

    def _selected_entry_id(self) -> str | None:
        table = self.query_one("#day-table", DataTable)
        if table.row_count == 0 or table.cursor_row is None:
            return None
        key = table.coordinate_to_cell_key(Coordinate(table.cursor_row, 0)).row_key.value
        return str(key) if key is not None else None

    async def action_add_entry(self) -> None:
        options = await project_options()
        if not options:
            self.notify("no projects yet", severity="warning")
            return
        prefix = ""
        if self.span == "day" and self.anchor_date != date.today():
            prefix = f"{self.anchor_date.isoformat()} "

        async def _log(payload: dict | None) -> None:
            if payload is None:
                return
            try:
                await split_and_log(payload, now=datetime.now())
            except TtdError as exc:
                self.notify(str(exc), severity="error")
            await self.refresh_data()

        self.app.push_screen(QuickLogModal(options, initial_spec=prefix), _log)

    async def action_edit_entry(self) -> None:
        uid = self._selected_entry_id()
        if uid is None:
            return
        entry = await entry_svc.find_entry(uid)
        if entry.invoice_id is not None:
            self.notify("entry is on an invoice — void it first", severity="warning")
            return
        options = await project_options()
        rows = await entry_svc.list_entries(date_from=entry.work_date, date_to=entry.work_date)
        current = next((r for r in rows if r.entry.id == entry.id), None)
        current_project = f"{current.client.slug}/{current.project.slug}" if current else None

        initial = {
            "time": _entry_spec(entry),
            "note": entry.note,
            "tags": entry.tags,
            "billable": entry.billable,
            "project": current_project,
        }
        form = FormModal(
            f"edit entry {uid[:8]}",
            [
                FormField(
                    "time",
                    "Time",
                    kind="spec",
                    value=initial["time"],
                    validate=validate_timespec,
                    preview=describe_timespec,
                    required=True,
                ),
                FormField("note", "Note", value=entry.note),
                FormField("tags", "Tags (comma-separated)", value=entry.tags),
                FormField("billable", "Billable", kind="toggle", value=entry.billable),
                FormField(
                    "project", "Project", kind="select", value=current_project, choices=options
                ),
            ],
        )

        async def _save(values: dict | None) -> None:
            if values is None:
                return
            kwargs: dict = {}
            if values["time"] != initial["time"]:
                kwargs["spec"] = values["time"]
            if values["note"] != initial["note"]:
                kwargs["note"] = values["note"]
            if values["tags"] != initial["tags"]:
                kwargs["tags"] = values["tags"]
            if values["billable"] != initial["billable"]:
                kwargs["billable"] = values["billable"]
            if values["project"] and values["project"] != initial["project"]:
                project_slug, client_slug = split_project_choice(values["project"])
                kwargs["project_slug"] = project_slug
                kwargs["client_slug"] = client_slug
            if not kwargs:
                return
            try:
                await entry_svc.edit_entry(
                    uid, now=datetime.now(), settings=get_settings(), **kwargs
                )
                self.notify("entry updated")
            except TtdError as exc:
                self.notify(str(exc), severity="error")
            await self.refresh_data()

        self.app.push_screen(form, _save)

    async def action_delete_entry(self) -> None:
        uid = self._selected_entry_id()
        if uid is None:
            return

        async def _confirmed(yes: bool | None) -> None:
            if not yes:
                return
            try:
                await entry_svc.delete_entry(uid)
                self.notify("entry deleted")
            except TtdError as exc:
                self.notify(str(exc), severity="error")
            await self.refresh_data()

        self.app.push_screen(ConfirmModal(f"Delete entry {uid[:8]}?"), _confirmed)
