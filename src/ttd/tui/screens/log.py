"""Log: month-scoped time entries (expenses added in Task 2); add/edit/delete."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.coordinate import Coordinate
from textual.widgets import DataTable, Label

from ttd.cli._pickers import describe_timespec, split_project_choice, validate_timespec
from ttd.config.loader import get_settings
from ttd.core.errors import TtdError
from ttd.core.money import format_hours, format_money
from ttd.reporting import periods
from ttd.services import entries as entry_svc
from ttd.services import expenses as expense_svc
from ttd.tui._data import hours_for_row, project_options
from ttd.tui.screens._base import PREV_NEXT_GROUP, TtdScreen, _validate_amount, _validate_date
from ttd.tui.widgets.forms import FormField, FormModal
from ttd.tui.widgets.modals import ConfirmModal


def _entry_spec(entry) -> str:
    """Reconstruct an unambiguous, round-trippable time spec for an entry."""
    if entry.started_at and entry.ended_at:
        return f"{entry.work_date} {entry.started_at:%H:%M} to {entry.ended_at:%H:%M}"
    h, rem = divmod(entry.seconds, 3600)
    duration = f"{h}h{rem // 60}m" if h else f"{rem // 60}m"
    return f"{entry.work_date} {duration}"


class LogScreen(TtdScreen):
    nav_id = "log"

    BINDINGS: ClassVar = [
        *TtdScreen.BINDINGS,
        Binding("left_square_bracket", "shift(-1)", "prev", group=PREV_NEXT_GROUP),
        Binding("right_square_bracket", "shift(1)", "next", group=PREV_NEXT_GROUP),
        ("g", "today", "this month"),
        ("e", "edit_entry", "edit"),
        ("x", "delete_entry", "delete"),
        ("tab", "switch_section", "switch section"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.anchor_date: date = date.today()
        self.active_section: str = "time"  # "time" | "expenses"

    def compose_content(self) -> ComposeResult:
        with Vertical(id="log"):
            yield Label("", id="day-title", classes="section-title")
            yield DataTable(id="day-table", cursor_type="row")
            yield Label("", id="day-total", classes="muted")
            yield Label("expenses", id="expense-title", classes="section-title")
            yield DataTable(id="expense-table", cursor_type="row")
            yield Label("", id="expense-total", classes="muted")

    def setup(self) -> None:
        self.query_one("#day-table", DataTable).add_columns(
            "date", "project", "time", "hours", "note", "flags"
        )
        self.query_one("#expense-table", DataTable).add_columns(
            "date", "project", "description", "amount"
        )

    def _period(self) -> periods.Period:
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
        self.query_one("#day-title", Label).update(period.label)
        self.query_one("#day-total", Label).update(
            f"{len(rows)} entr{'y' if len(rows) == 1 else 'ies'} · {format_hours(total)}"
            "   [dim]\\[ ] prev/next month · g this month · l add · e edit · x delete[/dim]"
        )
        expenses = await expense_svc.list_expenses(date_from=period.start, date_to=period.end)
        etable = self.query_one("#expense-table", DataTable)
        etable.clear()
        etotal = Decimal("0")
        for v in expenses:
            etotal += v.expense.amount
            flags = " inv" if v.expense.invoice_id is not None else ""
            etable.add_row(
                v.expense.incurred_date.strftime("%a %b %-d"),
                f"{v.client.slug}/{v.project.slug}",
                v.expense.description + flags,
                format_money(v.expense.amount, v.client.currency),
                key=str(v.expense.id),
            )
        if expenses:
            self.query_one("#expense-total", Label).update(
                f"{len(expenses)} expense{'s' if len(expenses) != 1 else ''} · "
                f"{format_money(etotal, expenses[0].client.currency)}"
            )
        else:
            self.query_one("#expense-total", Label).update("[dim]no expenses this month[/dim]")

    async def action_shift(self, delta: int) -> None:
        first = self.anchor_date.replace(day=1)
        if delta > 0:
            self.anchor_date = (first + timedelta(days=32)).replace(day=1)
        else:
            self.anchor_date = (first - timedelta(days=1)).replace(day=1)
        await self.refresh_data()

    async def action_today(self) -> None:
        self.anchor_date = date.today()
        await self.refresh_data()

    async def action_switch_section(self) -> None:
        self.active_section = "expenses" if self.active_section == "time" else "time"
        table_id = "#expense-table" if self.active_section == "expenses" else "#day-table"
        self.query_one(table_id, DataTable).focus()
        # mark the active section title
        self.query_one("#day-title", Label).remove_class("active-section")
        self.query_one("#expense-title", Label).remove_class("active-section")
        active_title = "#expense-title" if self.active_section == "expenses" else "#day-title"
        self.query_one(active_title, Label).add_class("active-section")

    def _selected_entry_id(self) -> str | None:
        table = self.query_one("#day-table", DataTable)
        if table.row_count == 0 or table.cursor_row is None:
            return None
        key = table.coordinate_to_cell_key(Coordinate(table.cursor_row, 0)).row_key.value
        return str(key) if key is not None else None

    def _selected_expense_id(self) -> str | None:
        table = self.query_one("#expense-table", DataTable)
        if table.row_count == 0 or table.cursor_row is None:
            return None
        key = table.coordinate_to_cell_key(Coordinate(table.cursor_row, 0)).row_key.value
        return str(key) if key is not None else None

    async def action_edit_entry(self) -> None:
        if self.active_section == "expenses":
            await self._edit_expense()
        else:
            await self._edit_entry_row()

    async def action_delete_entry(self) -> None:
        if self.active_section == "expenses":
            await self._delete_expense()
        else:
            await self._delete_entry_row()

    async def _edit_entry_row(self) -> None:
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

    async def _delete_entry_row(self) -> None:
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

    async def _edit_expense(self) -> None:
        uid = self._selected_expense_id()
        if uid is None:
            return
        expense = await expense_svc.find_expense(uid)
        if expense.invoice_id is not None:
            self.notify("expense is on an invoice -- void it first", severity="warning")
            return
        options = await project_options()
        views = await expense_svc.list_expenses(
            date_from=expense.incurred_date, date_to=expense.incurred_date
        )
        current = next((v for v in views if v.expense.id == expense.id), None)
        current_project = f"{current.client.slug}/{current.project.slug}" if current else None
        initial = {
            "description": expense.description,
            "amount": str(expense.amount),
            "date": expense.incurred_date.isoformat(),
            "note": expense.note,
            "project": current_project,
        }
        form = FormModal(
            f"edit expense {uid[:8]}",
            [
                FormField("description", "Description", value=expense.description, required=True),
                FormField(
                    "amount",
                    "Amount",
                    value=str(expense.amount),
                    validate=_validate_amount,
                    required=True,
                ),
                FormField(
                    "date", "Date (YYYY-MM-DD)", value=initial["date"], validate=_validate_date
                ),
                FormField("note", "Note", value=expense.note),
                FormField(
                    "project", "Project", kind="select", value=current_project, choices=options
                ),
            ],
        )

        async def _save(values: dict | None) -> None:
            if values is None:
                return
            kwargs: dict = {}
            if values["description"] != initial["description"]:
                kwargs["description"] = values["description"]
            if values["amount"] != initial["amount"]:
                kwargs["amount"] = Decimal(values["amount"])
            if values["date"] != initial["date"] and values["date"]:
                kwargs["incurred_date"] = date.fromisoformat(values["date"])
            if values["note"] != initial["note"]:
                kwargs["note"] = values["note"]
            if values["project"] and values["project"] != initial["project"]:
                project_slug, client_slug = split_project_choice(values["project"])
                kwargs["project_slug"] = project_slug
                kwargs["client_slug"] = client_slug
            if not kwargs:
                return
            try:
                await expense_svc.edit_expense(uid, **kwargs)
                self.notify("expense updated")
            except TtdError as exc:
                self.notify(str(exc), severity="error")
            await self.refresh_data()

        self.app.push_screen(form, _save)

    async def _delete_expense(self) -> None:
        uid = self._selected_expense_id()
        if uid is None:
            return

        async def _confirmed(yes: bool | None) -> None:
            if not yes:
                return
            try:
                await expense_svc.delete_expense(uid)
                self.notify("expense deleted")
            except TtdError as exc:
                self.notify(str(exc), severity="error")
            await self.refresh_data()

        self.app.push_screen(ConfirmModal(f"Delete expense {uid[:8]}?"), _confirmed)
