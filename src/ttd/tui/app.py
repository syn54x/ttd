"""The ttd TUI: launched by bare `ttd`."""

from typing import ClassVar

from textual.app import App

from ttd.config.loader import get_settings
from ttd.storage.db import close_db, init_db
from ttd.tui.screens.clients import ClientsScreen
from ttd.tui.screens.dashboard import DashboardScreen
from ttd.tui.screens.invoices import InvoicesScreen
from ttd.tui.screens.reports import ReportsScreen
from ttd.tui.screens.taxes import TaxesScreen
from ttd.tui.screens.timesheet import TimesheetScreen
from ttd.tui.theme import TTD_DARK, TTD_LIGHT


class TtdApp(App):
    TITLE = "ttd"
    CSS_PATH = "ttd.tcss"

    SCREENS: ClassVar = {
        "dashboard": DashboardScreen,
        "timesheet": TimesheetScreen,
        "clients": ClientsScreen,
        "reports": ReportsScreen,
        "invoices": InvoicesScreen,
        "taxes": TaxesScreen,
    }

    async def on_mount(self) -> None:
        self.register_theme(TTD_DARK)
        self.register_theme(TTD_LIGHT)
        configured = get_settings().display.theme
        self.theme = configured if configured in ("ttd-dark", "ttd-light") else "ttd-dark"
        await init_db()
        await self.push_screen("dashboard")

    async def on_unmount(self) -> None:
        await close_db()


def run_tui() -> None:
    TtdApp().run()
