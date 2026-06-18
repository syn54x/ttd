"""`ttd invoice …` commands."""

from datetime import date, datetime
from pathlib import Path
from typing import Annotated

from cyclopts import Parameter
from pydantic import BaseModel, Field

from ttd.cli._interactive import interactive_fill
from ttd.cli._output import console, success, table
from ttd.cli._pickers import client_choices
from ttd.cli._run import TtdApp, with_db
from ttd.config.loader import get_settings
from ttd.core.errors import TtdError
from ttd.core.money import format_hours, format_money
from ttd.core.taxes import compute_set_aside, format_rate
from ttd.invoicing.markdown import write_markdown
from ttd.invoicing.pdf import render_pdf
from ttd.reporting import periods
from ttd.services import invoicing as svc
from ttd.services import taxes as taxes_svc
from ttd.storage.models import Invoice, enum_value

app = TtdApp(name="invoice", help="Create and manage invoices.")

STATUS_STYLE = {"draft": "muted", "sent": "warn", "paid": "ok", "void": "err"}


def _status_pill(status: str) -> str:
    return f"[{STATUS_STYLE.get(status, 'muted')}]{status}[/]"


def _estimate_cells(invoice: Invoice, estimate: taxes_svc.InvoiceEstimate | None) -> list[str]:
    """``Est. Tax`` and ``Take-Home`` cells; unpaid previews render muted."""
    if estimate is None:
        return ["[muted]—[/muted]", "[muted]—[/muted]"]
    cells = [
        format_money(estimate.set_aside, invoice.currency),
        format_money(estimate.take_home, invoice.currency),
    ]
    if enum_value(invoice.status) != "paid":  # not frozen yet — current-rate preview
        cells = [f"[muted]{cell}[/muted]" for cell in cells]
    return cells


