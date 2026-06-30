"""Base screen with the left nav rail; subclasses fill the content area."""

import asyncio
import decimal
from datetime import date, datetime
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Label

from ttd.core.errors import TtdError
from ttd.services import timer as timer_svc
from ttd.tui._data import add_expense_entry, project_options, split_and_log
from ttd.tui.widgets.footer import AdaptiveFooter
from ttd.tui.widgets.forms import FormField, FormModal
from ttd.tui.widgets.modals import PickerModal, QuickLogModal

NAV = [
    ("dashboard", "1 dashboard"),
    ("timesheet", "2 timesheet"),
    ("clients", "3 clients"),
    ("reports", "4 reports"),
    ("invoices", "5 invoices"),
    ("taxes", "6 taxes"),
]

# The nav rail already names each screen next to its number, so the footer
# shows the nav keys as one compact group instead of six labelled items.
SCREEN_GROUP = Binding.Group("screen", compact=True)

PREV_NEXT_GROUP = Binding.Group("prev/next", compact=True)
"""Shared by screens that page through periods with [ and ]."""


def _validate_amount(raw: str) -> bool | str:
    """Return True if *raw* is a positive number; else an error string."""
    try:
        value = decimal.Decimal(raw)
    except decimal.InvalidOperation:
        return "amount must be a number"
    if value <= 0:
        return "amount must be positive"
    return True


def _validate_date(raw: str) -> bool | str:
    """Return True if *raw* is a valid ISO date (YYYY-MM-DD); else an error string.

    FormModal only calls validate on non-empty values, so blank → today is
    handled downstream without touching this validator.
    """
    try:
        date.fromisoformat(raw)
    except ValueError:
        return "date must be YYYY-MM-DD"
    return True


class TtdScreen(Screen):
    """Nav rail + content + footer; global timer/log actions."""

    nav_id = ""  # subclass sets

    BINDINGS: ClassVar = [
        Binding("1", "goto('dashboard')", "dashboard", group=SCREEN_GROUP),
        Binding("2", "goto('timesheet')", "timesheet", group=SCREEN_GROUP),
        Binding("3", "goto('clients')", "clients", group=SCREEN_GROUP),
        Binding("4", "goto('reports')", "reports", group=SCREEN_GROUP),
        Binding("5", "goto('invoices')", "invoices", group=SCREEN_GROUP),
        Binding("6", "goto('taxes')", "taxes", group=SCREEN_GROUP),
        Binding("s", "toggle_timer", "start/stop"),
        Binding("l", "quick_log", "log"),
        Binding("t", "pick_theme", "theme"),
        Binding("r", "refresh", "refresh"),
        Binding("q", "quit_app", "quit"),
    ]

    def compose(self) -> ComposeResult:
        with Horizontal(id="frame"):
            with Vertical(id="rail"):
                yield Label("ttd", id="brand")
                for nav_id, label in NAV:
                    classes = "nav-item active" if nav_id == self.nav_id else "nav-item"
                    yield Label(label, classes=classes, id=f"nav-{nav_id}")
            with Vertical(id="content"):
                yield from self.compose_content()
        yield AdaptiveFooter()

    def compose_content(self) -> ComposeResult:
        yield from ()

    async def refresh_data(self) -> None:
        """Re-query and re-render, serialized.

        Modal callbacks and on_screen_resume can both trigger refreshes; the
        lock keeps fetch+paint atomic so the last paint reflects the final
        database state instead of a stale pre-mutation fetch.
        """
        if not hasattr(self, "_refresh_lock"):
            self._refresh_lock = asyncio.Lock()
        async with self._refresh_lock:
            await self.render_data()

    async def render_data(self) -> None:
        """Subclasses re-query and re-render here."""

    async def on_screen_resume(self) -> None:
        await self.refresh_data()

    def setup(self) -> None:
        """One-time widget setup (columns, intervals) before the first refresh."""

    async def on_mount(self) -> None:
        self.setup()
        await self.refresh_data()

    def action_goto(self, screen: str) -> None:
        if screen != self.nav_id:
            self.app.switch_screen(screen)

    def action_quit_app(self) -> None:
        self.app.exit()

    async def action_refresh(self) -> None:
        await self.refresh_data()

    async def action_toggle_timer(self) -> None:
        now = datetime.now()
        status = await timer_svc.timer_status(now=now)
        if status.timer is not None:
            entry = await timer_svc.stop_timer(now=now)
            self.notify(
                f"logged {entry.seconds // 3600}:{entry.seconds % 3600 // 60:02d}",
                title="timer stopped",
            )
            await self.refresh_data()
            return
        options = await project_options()
        if not options:
            self.notify("no projects yet — add a client and project first", severity="warning")
            return

        async def _start(choice: str | None) -> None:
            if choice is None:
                return
            client_slug, project_slug = choice.split("/", 1)
            try:
                await timer_svc.start_timer(project_slug, client_slug, now=datetime.now())
                self.notify(f"tracking {choice}", title="timer started")
            except TtdError as exc:
                self.notify(str(exc), severity="error")
            await self.refresh_data()

        self.app.push_screen(PickerModal("start timer on…", options), _start)

    def action_pick_theme(self) -> None:
        search = getattr(self.app, "search_themes", None)
        if search is not None:
            search()

    async def action_quick_log(self) -> None:
        """Open a chooser: 'time' → existing log-time flow; 'expense' → expense form."""

        def _route(choice: str | None) -> None:
            if choice == "time":
                self.run_worker(self._open_time_log())
            elif choice == "expense":
                self.run_worker(self._open_expense_form())

        self.app.push_screen(
            PickerModal("log…", [("time", "⏱  time"), ("expense", "$  expense")]),
            _route,
        )

    async def _open_time_log(self) -> None:
        """Original quick-log body: pick a project and log a time entry."""
        options = await project_options()
        if not options:
            self.notify("no projects yet — add a client and project first", severity="warning")
            return

        async def _log(payload: dict | None) -> None:
            if payload is None:
                return
            try:
                entry = await split_and_log(payload, now=datetime.now())
                self.notify(
                    f"{entry.seconds // 3600}:{entry.seconds % 3600 // 60:02d} "
                    f"on {entry.work_date:%a %b %-d}",
                    title="logged",
                )
            except TtdError as exc:
                self.notify(str(exc), severity="error")
            await self.refresh_data()

        self.app.push_screen(QuickLogModal(options), _log)

    async def _open_expense_form(self) -> None:
        """Show a FormModal to log a billable expense."""
        options = await project_options()
        if not options:
            self.notify("no projects yet — add a client and project first", severity="warning")
            return

        fields = [
            FormField(
                "project",
                "project",
                kind="select",
                choices=options,
                value=options[0][0],
                required=True,
            ),
            FormField("description", "description", required=True, placeholder="Claude Code"),
            FormField(
                "amount",
                "amount",
                required=True,
                placeholder="100.00",
                validate=_validate_amount,
            ),
            FormField(
                "date",
                "date",
                placeholder="YYYY-MM-DD (blank = today)",
                validate=_validate_date,
            ),
        ]

        async def _save(payload: dict | None) -> None:
            if payload is None:
                return
            try:
                expense = await add_expense_entry(payload)
                self.notify(
                    f"{payload['description']}  ·  {expense.amount}",
                    title="expense added",
                )
            except TtdError as exc:
                self.notify(str(exc), severity="error")
            except Exception as exc:
                self.notify(str(exc), severity="error")
            await self.refresh_data()

        self.app.push_screen(FormModal("log expense", fields), _save)
