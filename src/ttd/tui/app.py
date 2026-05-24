from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Static


class TtdApp(App[None]):
    TITLE = "TTD"
    SUB_TITLE = "Bill from the terminal"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("TTD ledger scaffold — billing features coming soon.")
        yield Footer()


def main() -> None:
    TtdApp().run()
