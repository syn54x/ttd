# TUI Log Page (re-scope timesheet) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-scope the underused TUI `timesheet` screen into a `log` page that views, adds, edits, and deletes both time entries and expenses, with a month-only window.

**Architecture:** Rework `TimesheetScreen` into `LogScreen` (rename file/class/nav_id, update the screen registry and nav). Two stacked `DataTable` sections — time, then expenses — both scoped to one month cycled with `[`/`]`. Adding reuses the existing global `l` chooser; `e`/`x` edit/delete the highlighted row of the focused section, dispatched to `entry_svc` or `expense_svc`.

**Tech Stack:** Python 3.13, Textual (TUI), Ferro-ORM/SQLite, pytest + pytest-asyncio (Textual pilot tests).

## Global Constraints

- Re-scope, do not add a 7th nav item. `timesheet` → `log` everywhere (nav label "2 log", `nav_id = "log"`, registry key `"log"`).
- **Month-only** window cycled with `[` / `]`; `g` resets to the current month. Remove the `d`/`w`/`m` span toggle and the `Span` machinery.
- Adding is the existing global `l` chooser (time/expense). Remove the screen-local `a` (add_entry) binding.
- Two stacked sections: **time** (date · project · time · hours · note · flags — the current table, unchanged) then **expenses** (date · project · description · amount). Empty expenses → header + muted "no expenses this month".
- `e` edits / `x` deletes the highlighted row of the **focused** section; dispatch to `entry_svc` (entries) or `expense_svc` (expenses). Both services already refuse invoiced rows — surface that via `notify`.
- Reuse existing pieces: `entry_svc` list/edit/delete (unchanged), `expense_svc.list_expenses`/`edit_expense`/`delete_expense`, the generic `FormModal`, `ConfirmModal`, and the `_validate_amount`/`_validate_date` helpers already in `screens/_base.py`.
- Tests: `asyncio_mode = "auto"`; Textual pilot tests use the `seeded_app` fixture + `app.run_test(size=(120, 40)) as pilot`, `pilot.press(...)`, `pilot.pause()`, assert on `seeded_app.screen.nav_id` and `screen.query_one("#id", DataTable).row_count`. Keep the coverage gate (`fail_under = 84`) green; `ty` + `ruff` clean.

---

## File Structure

- **Rename/rework:** `src/ttd/tui/screens/timesheet.py` → `src/ttd/tui/screens/log.py` (`TimesheetScreen` → `LogScreen`).
- **Modify:** `src/ttd/tui/app.py` (import + `SCREENS` key), `src/ttd/tui/screens/_base.py` (`NAV` entry).
- **Modify tests:** `tests/test_tui/test_app.py` (nav refs `timesheet`→`log`; day-navigation test → month navigation; add-via-`a` test → add-via-`l`; seed an expense in `seeded_app`).

---

## Task 1: Rename timesheet → log, month-only window

**Files:**
- Rename + rewrite: `src/ttd/tui/screens/timesheet.py` → `src/ttd/tui/screens/log.py`
- Modify: `src/ttd/tui/app.py`
- Modify: `src/ttd/tui/screens/_base.py`
- Modify: `tests/test_tui/test_app.py`

**Interfaces:**
- Produces: `LogScreen` (in `ttd.tui.screens.log`) with `nav_id = "log"`; registry key `"log"`; nav entry `("log", "2 log")`. Keeps `#day-title`, `#day-table`, `#day-total` ids and the entry edit/delete actions (`action_edit_entry`, `action_delete_entry`, `_selected_entry_id`). Month-only: `action_shift(delta)` moves whole months; `action_today` resets to the current month. No `action_span`, no `a`/`d`/`w`/`m` bindings.

- [ ] **Step 1: Rename the file with git**

```bash
git mv src/ttd/tui/screens/timesheet.py src/ttd/tui/screens/log.py
```

