"""Taxes: IRS-quarter set-aside dashboard and estimated-tax payments."""

from datetime import date
from decimal import Decimal
from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Label

from ttd.config.loader import get_settings
from ttd.core.errors import TtdError
from ttd.core.money import format_money, parse_money
from ttd.core.taxes import TaxQuarter, format_rate
from ttd.services import taxes as svc
from ttd.tui.screens._base import TtdScreen

YEAR_GROUP = Binding.Group("year", compact=True)


class TaxPaymentModal(ModalScreen[dict | None]):
    """Record an estimated-tax payment for an IRS quarter."""

    BINDINGS: ClassVar = [("escape", "dismiss(None)", "Cancel")]

    def compose(self) -> ComposeResult:
        today = date.today()
        with Vertical(classes="modal-box"):
            yield Label("record IRS payment", classes="modal-title")
            yield Input(value=TaxQuarter.from_date(today).label, placeholder="2026Q2", id="quarter")
            yield Input(placeholder="amount", id="amount")
            yield Input(value=today.isoformat(), placeholder="YYYY-MM-DD", id="date")
            yield Input(placeholder="note (optional)", id="note")
            with Horizontal(classes="modal-buttons"):
                yield Button("Record", variant="primary", id="submit")
                yield Button("Cancel", id="cancel")

    @on(Input.Submitted)
    def _input_submitted(self) -> None:
        self._submit()

    @on(Button.Pressed, "#submit")
    def _button_submit(self) -> None:
        self._submit()

    @on(Button.Pressed, "#cancel")
    def _button_cancel(self) -> None:
        self.dismiss(None)

    def _submit(self) -> None:
        amount = self.query_one("#amount", Input).value.strip()
        if not amount:
            return
        self.dismiss(
            {
                "quarter": self.query_one("#quarter", Input).value.strip(),
                "amount": amount,
                "date": self.query_one("#date", Input).value.strip(),
                "note": self.query_one("#note", Input).value.strip(),
            }
        )


class TaxesScreen(TtdScreen):
    nav_id = "taxes"

    BINDINGS: ClassVar = [
        *TtdScreen.BINDINGS,
        Binding("left_square_bracket", "shift_year(-1)", "prev year", group=YEAR_GROUP),
        Binding("right_square_bracket", "shift_year(1)", "next year", group=YEAR_GROUP),
        ("p", "record_payment", "record payment"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.year = date.today().year

    def compose_content(self) -> ComposeResult:
        with Vertical(id="taxes"):
            yield Label("", id="tax-title", classes="section-title")
            yield DataTable(id="tax-table", cursor_type="row")
            yield Label("", id="tax-help", classes="muted")

    def setup(self) -> None:
        table = self.query_one("#tax-table", DataTable)
        table.add_columns("quarter", "window", "due", "income", "set aside", "remitted", "balance")

    async def render_data(self) -> None:
        settings = get_settings()
        currency = settings.business.currency
        summaries = await svc.year_summary(self.year, settings)

        table = self.query_one("#tax-table", DataTable)
        table.clear()
        for s in summaries:
            q = s.quarter
            balance_style = "green" if s.balance <= 0 else "yellow"
            table.add_row(
                q.label,
                f"{q.start:%b %-d} – {q.end:%b %-d}",
                f"{q.due_date:%b %-d %Y}",
                format_money(s.income, currency),
                format_money(s.set_aside, currency),
                format_money(s.remitted, currency),
                f"[{balance_style}]{format_money(s.balance, currency)}[/]",
                key=q.label,
            )

        self.query_one("#tax-title", Label).update(f"taxes · {self.year}")
        set_aside = sum((s.set_aside for s in summaries), Decimal("0"))
        remitted = sum((s.remitted for s in summaries), Decimal("0"))
        rate = settings.tax.set_aside_rate
        if rate == 0 and all(s.invoice_count == 0 for s in summaries):
            totals = "set a rate first: ttd config set tax.set_aside_rate 0.32"
        else:
            totals = (
                f"rate {format_rate(rate)} · set aside {format_money(set_aside, currency)} · "
                f"remitted {format_money(remitted, currency)}"
            )
        self.query_one("#tax-help", Label).update(
            f"{totals}   [dim]p record payment · \\[ ] year[/dim]"
        )

    async def action_shift_year(self, delta: int) -> None:
        self.year += delta
        await self.refresh_data()

    async def action_record_payment(self) -> None:
        async def _record(payload: dict | None) -> None:
            if payload is None:
                return
            try:
                quarter = TaxQuarter.parse(payload["quarter"], date.today())
                paid_on = date.fromisoformat(payload["date"]) if payload["date"] else None
                payment = await svc.record_payment(
                    quarter,
                    parse_money(payload["amount"]),
                    paid_on=paid_on,
                    note=payload["note"],
                )
                self.notify(
                    f"{format_money(payment.amount, get_settings().business.currency)} "
                    f"for {quarter.label}",
                    title="payment recorded",
                )
            except ValueError:
                self.notify("date must be YYYY-MM-DD", severity="error")
            except TtdError as exc:
                self.notify(str(exc), severity="error")
            await self.refresh_data()

        self.app.push_screen(TaxPaymentModal(), _record)
