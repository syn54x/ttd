"""`ttd report …` commands."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from cyclopts import Parameter

from ttd.cli._output import console, table
from ttd.cli._run import TtdApp, with_db
from ttd.config.loader import get_settings
from ttd.core.errors import TtdError
from ttd.core.money import format_hours
from ttd.core.rollup import EntryFacts, amount, rollup_days, seconds_by_date
from ttd.core.taxes import compute_set_aside
from ttd.reporting import periods
from ttd.reporting.render import day_series, hours_cell, money_cell, sparkline
from ttd.services import entries as entry_svc
from ttd.services import projects as project_svc
from ttd.storage.models import pk

app = TtdApp(name="report", help="Summaries by day, week, month, or range.")

ProjectOpt = Annotated[str | None, Parameter(name=["--project", "-p"])]
ClientOpt = Annotated[str | None, Parameter(name="--client")]
ByOpt = Annotated[str, Parameter(name="--by", help="Group rows by: day|project|client")]


def _parse_date(raw: str, what: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise TtdError(f"{what} must be YYYY-MM-DD (got '{raw}')") from exc


async def _gather(period: periods.Period, project: str | None, client: str | None):
    rows = await entry_svc.list_entries(
        project_slug=project,
        client_slug=client,
        date_from=period.start,
        date_to=period.end,
    )
    facts = []
    rates: dict = {}
    meta: dict = {}
    for r in rows:
        facts.append(
            EntryFacts(
                project_id=pk(r.project),
                client_id=pk(r.client),
                work_date=r.entry.work_date,
                seconds=r.entry.seconds,
                billable=r.entry.billable,
                note=r.entry.note,
                invoiced=r.entry.invoice_id is not None,
            )
        )
        if r.project.id not in rates:
            rates[r.project.id] = await project_svc.effective_rate(r.project)
            meta[r.project.id] = (r.project, r.client)
    return facts, rates, meta


def _render(period: periods.Period, facts, rates, meta, by: str) -> None:
    settings = get_settings()
    console.print(f"\n[bold]{period.label}[/bold]")
    if not facts:
        console.print("[muted]No entries in this period.[/muted]")
        return

    cells = rollup_days(facts)
    days = period.days()
    total_seconds = sum(f.seconds for f in facts)
    total_amount = Decimal("0")
    total_tax = Decimal("0")
    set_aside_rate = settings.tax.set_aside_rate  # 0 hides the tax columns
    any_rate = False

    if by == "day":
        t = table("Date", "Project", "Entries", "Hours", "Amount")
        last_day = None
        for cell in cells:
            project, client = meta[cell.project_id]
            billed = cell.billed_seconds(settings.billing)
            value = amount(billed, rates[cell.project_id])
            if value is not None:
                total_amount += value
                total_tax += compute_set_aside(value, set_aside_rate)
                any_rate = True
            day_label = cell.work_date.strftime("%a %b %-d")
            t.add_row(
                day_label if day_label != last_day else "",
                f"{client.slug}/{project.slug}",
                str(cell.entry_count),
                hours_cell(cell.seconds, cell.billable_seconds),
                money_cell(value, client.currency),
            )
            last_day = day_label
        console.print(t)
    else:
        key_of = (
            (lambda c: c.project_id) if by == "project" else (lambda c: meta[c.project_id][1].id)
        )
        groups: dict = {}
        for cell in cells:
            groups.setdefault(key_of(cell), []).append(cell)
        headers = ["Client" if by == "client" else "Project", "Days", "Hours", "Activity", "Amount"]
        if set_aside_rate > 0:
            headers += ["Est. Tax", "Take-Home"]
        t = table(*headers)
        for _, group in sorted(groups.items(), key=lambda kv: -sum(c.seconds for c in kv[1])):
            project, client = meta[group[0].project_id]
            label = client.slug if by == "client" else f"{client.slug}/{project.slug}"
            seconds = sum(c.seconds for c in group)
            billable = sum(c.billable_seconds for c in group)
            value = Decimal("0")
            has_rate = False
            for c in group:
                v = amount(c.billed_seconds(settings.billing), rates[c.project_id])
                if v is not None:
                    value += v
                    has_rate = True
            tax = compute_set_aside(value, set_aside_rate)
            if has_rate:
                total_amount += value
                total_tax += tax
                any_rate = True
            group_by_date = seconds_by_date([f for f in facts if key_of_fact(f, by, meta) == label])
            row = [
                label,
                str(len({c.work_date for c in group})),
                hours_cell(seconds, billable),
                sparkline(day_series(group_by_date, days)) if len(days) > 1 else "",
                money_cell(value if has_rate else None, client.currency),
            ]
            if set_aside_rate > 0:
                row += [
                    money_cell(tax if has_rate else None, client.currency),
                    money_cell(value - tax if has_rate else None, client.currency),
                ]
            t.add_row(*row)
        console.print(t)

    summary = f"Total: [bold]{format_hours(total_seconds)}[/bold]"
    if any_rate:
        currency = next(iter(meta.values()))[1].currency
        summary += f"  ·  [bold]{money_cell(total_amount, currency)}[/bold] billable value"
        if set_aside_rate > 0:
            summary += (
                f"  ·  [bold]{money_cell(total_tax, currency)}[/bold] est. tax"
                f"  ·  [bold]{money_cell(total_amount - total_tax, currency)}[/bold] take-home"
            )
    console.print(summary)


def key_of_fact(f: EntryFacts, by: str, meta: dict) -> str:
    project, client = meta[f.project_id]
    return client.slug if by == "client" else f"{client.slug}/{project.slug}"


async def _run(period: periods.Period, project: str | None, client: str | None, by: str) -> None:
    if by not in ("day", "project", "client"):
        raise TtdError(f"--by must be day, project, or client (got '{by}')")
    facts, rates, meta = await _gather(period, project, client)
    _render(period, facts, rates, meta, by)


@app.command(name="day")
@with_db
async def day(
    on: Annotated[str | None, Parameter(help="YYYY-MM-DD, default today")] = None,
    *,
    project: ProjectOpt = None,
    client: ClientOpt = None,
) -> None:
    """One day's work."""
    d = _parse_date(on, "DATE") if on else datetime.now().date()
    await _run(periods.day_period(d), project, client, "day")


@app.command(name="week")
@with_db
async def week(
    *,
    last: Annotated[bool, Parameter(help="Previous week")] = False,
    project: ProjectOpt = None,
    client: ClientOpt = None,
    by: ByOpt = "project",
) -> None:
    """This (or last) week."""
    period = periods.week_period(datetime.now().date(), get_settings().display.week_start, last)
    await _run(period, project, client, by)


@app.command(name="month")
@with_db
async def month(
    ym: Annotated[str | None, Parameter(help="YYYY-MM, default current")] = None,
    *,
    last: Annotated[bool, Parameter(help="Previous month")] = False,
    project: ProjectOpt = None,
    client: ClientOpt = None,
    by: ByOpt = "project",
) -> None:
    """A calendar month."""
    period = periods.month_period(datetime.now().date(), last=last, ym=ym)
    await _run(period, project, client, by)


@app.command(name="range")
@with_db
async def range_(
    *,
    date_from: Annotated[str, Parameter(name="--from")],
    date_to: Annotated[str, Parameter(name="--to")],
    project: ProjectOpt = None,
    client: ClientOpt = None,
    by: ByOpt = "project",
) -> None:
    """An arbitrary date range."""
    period = periods.range_period(_parse_date(date_from, "--from"), _parse_date(date_to, "--to"))
    await _run(period, project, client, by)