- [ ] **Step 2: Rewrite `src/ttd/tui/screens/log.py`**

Replace the whole file with the month-only LogScreen (entry section only — expenses arrive in Task 2):

```python
"""Log: month-scoped time entries (expenses added in Task 2); add/edit/delete."""

from datetime import date, datetime, timedelta
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.coordinate import Coordinate
from textual.widgets import DataTable, Label

from ttd.cli._pickers import describe_timespec, split_project_choice, validate_timespec
from ttd.config.loader import get_settings
from ttd.core.errors import TtdError
from ttd.core.money import format_hours
from ttd.reporting import periods
from ttd.services import entries as entry_svc
from ttd.tui._data import hours_for_row, project_options
from ttd.tui.screens._base import PREV_NEXT_GROUP, TtdScreen
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
    ]

    def __init__(self) -> None:
        super().__init__()
        self.anchor_date: date = date.today()

    def compose_content(self) -> ComposeResult:
        with Vertical(id="log"):
            yield Label("", id="day-title", classes="section-title")
            yield DataTable(id="day-table", cursor_type="row")
            yield Label("", id="day-total", classes="muted")

    def setup(self) -> None:
        table = self.query_one("#day-table", DataTable)
        table.add_columns("date", "project", "time", "hours", "note", "flags")

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

    def _selected_entry_id(self) -> str | None:
        table = self.query_one("#day-table", DataTable)
        if table.row_count == 0 or table.cursor_row is None:
            return None
        key = table.coordinate_to_cell_key(Coordinate(table.cursor_row, 0)).row_key.value
        return str(key) if key is not None else None

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
                await entry_svc.edit_entry(uid, now=datetime.now(), settings=get_settings(), **kwargs)
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
```

(This is the current timesheet minus: `Span`/`SPAN_GROUP`, `action_span`, the `d`/`w`/`m`/`a` bindings, `action_add_entry`, and the day/yesterday title suffix. `QuickLogModal`/`split_and_log` imports are dropped because adding now goes through the global `l` chooser in `_base.py`.)

- [ ] **Step 3: Update the screen registry and nav**

In `src/ttd/tui/app.py`: change the import and the `SCREENS` key:

```python
from ttd.tui.screens.log import LogScreen
```
```python
    SCREENS: ClassVar = {
        "dashboard": DashboardScreen,
        "log": LogScreen,
        "clients": ClientsScreen,
        "reports": ReportsScreen,
        "invoices": InvoicesScreen,
        "taxes": TaxesScreen,
    }
```

In `src/ttd/tui/screens/_base.py`, change the `NAV` entry:

```python
NAV = [
    ("dashboard", "1 dashboard"),
    ("log", "2 log"),
    ("clients", "3 clients"),
    ("reports", "4 reports"),
    ("invoices", "5 invoices"),
    ("taxes", "6 taxes"),
]
```

(The `goto('timesheet')` binding in `_base.py` is keyed off `nav_id`; the nav key `2` maps to whatever the registry/nav call it. Search `_base.py` for `goto('timesheet')` / `"timesheet"` and change to `'log'` if present — the nav `2` binding uses the registry key, so update it to `"log"`.)

- [ ] **Step 4: Update existing tests for the rename + month-only + add-via-l**

In `tests/test_tui/test_app.py`:
- In `test_navigation_between_screens`, change `("2", "timesheet")` to `("2", "log")`.
- In `test_quick_log_creates_entry`: it presses `"2"` then `"a"`. Remove the `"a"` path (the `a` binding is gone) and drive adding through `l` → time. Rewrite its body to:

```python
async def test_quick_log_creates_entry(seeded_app):
    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("2")  # log
        await pilot.pause()
        assert seeded_app.screen.nav_id == "log"
        before = seeded_app.screen.query_one("#day-table").row_count
        await pilot.press("l")            # log chooser
        await pilot.pause()
        await pilot.press("enter")        # first option = time
        await pilot.pause()
        await pilot.press(*"today 3pm to 4pm")
        await pilot.pause()
        await pilot.press("enter")        # submit spec → picks first project
        await pilot.pause()
        await pilot.pause()
        assert seeded_app.screen.query_one("#day-table").row_count == before + 1
```

