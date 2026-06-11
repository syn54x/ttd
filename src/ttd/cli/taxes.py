"""`ttd tax …` commands: set-aside dashboard and IRS estimated-tax payments."""

from datetime import date
from decimal import Decimal
from typing import Annotated

from cyclopts import Parameter

from ttd.cli._output import console, success, table, warn
from ttd.cli._run import TtdApp, with_db
from ttd.config.loader import get_settings
from ttd.core.errors import TtdError
from ttd.core.money import format_money, parse_money
from ttd.core.taxes import TaxQuarter
from ttd.services import taxes as svc
from ttd.storage.models import pk

app = TtdApp(name="tax", help="Track tax set-aside and IRS estimated-tax payments.")


def _parse_date(raw: str, what: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise TtdError(f"{what} must be YYYY-MM-DD (got '{raw}')") from exc


async def _print_status(year: int | None) -> None:
    settings = get_settings()
    year = year or date.today().year
    currency = settings.business.currency
    summaries = await svc.year_summary(year, settings)

    t = table("Quarter", "Window", "Due", "Income", "Set aside", "Remitted", "Balance")
    for s in summaries:
        q = s.quarter
        t.add_row(
            q.label,
            f"{q.start:%b %-d} – {q.end:%b %-d}",
            f"{q.due_date:%b %-d %Y}",
            format_money(s.income, currency),
            format_money(s.set_aside, currency),
            format_money(s.remitted, currency),
            format_money(s.balance, currency),
        )
    t.add_row(
        "[bold]total[/bold]",
        "",
        "",
        format_money(sum((s.income for s in summaries), Decimal("0")), currency),
        format_money(sum((s.set_aside for s in summaries), Decimal("0")), currency),
        format_money(sum((s.remitted for s in summaries), Decimal("0")), currency),
        format_money(sum((s.balance for s in summaries), Decimal("0")), currency),
    )
    console.print(t)
    if settings.tax.set_aside_rate == 0 and all(s.invoice_count == 0 for s in summaries):
        warn("Set a rate first: ttd config set tax.set_aside_rate 0.32")


@app.command(name="status")
@with_db
async def status(
    *, year: Annotated[int | None, Parameter(help="Tax year (default current)")] = None
) -> None:
    """Quarterly dashboard: income received, set aside, remitted, balance."""
    await _print_status(year)


@app.command(name="pay")
@with_db
async def pay(
    quarter: Annotated[str, Parameter(help="IRS quarter, e.g. 2026q2 (or q2 for this year)")],
    amount: str,
    *,
    on: Annotated[str | None, Parameter(name="--date", help="YYYY-MM-DD (default today)")] = None,
    note: str = "",
) -> None:
    """Record an estimated-tax payment, e.g. `ttd tax pay 2026q2 5200`."""
    parsed = TaxQuarter.parse(quarter, date.today())
    payment = await svc.record_payment(
        parsed,
        parse_money(amount),
        paid_on=_parse_date(on, "--date") if on else None,
        note=note,
    )
    success(
        f"Recorded {format_money(payment.amount, get_settings().business.currency)} "
        f"for {parsed.label} ({payment.paid_on})"
    )


@app.command(name="payments")
@with_db
async def payments(
    *, year: Annotated[int | None, Parameter(help="Filter to one tax year")] = None
) -> None:
    """List recorded IRS payments."""
    rows = await svc.list_payments(year)
    if not rows:
        console.print("[muted]No payments recorded — `ttd tax pay 2026q2 AMOUNT`[/muted]")
        return
    currency = get_settings().business.currency
    t = table("Id", "Quarter", "Amount", "Date", "Note")
    for p in rows:
        t.add_row(
            str(pk(p))[:8],
            TaxQuarter(p.year, p.quarter).label,
            format_money(p.amount, currency),
            str(p.paid_on),
            p.note,
        )
    console.print(t)


@app.command(name="rm")
@with_db
async def rm(payment_id: Annotated[str, Parameter(help="Payment id (prefix ok)")]) -> None:
    """Delete a mistakenly recorded payment."""
    payment = await svc.remove_payment(payment_id)
    quarter = TaxQuarter(payment.year, payment.quarter)
    success(
        f"Removed {format_money(payment.amount, get_settings().business.currency)} "
        f"payment for {quarter.label}"
    )


@app.default
@with_db
async def default(*, year: Annotated[int | None, Parameter(show=False)] = None) -> None:
    """Quarterly dashboard (same as `ttd tax status`)."""
    await _print_status(year)