def _parse_date(raw: str, what: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise TtdError(f"{what} must be YYYY-MM-DD (got '{raw}')") from exc


def _resolve_period(
    month: str | None, date_from: str | None, date_to: str | None
) -> periods.Period:
    if month is not None:
        return periods.month_period(datetime.now().date(), ym=month)
    if date_from is not None and date_to is not None:
        return periods.range_period(_parse_date(date_from, "--from"), _parse_date(date_to, "--to"))
    if date_from or date_to:
        raise TtdError("Pass both --from and --to (or use --month)")
    # default: last calendar month — the usual "invoice my last month" flow
    return periods.month_period(datetime.now().date(), last=True)


def _output_paths(view: svc.InvoiceView, out: Path | None) -> Path:
    settings = get_settings()
    base = out or settings.invoice.output_dir
    return base / f"{view.invoice.number}-{view.client.slug}"


def _render_files(view: svc.InvoiceView, pdf: bool, md: bool, out: Path | None) -> None:
    settings = get_settings()
    stem = _output_paths(view, out)
    if pdf:
        path = render_pdf(view, settings, stem.with_suffix(".pdf"))
        success(f"Wrote {path}")
    if md:
        path = write_markdown(view, settings, stem.with_suffix(".md"))
        success(f"Wrote {path}")


def _print_draft(draft: svc.Draft) -> None:
    t = table("Date", "Description", "Hours", "Rate", "Amount")
    currency = draft.client.currency
    for line in draft.lines:
        t.add_row(
            line.work_date.strftime("%a %b %-d"),
            line.description,
            f"{line.billed_seconds / 3600:.2f}",
            format_money(line.rate, currency),
            format_money(line.amount, currency),
        )
    console.print(t)
    console.print(f"Subtotal: {format_money(draft.subtotal, currency)}")
    if draft.tax:
        console.print(f"Tax: {format_money(draft.tax, currency)}")
    console.print(f"[bold]Total: {format_money(draft.total, currency)}[/bold]")
    rate = get_settings().tax.set_aside_rate
    if rate > 0:
        preview = compute_set_aside(draft.subtotal, rate)
        console.print(
            f"[muted]Set aside at {format_rate(rate)} when paid: "
            f"{format_money(preview, currency)} · take-home "
            f"{format_money(draft.subtotal - preview, currency)}[/muted]"
        )


def _validate_month(text: str) -> bool | str:
    if not text.strip():
        return True  # blank = last month
    try:
        periods.month_period(datetime.now().date(), ym=text.strip())
    except TtdError as exc:
        return str(exc)
    return True


class InvoiceCreateInput(BaseModel):
    client: str = Field(
        json_schema_extra={"prompt": "Client", "widget": "select", "choices": client_choices}
    )
    month: str | None = Field(
        None,
        json_schema_extra={
            "prompt": "Month YYYY-MM (blank for last month)",
            "validate": _validate_month,
        },
    )
    pdf: bool = Field(True, json_schema_extra={"prompt": "Render PDF?"})
    md: bool = Field(False, json_schema_extra={"prompt": "Render Markdown?"})


@app.command(name="create")
@with_db
async def create(
    *,
    client: Annotated[str | None, Parameter(help="Client slug")] = None,
    month: Annotated[str | None, Parameter(help="YYYY-MM")] = None,
    date_from: Annotated[str | None, Parameter(name="--from")] = None,
    date_to: Annotated[str | None, Parameter(name="--to")] = None,
    number: Annotated[str | None, Parameter(help="Override the number")] = None,
    pdf: Annotated[bool, Parameter(help="Render a PDF")] = False,
    md: Annotated[bool, Parameter(help="Render Markdown")] = False,
    out: Annotated[Path | None, Parameter(help="Output directory")] = None,
    dry_run: Annotated[bool, Parameter(help="Preview, change nothing")] = False,
    interactive: Annotated[
        bool, Parameter(name=["--interactive", "-i"], help="Fill remaining fields via a form")
    ] = False,
) -> None:
    """Invoice a client's uninvoiced billable work (defaults to last month)."""
    settings = get_settings()
    if interactive:
        data = await interactive_fill(
            InvoiceCreateInput,
            {"client": client, "month": month, "pdf": pdf or None, "md": md or None},
        )
        client, month, pdf, md = data.client, data.month, data.pdf, data.md
    if client is None:
        raise TtdError("--client is required (or use -i for the interactive form)")
    period = _resolve_period(month, date_from, date_to)

    draft = await svc.build_draft(client, period, settings)
    view = None
    if not dry_run:
        invoice = await svc.persist_draft(draft, settings, number=number)
        view = await svc.get_invoice(invoice.number)

    console.print(f"\n[bold]{draft.client.name}[/bold] — {period.label}")
    _print_draft(draft)
    if dry_run:
        console.print("[muted]Dry run — nothing created.[/muted]")
        return
    assert view is not None
    success(f"Created invoice [accent]{view.invoice.number}[/accent]")
    _render_files(view, pdf, md, out)


@app.command(name="list")
@with_db
async def list_() -> None:
    """List invoices, newest first."""
    rows = await svc.list_invoices()
    if not rows:
        console.print("[muted]No invoices yet — `ttd invoice create --client SLUG`[/muted]")
        return
    rate = get_settings().tax.set_aside_rate
    estimates = [taxes_svc.estimate_invoice(invoice, rate) for invoice, _ in rows]
    show_tax = any(e is not None for e in estimates)
    headers = ["Number", "Client", "Period", "Total"]
    if show_tax:
        headers += ["Est. Tax", "Take-Home"]
    t = table(*headers, "Status")
    for (invoice, client), estimate in zip(rows, estimates, strict=True):
        row = [
            invoice.number,
            client.slug,
            f"{invoice.period_start:%b %-d} – {invoice.period_end:%b %-d %Y}",
            format_money(invoice.total, invoice.currency),
        ]
        if show_tax:
            row += _estimate_cells(invoice, estimate)
        t.add_row(*row, _status_pill(enum_value(invoice.status)))
    console.print(t)


@app.command(name="show")
@with_db
async def show(number: str) -> None:
    """Show one invoice with line items."""
    view = await svc.get_invoice(number)
    invoice, client = view.invoice, view.client
    console.print(
        f"\n[bold]Invoice {invoice.number}[/bold]  {_status_pill(enum_value(invoice.status))}"
    )
    console.print(
        f"{client.name} · issued {invoice.issued_date} · due {invoice.due_date or 'on receipt'}"
    )
    t = table("Date", "Description", "Hours", "Rate", "Amount")
    for line in view.lines:
        t.add_row(
            line.work_date.strftime("%a %b %-d"),
            line.description,
            format_hours(line.billed_seconds),
            format_money(line.rate, invoice.currency),
            format_money(line.amount, invoice.currency),
        )
    console.print(t)
    console.print(f"[bold]Total: {format_money(invoice.total, invoice.currency)}[/bold]")
    settings = get_settings()
    if enum_value(invoice.status) == "paid":
        paid_on, rate, set_aside = taxes_svc.paid_facts(invoice, settings.tax.set_aside_rate)
        if set_aside:
            console.print(
                f"Set aside ({format_rate(rate)}): "
                f"{format_money(set_aside, invoice.currency)} · take-home "
                f"{format_money(invoice.subtotal - set_aside, invoice.currency)} · paid {paid_on}"
            )
    elif settings.tax.set_aside_rate > 0 and enum_value(invoice.status) != "void":
        preview = compute_set_aside(invoice.subtotal, settings.tax.set_aside_rate)
        console.print(
            f"[muted]Set aside at {format_rate(settings.tax.set_aside_rate)} when paid: "
            f"{format_money(preview, invoice.currency)} · take-home "
            f"{format_money(invoice.subtotal - preview, invoice.currency)}[/muted]"
        )


@app.command(name="render")
@with_db
async def render(
    number: str,
    *,
    pdf: bool = False,
    md: bool = False,
    out: Path | None = None,
) -> None:
    """(Re)render an invoice's PDF/Markdown files."""
    if not pdf and not md:
        pdf = md = True
    view = await svc.get_invoice(number)
    _render_files(view, pdf, md, out)


def _print_refresh_diff(preview: svc.RefreshPreview) -> None:
    invoice = preview.invoice
    currency = invoice.currency
    status = enum_value(invoice.status)
    console.print(f"\n[bold]Refresh {invoice.number}[/bold]  {_status_pill(status)}")
    if preview.blocked_reason:
        console.print(f"[err]{preview.blocked_reason}[/err]")
    elif status == "paid" and preview.can_apply:
        console.print("[muted]Paid invoice — only line descriptions will be updated.[/muted]")
    elif not preview.has_changes:
        console.print("[muted]No changes — invoice lines match current rules.[/muted]")

    changed = [d for d in preview.lines if d.changed]
    if changed:
        t = table("Date", "Project", "Description", "Hours", "Rate", "Amount")
        for diff in changed:
            t.add_row(
                diff.work_date.strftime("%a %b %-d"),
                diff.project_name,
                _refresh_diff_cell("description", diff, currency),
                _refresh_diff_cell("billed_seconds", diff, currency),
                _refresh_diff_cell("rate", diff, currency),
                _refresh_diff_cell("amount", diff, currency),
            )
        console.print(t)

    sub = format_money(preview.before_subtotal, currency)
    sub_after = format_money(preview.after_subtotal, currency)
    total = format_money(preview.before_total, currency)
    total_after = format_money(preview.after_total, currency)
    if preview.totals_changed:
        console.print(f"Subtotal: {sub} → [bold]{sub_after}[/bold]")
        if preview.before_tax or preview.after_tax:
            console.print(
                f"Tax: {format_money(preview.before_tax, currency)} → "
                f"[bold]{format_money(preview.after_tax, currency)}[/bold]"
            )
        console.print(f"Total: {total} → [bold]{total_after}[/bold]")
    else:
        console.print(f"Subtotal: {sub} · Total: {total}")


def _refresh_diff_cell(field: str, diff: svc.LineDiff, currency: str) -> str:
    before = diff.before
    after = diff.after
    if field == "description":
        old = svc.flatten_line_description(before.description if before else "")
        new = svc.flatten_line_description(after.description)
    elif field == "billed_seconds":
        old, new = (
            f"{before.billed_seconds / 3600:.2f}" if before else "0.00",
            f"{after.billed_seconds / 3600:.2f}",
        )
    elif field == "rate":
        old = format_money(before.rate, currency) if before else "—"
        new = format_money(after.rate, currency)
    else:
        old = format_money(before.amount, currency) if before else "—"
        new = format_money(after.amount, currency)
    if field not in diff.changed or old == new:
        return new
    return f"[muted]{old}[/muted] → {new}"


@app.command(name="refresh")
@with_db
async def refresh(
    number: str,
    *,
    apply: Annotated[bool, Parameter(name="--apply", help="Apply changes when allowed")] = False,
) -> None:
    """Recompute invoice lines from locked entries and show a before/after diff."""
    settings = get_settings()
    preview = await svc.preview_refresh(number, settings)
    _print_refresh_diff(preview)
    if apply:
        if not preview.can_apply:
            raise TtdError(preview.blocked_reason or "No changes to apply")
        invoice = await svc.apply_refresh(number, preview, settings)
        success(f"Updated invoice [accent]{invoice.number}[/accent]")


@app.command(name="mark")
@with_db
async def mark(
    number: str,
    status: Annotated[str, Parameter(help="sent|paid|void")],
    *,
    paid_date: Annotated[
        str | None, Parameter(name="--paid-date", help="YYYY-MM-DD (default today); paid only")
    ] = None,
) -> None:
    """Update invoice status; void releases its entries for re-invoicing.

    Marking paid records the paid date and freezes the tax set-aside at the
    current `tax.set_aside_rate` — re-mark with --paid-date to correct either.
    """
    settings = get_settings()
    invoice = await svc.mark_invoice(
        number,
        status,
        paid_date=_parse_date(paid_date, "--paid-date") if paid_date else None,
        set_aside_rate=settings.tax.set_aside_rate,
    )
    message = f"Invoice {invoice.number} marked {enum_value(invoice.status)}"
    if invoice.set_aside and invoice.set_aside_rate:
        message += (
            f" ({invoice.paid_date}) — set aside "
            f"{format_money(invoice.set_aside, invoice.currency)}"
            f" ({format_rate(invoice.set_aside_rate)})"
        )
    success(message)