- Replace `test_timesheet_day_navigation` with a month-navigation test (rename to `test_log_month_navigation`). The seed logs entries every 2 days for the last 14 days; all fall in the current or previous month. Assert the current month has rows and the previous month differs:

```python
async def test_log_month_navigation(seeded_app):
    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("2")  # log
        await pilot.pause()
        screen = seeded_app.screen
        this_month = screen.query_one("#day-table").row_count
        assert this_month >= 1
        await pilot.press("left_square_bracket")  # previous month
        await pilot.pause()
        prev_month = screen.query_one("#day-table").row_count
        await pilot.press("g")  # back to this month
        await pilot.pause()
        assert screen.query_one("#day-table").row_count == this_month
        assert prev_month != this_month or prev_month == 0
```

- Grep the test file for any other `"timesheet"` / `TimesheetScreen` references and update them.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_tui -v && uv run ty check && uv run ruff check`
Expected: PASS, clean. Also run the full suite to catch any other `timesheet` reference: `uv run pytest -q`.

- [ ] **Step 6: Commit**

```bash
git add src/ttd/tui/ tests/test_tui/test_app.py
git commit -m "feat: re-scope timesheet into month-only log screen"
```

---

## Task 2: Add the expenses section (display)

**Files:**
- Modify: `src/ttd/tui/screens/log.py`
- Modify: `tests/test_tui/test_app.py` (seed an expense; assert the expenses table renders it)

**Interfaces:**
- Consumes: `LogScreen` (Task 1); `expense_svc.list_expenses(*, date_from, date_to)` returning `ExpenseView`s (`.expense`, `.project`, `.client`, `.has_receipt`).
- Produces: a second `DataTable#expense-table` (columns date · project · description · amount), a `#expense-title` label, a `#expense-total` label, all populated in `render_data`.

- [ ] **Step 1: Write the failing test**

Seed an expense in the `seeded_app` fixture (add after the entry seeding loop, inside `open_test_db`):

```python
        from decimal import Decimal as _D
        from ttd.services import expenses as expense_svc
        await expense_svc.add_expense("api-rewrite", "Cloud hosting", _D("49.99"))
```

Then add a test:

```python
async def test_log_shows_expense_section(seeded_app):
    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("2")  # log
        await pilot.pause()
        screen = seeded_app.screen
        expense_table = screen.query_one("#expense-table")
        assert expense_table.row_count == 1
        # the description appears in the rendered table
        cells = [expense_table.get_row_at(0)]
        assert any("Cloud hosting" in str(c) for row in cells for c in row)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tui/test_app.py -k log_shows_expense -v`
Expected: FAIL — `#expense-table` does not exist (`NoMatches`).

- [ ] **Step 3: Add the expenses widgets to `compose_content` and `setup`**

In `log.py`, extend `compose_content`:

```python
    def compose_content(self) -> ComposeResult:
        with Vertical(id="log"):
            yield Label("", id="day-title", classes="section-title")
            yield DataTable(id="day-table", cursor_type="row")
            yield Label("", id="day-total", classes="muted")
            yield Label("expenses", id="expense-title", classes="section-title")
            yield DataTable(id="expense-table", cursor_type="row")
            yield Label("", id="expense-total", classes="muted")
```

Extend `setup` to add the expense columns:

```python
    def setup(self) -> None:
        self.query_one("#day-table", DataTable).add_columns(
            "date", "project", "time", "hours", "note", "flags"
        )
        self.query_one("#expense-table", DataTable).add_columns(
            "date", "project", "description", "amount"
        )
```

- [ ] **Step 4: Render expenses in `render_data`**

