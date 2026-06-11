"""Base screen with the left nav rail; subclasses fill the content area."""

import asyncio
from datetime import datetime
from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Label

from ttd.core.errors import TtdError
from ttd.services import timer as timer_svc
from ttd.tui._data import project_options, split_and_log
from ttd.tui.widgets.modals import PickerModal, QuickLogModal

NAV = [
    ("dashboard", "1 dashboard"),
    ("timesheet", "2 timesheet"),
    ("clients", "3 clients"),
    ("reports", "4 reports"),
    ("invoices", "5 invoices"),
]


class TtdScreen(Screen):
    """Nav rail + content + footer; global timer/log actions."""

    nav_id = ""  # subclass sets

    BINDINGS: ClassVar = [
        ("1", "goto('dashboard')", "dashboard"),
        ("2", "goto('timesheet')", "timesheet"),
        ("3", "goto('clients')", "clients"),
        ("4", "goto('reports')", "reports"),
        ("5", "goto('invoices')", "invoices"),
        ("s", "toggle_timer", "start/stop"),
        ("l", "quick_log", "log"),
        ("r", "refresh", "refresh"),
        ("q", "quit_app", "quit"),
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
        yield Footer()

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

    async def action_quick_log(self) -> None:
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
