"""The ttd TUI: launched by bare `ttd`."""

from contextlib import AsyncExitStack
from typing import ClassVar

from ferro import engines
from textual.app import App

from ttd.config import writer
from ttd.config.loader import get_settings
from ttd.core.errors import ConfigError
from ttd.storage.db import close_db, init_db
from ttd.tui.screens._base import TtdScreen
from ttd.tui.screens.clients import ClientsScreen
from ttd.tui.screens.dashboard import DashboardScreen
from ttd.tui.screens.invoices import InvoicesScreen
from ttd.tui.screens.log import LogScreen
from ttd.tui.screens.reports import ReportsScreen
from ttd.tui.screens.taxes import TaxesScreen
from ttd.tui.theme import THEME_DARK, TTD_DARK, TTD_LIGHT
from ttd.tui.widgets.modals import ConfirmModal
from ttd.tui.widgets.theme_picker import ThemePickerModal


class TtdApp(App):
    TITLE = "ttd"
    CSS_PATH = "ttd.tcss"

    SCREENS: ClassVar = {
        "dashboard": DashboardScreen,
        "log": LogScreen,
        "clients": ClientsScreen,
        "reports": ReportsScreen,
        "invoices": InvoicesScreen,
        "taxes": TaxesScreen,
    }

    _db_stack: AsyncExitStack | None = None

    async def on_mount(self) -> None:
        self.register_theme(TTD_DARK)
        self.register_theme(TTD_LIGHT)
        configured = get_settings().display.theme
        self.theme = configured if configured in self.available_themes else THEME_DARK
        await init_db()
        self._db_stack = AsyncExitStack()
        await self._db_stack.__aenter__()
        await self._db_stack.enter_async_context(engines.session())
        await self.push_screen("dashboard")

    def search_themes(self) -> None:
        """Command palette → Theme: two-column picker with live preview."""
        calling = self.screen if isinstance(self.screen, TtdScreen) else None

        async def _picked(selected: str | None) -> None:
            if selected is None:
                if isinstance(calling, TtdScreen):
                    await calling.refresh_data()
                return

            async def _save(save: bool | None) -> None:
                if save:
                    try:
                        path = writer.set_value("display.theme", selected, local=False)
                    except ConfigError as exc:
                        self.notify(str(exc), severity="error")
                    else:
                        self.notify(f"saved to {path}", title=f"theme: {selected}")
                else:
                    self.notify("theme changed for this session", title=selected)
                if isinstance(calling, TtdScreen):
                    await calling.refresh_data()

            self.push_screen(
                ConfirmModal(f"Save {selected} as your default theme?"),
                _save,
            )

        self.push_screen(ThemePickerModal(), _picked)

    async def on_unmount(self) -> None:
        if self._db_stack is not None:
            await self._db_stack.__aexit__(None, None, None)
            self._db_stack = None
        await close_db()


def run_tui() -> None:
    TtdApp().run()