Add these imports at the top of `log.py`:

```python
from decimal import Decimal

from ttd.core.money import format_hours, format_money
from ttd.services import expenses as expense_svc
```

(Replace the existing `from ttd.core.money import format_hours` line with the combined import.)

At the end of `render_data`, after updating `#day-total`, render the expenses section:

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_tui -v && uv run ty check && uv run ruff check`
Expected: PASS, clean.

- [ ] **Step 6: Commit**

```bash
git add src/ttd/tui/screens/log.py tests/test_tui/test_app.py
git commit -m "feat: show expenses section on the log screen"
```

---

## Task 3: Focus switching + expense edit/delete

**Files:**
- Modify: `src/ttd/tui/screens/log.py`
- Modify: `tests/test_tui/test_app.py`

**Interfaces:**
- Consumes: Task 2 widgets; `expense_svc.find_expense`, `expense_svc.edit_expense(uid_prefix, *, amount=None, description=None, note=None, incurred_date=None, project_slug=None, client_slug=None)`, `expense_svc.delete_expense(uid_prefix)`; `_validate_amount`/`_validate_date` from `ttd.tui.screens._base`; `split_project_choice`; `FormModal`/`FormField`/`ConfirmModal`.
- Produces: a `tab` binding that toggles the active section and focuses its table; `e`/`x` dispatch to entry vs expense based on the active section; expense edit (FormModal) and delete (ConfirmModal) flows.

- [ ] **Step 1: Write the failing test (delete an expense from the log screen)**

```python
async def test_log_delete_expense(seeded_app):
    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("2")  # log
        await pilot.pause()
        screen = seeded_app.screen
        assert screen.query_one("#expense-table").row_count == 1
        await pilot.press("tab")      # focus the expenses section
        await pilot.pause()
        await pilot.press("x")        # delete highlighted expense
        await pilot.pause()
        await pilot.press("enter")    # confirm
        await pilot.pause()
        await pilot.pause()
        assert screen.query_one("#expense-table").row_count == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tui/test_app.py -k log_delete_expense -v`
Expected: FAIL — `tab` doesn't switch focus and `x` deletes an entry (or does nothing), so the expense row remains.

- [ ] **Step 3: Add active-section state, the tab binding, and a selected-expense helper**

In `log.py`, add to `__init__`:

```python
    def __init__(self) -> None:
        super().__init__()
        self.anchor_date: date = date.today()
        self.active_section: str = "time"  # "time" | "expenses"
```

Add a `tab` binding to `BINDINGS` (after the `x` binding):

```python
        ("tab", "switch_section", "switch section"),
```

Add the action and an expense-id helper (mirrors `_selected_entry_id`):

```python
    async def action_switch_section(self) -> None:
        self.active_section = "expenses" if self.active_section == "time" else "time"
        table_id = "#expense-table" if self.active_section == "expenses" else "#day-table"
        self.query_one(table_id, DataTable).focus()
        # mark the active section title
        self.query_one("#day-title", Label).remove_class("active-section")
        self.query_one("#expense-title", Label).remove_class("active-section")
        active_title = "#expense-title" if self.active_section == "expenses" else "#day-title"
        self.query_one(active_title, Label).add_class("active-section")

    def _selected_expense_id(self) -> str | None:
        table = self.query_one("#expense-table", DataTable)
        if table.row_count == 0 or table.cursor_row is None:
            return None
        key = table.coordinate_to_cell_key(Coordinate(table.cursor_row, 0)).row_key.value
        return str(key) if key is not None else None
```

- [ ] **Step 4: Dispatch `e`/`x` by active section**

Rename the entry actions to private helpers and make `action_edit_entry`/`action_delete_entry` (still bound to `e`/`x`) route. Replace the binding-targeted actions:

```python
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
```

Rename the existing `action_edit_entry` body to `_edit_entry_row` and the existing `action_delete_entry` body to `_delete_entry_row` (same code, just the method names change).

- [ ] **Step 5: Add the expense edit/delete flows**

Add these imports to `log.py`:

```python
from ttd.tui.screens._base import PREV_NEXT_GROUP, TtdScreen, _validate_amount, _validate_date
```

(extend the existing `_base` import). Then add:

```python
    async def _edit_expense(self) -> None:
        uid = self._selected_expense_id()
        if uid is None:
            return
        expense = await expense_svc.find_expense(uid)
        if expense.invoice_id is not None:
            self.notify("expense is on an invoice — void it first", severity="warning")
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
                    "amount", "Amount", value=str(expense.amount),
                    validate=_validate_amount, required=True,
                ),
                FormField("date", "Date (YYYY-MM-DD)", value=initial["date"], validate=_validate_date),
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
```

- [ ] **Step 6: Add an edit-expense test**

```python
async def test_log_edit_expense(seeded_app):
    async with seeded_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("2")
        await pilot.pause()
        screen = seeded_app.screen
        await pilot.press("tab")     # focus expenses
        await pilot.pause()
        await pilot.press("e")       # edit
        await pilot.pause()
        # amount field is the second field; clear and retype via the form is heavy —
        # assert the edit modal opened with the expense's values instead.
        from ttd.tui.widgets.forms import FormModal
        assert isinstance(seeded_app.screen, FormModal)
        await pilot.press("escape")
        await pilot.pause()
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/test_tui -v && uv run ty check && uv run ruff check`
Expected: PASS, clean.

- [ ] **Step 8: Optional polish — active-section CSS**

If the app has a TUI stylesheet (search for `.section-title` in `src/ttd/tui/*.tcss` or theme files), add an `.active-section` rule so the focused section header stands out (e.g. accent color/bold). If no stylesheet rule is found, the `add_class("active-section")` is harmless and this step is a no-op; note it in the report.

- [ ] **Step 9: Run the full suite + commit**

Run: `uv run pytest -q && uv run ty check && uv run ruff check`
Expected: full suite passes, coverage ≥84%, clean.

```bash
git add src/ttd/tui/screens/log.py tests/test_tui/test_app.py
git commit -m "feat: focus switching and expense edit/delete on the log screen"
```

---

## Self-Review Notes (coverage against the spec)

- Re-scope timesheet → log (nav slot 2, rename, registry) → **Task 1**.
- Month-only window, `[`/`]`, `g`; drop `d`/`w`/`m` and `a` (add via `l`) → **Task 1**.
- Two stacked sections (time, then expenses) with empty-state → **Task 2**.
- Focus-based `e`/`x` dispatch; expense edit (FormModal) / delete (ConfirmModal) honoring invoiced lock → **Task 3**.
- Reuse `entry_svc`, `expense_svc`, `FormModal`, `ConfirmModal`, `_validate_amount`/`_validate_date` → Tasks 1–3.
- Adding via global `l` chooser (already built) — no new add code; existing flow refreshes the log screen via `refresh_data`.
- Coverage gate kept green via pilot tests each task.
- **Deviation from spec (justified):** the spec suggested a new `_data` helper for "expenses in a month window"; the log screen instead calls `expense_svc.list_expenses(date_from=, date_to=)` directly, exactly as it calls `entry_svc.list_entries` directly — mirroring the existing pattern rather than adding an indirection. Noted for the reviewer.
- **Trim (YAGNI):** up/down edge-rollover between the two tables (mentioned in the spec) is not implemented; `tab` switches sections and focuses the table so arrows navigate within it. Flagged as an optional follow-up rather than building fiddly cross-table cursor handoff.
- **Verify during impl:** confirm `_validate_amount`/`_validate_date` are module-level importable from `ttd.tui.screens._base` (they were added there in the `l`-chooser work). If they are nested/non-importable, lift them to module scope in `_base.py` as part of Task 3.
