"""Invoices: list with status pills, detail view, create wizard, render, mark paid."""

from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from ttd.config.schema import Settings

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Label, Markdown, Static, Switch

from ttd.config.loader import get_settings
from ttd.core.errors import TtdError
from ttd.core.money import format_hours, format_money
from ttd.invoicing.markdown import render_markdown, write_markdown
from ttd.invoicing.pdf import render_pdf
from ttd.reporting import periods
from ttd.services import invoicing as svc
from ttd.services import taxes as taxes_svc
from ttd.storage.models import Client, Invoice, enum_value
from ttd.tui.screens._base import TtdScreen
from ttd.tui.widgets.modals import ConfirmModal, PickerModal

PILL = {"draft": "dim", "sent": "#ffcf5c", "paid": "#3fcf8e", "void": "#ff5c5c"}


def _estimate_cells(invoice: Invoice, estimate: taxes_svc.InvoiceEstimate | None) -> list[str]:
    """``est. tax`` and ``take-home`` cells; unpaid previews render dim."""
    if estimate is None:
        return ["[dim]—[/dim]", "[dim]—[/dim]"]
    cells = [
        format_money(estimate.set_aside, invoice.currency),
        format_money(estimate.take_home, invoice.currency),
    ]
    if enum_value(invoice.status) != "paid":  # not frozen yet — current-rate preview
        cells = [f"[dim]{cell}[/dim]" for cell in cells]
    return cells


class InvoiceDetailModal(ModalScreen[None]):
    BINDINGS: ClassVar = [("escape", "dismiss", "close")]

    def __init__(self, view: svc.InvoiceView) -> None:
        super().__init__()
        self.view = view

    def compose(self) -> ComposeResult:
        invoice, client = self.view.invoice, self.view.client
        status = enum_value(invoice.status)
        with Vertical(classes="modal-box wide"):
            yield Label(
                f"invoice {invoice.number} · {client.name} · "
                f"[{PILL.get(status, 'dim')}]{status}[/]",
                classes="modal-title",
            )
            table = DataTable(id="detail-table")
            table.add_columns("date", "description", "hours", "rate", "amount")
            for line in self.view.lines:
                table.add_row(
                    line.work_date.strftime("%a %b %-d"),
                    line.description,
                    format_hours(line.billed_seconds),
                    format_money(line.rate, invoice.currency),
                    format_money(line.amount, invoice.currency),
                )
            yield table
            if self.view.expense_lines:
                yield Label("expenses", classes="section-title")
                expense_table = DataTable(id="expense-table", cursor_type="none")
                expense_table.add_columns("date", "description", "amount")
                for eline in self.view.expense_lines:
                    expense_table.add_row(
                        eline.incurred_date.strftime("%a %b %-d"),
                        eline.description,
                        format_money(eline.amount, invoice.currency),
                    )
                yield expense_table
            summary = (
                f"issued {invoice.issued_date} · due {invoice.due_date or 'on receipt'} · "
                f"[bold]{format_money(invoice.total, invoice.currency)}[/bold]"
            )
            estimate = taxes_svc.estimate_invoice(invoice, get_settings().tax.set_aside_rate)
            if estimate is not None:
                summary += (
                    f" · est. tax {format_money(estimate.set_aside, invoice.currency)}"
                    f" · take-home {format_money(estimate.take_home, invoice.currency)}"
                )
            yield Label(summary)
            yield Button("close (esc)", id="close")

    def on_button_pressed(self) -> None:
        self.dismiss()


class MarkdownPreviewModal(ModalScreen[None]):
    """Scrollable preview of an invoice's rendered Markdown."""

    BINDINGS: ClassVar = [("escape", "dismiss", "close")]

    def __init__(self, title: str, markdown: str) -> None:
        super().__init__()
        self.title_text = title
        self.markdown_source = markdown

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box wide markdown-preview"):
            yield Label(self.title_text, classes="modal-title")
            with VerticalScroll():
                yield Markdown(self.markdown_source)
            yield Label("[dim]esc close[/dim]")


class NewInvoiceModal(ModalScreen["svc.Draft | None"]):
    """Type a period, watch the invoice lines build live, then create.

    Dismisses with the previewed Draft so what you saw is exactly what
    gets persisted.
    """

    BINDINGS: ClassVar = [
        ("escape", "dismiss(None)", "cancel"),
        ("ctrl+s", "create", "create"),
    ]

    def __init__(self, client_slug: str) -> None:
        super().__init__()
        self.client_slug = client_slug
        self.draft: svc.Draft | None = None

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box wide"):
            yield Label(f"new invoice · {self.client_slug}", classes="modal-title")
            yield Label("Period (blank = last month)", classes="field-label")
            yield Input(
                placeholder="last month · this week · last two weeks · june 16–30 · 2026-05",
                id="period",
            )
            yield Static("", id="draft-status")
            table = DataTable(id="draft-table", cursor_type="none")
            table.add_columns("date", "description", "hours", "rate", "amount")
            yield table
            with Horizontal(classes="modal-buttons"):
                yield Button("Create (ctrl+s)", variant="primary", id="create", disabled=True)
                yield Button("Cancel (esc)", id="cancel")

    async def on_mount(self) -> None:
        await self._rebuild("")

    @on(Input.Changed, "#period")
    async def _period_changed(self, event: Input.Changed) -> None:
        await self._rebuild(event.value)

    @on(Input.Submitted, "#period")
    def _period_submitted(self) -> None:
        self.action_create()

    async def _rebuild(self, raw: str) -> None:
        status = self.query_one("#draft-status", Static)
        table = self.query_one("#draft-table", DataTable)
        button = self.query_one("#create", Button)
        table.clear()
        self.draft = None
        button.disabled = True

        try:
            period = periods.parse_period(
                raw, datetime.now().date(), week_start=get_settings().display.week_start
            )
        except TtdError as exc:
            status.update(f"[red]✗ {exc}[/red]")
            return
        try:
            draft = await svc.build_draft(self.client_slug, period, get_settings())
        except TtdError as exc:
            status.update(f"{period.label} — [dim]{exc}[/dim]")
            return

        currency = draft.client.currency
        entry_count = 0
        for line in draft.lines:
            entry_count += len(line.entry_ids)
            table.add_row(
                line.work_date.strftime("%a %b %-d"),
                line.description,
                f"{line.billed_seconds / 3600:.2f}",
                format_money(line.rate, currency),
                format_money(line.amount, currency),
            )
        if draft.expense_lines:
            table.add_row("", "-- reimbursable expenses --", "", "", "")
            for e in draft.expense_lines:
                table.add_row(
                    e.incurred_date.strftime("%a %b %-d"),
                    e.description,
                    "",
                    "",
                    format_money(e.amount, currency),
                )
        hours = format_hours(sum(line.billed_seconds for line in draft.lines))
        expense_note = (
            f" · {len(draft.expense_lines)} expense{'s' if len(draft.expense_lines) != 1 else ''}"
            if draft.expense_lines
            else ""
        )
        status.update(
            f"[#ffb000]✓[/#ffb000] {period.label} · {entry_count} "
            f"entr{'y' if entry_count == 1 else 'ies'} → {len(draft.lines)} "
            f"line{'s' if len(draft.lines) != 1 else ''} · {hours}"
            f"{expense_note} · "
            f"[bold]{format_money(draft.total, currency)}[/bold]"
        )
        self.draft = draft
        button.disabled = False

    @on(Button.Pressed, "#create")
    def _create_pressed(self) -> None:
        self.action_create()

    @on(Button.Pressed, "#cancel")
    def _cancel_pressed(self) -> None:
        self.dismiss(None)

    def action_create(self) -> None:
        if self.draft is not None:
            self.dismiss(self.draft)


def _format_diff_cell(
    field: str, diff: svc.LineDiff, currency: str, *, changed_only: bool = False
) -> str:
    if changed_only and field not in diff.changed:
        return ""
    before = diff.before
    after = diff.after
    if field == "description":
        old = svc.flatten_line_description(before.description if before else "")
        new = svc.flatten_line_description(after.description)
        if old == new:
            return new
        return f"[dim]{old}[/dim] → {new}"
    if field == "billed_seconds":
        old = format_hours(before.billed_seconds) if before else "0:00"
        new = format_hours(after.billed_seconds)
        if old == new:
            return new
        return f"[dim]{old}[/dim] → {new}"
    if field == "rate":
        old = format_money(before.rate, currency) if before else "—"
        new = format_money(after.rate, currency)
        if old == new:
            return new
        return f"[dim]{old}[/dim] → {new}"
    if field == "amount":
        old = format_money(before.amount, currency) if before else "—"
        new = format_money(after.amount, currency)
        if old == new:
            return new
        return f"[dim]{old}[/dim] → {new}"
    return ""


class InvoiceRefreshModal(ModalScreen["svc.RefreshPreview | None"]):
    """Before/after diff for recomputing invoice lines from locked entries."""

    BINDINGS: ClassVar = [
        ("escape", "dismiss(None)", "cancel"),
        ("ctrl+s", "apply", "apply"),
    ]

    def __init__(self, preview: svc.RefreshPreview) -> None:
        super().__init__()
        self.preview = preview

    def compose(self) -> ComposeResult:
        invoice = self.preview.invoice
        status = enum_value(invoice.status)
        currency = invoice.currency
        with Vertical(classes="modal-box wide"):
            yield Label(
                f"refresh · {invoice.number} · [{PILL.get(status, 'dim')}]{status}[/]",
                classes="modal-title",
            )
            if self.preview.blocked_reason:
                yield Static(f"[#ff5c5c]{self.preview.blocked_reason}[/#ff5c5c]")
            elif status == "paid" and self.preview.can_apply:
                yield Static("[dim]Paid invoice — only line descriptions will be updated.[/dim]")
            elif not self.preview.has_changes:
                yield Static("[dim]No changes — invoice lines match current rules.[/dim]")

            table = DataTable(id="refresh-table", cursor_type="none")
            table.add_columns("date", "project", "description", "hours", "rate", "amount")
            for diff in self.preview.lines:
                if not diff.changed:
                    continue
                table.add_row(
                    diff.work_date.strftime("%a %b %-d"),
                    diff.project_name,
                    _format_diff_cell("description", diff, currency),
                    _format_diff_cell("billed_seconds", diff, currency),
                    _format_diff_cell("rate", diff, currency),
                    _format_diff_cell("amount", diff, currency),
                )
            yield table

            totals = self.preview
            sub = format_money(totals.before_subtotal, currency)
            sub_after = format_money(totals.after_subtotal, currency)
            total = format_money(totals.before_total, currency)
            total_after = format_money(totals.after_total, currency)
            if totals.totals_changed:
                footer = (
                    f"subtotal {sub} → [bold]{sub_after}[/bold] · "
                    f"total {total} → [bold]{total_after}[/bold]"
                )
            else:
                footer = f"subtotal {sub} · total {total}"
            yield Label(footer)

            with Horizontal(classes="modal-buttons"):
                yield Button(
                    "Apply (ctrl+s)",
                    variant="primary",
                    id="apply",
                    disabled=not self.preview.can_apply,
                )
                yield Button("Cancel (esc)", id="cancel")

    @on(Button.Pressed, "#apply")
    def _apply_pressed(self) -> None:
        self.action_apply()

    @on(Button.Pressed, "#cancel")
    def _cancel_pressed(self) -> None:
        self.dismiss(None)

    def action_apply(self) -> None:
        if self.preview.can_apply:
            self.dismiss(self.preview)


class RenderFormatModal(ModalScreen[dict | None]):
    """Choose which files to render. Receipts embed into the PDF and are only
    available when the invoice has receipts; enabling them locks out Markdown."""

    BINDINGS: ClassVar = [("escape", "dismiss(None)", "cancel")]

    def __init__(self, has_receipts: bool) -> None:
        super().__init__()
        self.has_receipts = has_receipts

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Label("render invoice", classes="modal-title")
            with Horizontal(classes="form-toggle-row"):
                yield Switch(value=True, id="pdf")
                yield Label("PDF", classes="field-label")
            with Horizontal(classes="form-toggle-row"):
                yield Switch(value=False, id="md", disabled=self.has_receipts)
                yield Label("Markdown", classes="field-label")
            with Horizontal(classes="form-toggle-row"):
                yield Switch(value=self.has_receipts, id="receipts", disabled=not self.has_receipts)
                yield Label("Include receipts", classes="field-label")
            yield Static("", id="render-error", classes="form-error")
            with Horizontal(classes="modal-buttons"):
                yield Button("Render", variant="primary", id="render")
                yield Button("Cancel", id="cancel")

    @on(Switch.Changed, "#receipts")
    def _receipts_changed(self, event: Switch.Changed) -> None:
        md = self.query_one("#md", Switch)
        if event.value:
            self.query_one("#pdf", Switch).value = True
            md.value = False
            md.disabled = True
        else:
            md.disabled = False

    @on(Button.Pressed, "#render")
    def _do_render(self) -> None:
        pdf = self.query_one("#pdf", Switch).value
        md = self.query_one("#md", Switch).value
        receipts = self.query_one("#receipts", Switch).value
        if not pdf and not md:
            self.query_one("#render-error", Static).update("[red]Choose at least one format[/red]")
            return
        self.dismiss({"pdf": pdf, "md": md, "receipts": receipts})

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(None)


async def _write_selected_formats(
    view: "svc.InvoiceView", settings: "Settings", choice: dict
) -> list[str]:
    """Render the chosen formats; return the file names (with extension) written."""
    from ttd.services.expenses import load_invoice_receipts

    stem = settings.invoice.output_dir / f"{view.invoice.number}-{view.client.slug}"
    wrote: list[str] = []
    if choice["pdf"]:
        decoded = await load_invoice_receipts(view.expense_lines) if choice["receipts"] else None
        render_pdf(view, settings, stem.with_suffix(".pdf"), receipts=decoded)
        wrote.append(f"{stem.name}.pdf")
    if choice["md"]:
        write_markdown(view, settings, stem.with_suffix(".md"))
        wrote.append(f"{stem.name}.md")
    return wrote


class InvoicesScreen(TtdScreen):
    nav_id = "invoices"

    BINDINGS: ClassVar = [
        *TtdScreen.BINDINGS,
        ("n", "new_invoice", "new"),
        Binding("o", "open_detail", "open"),
        ("m", "preview_markdown", "preview md"),
        ("e", "render_files", "render"),
        ("u", "refresh_invoice", "update"),
        ("p", "mark('paid')", "paid"),
        ("t", "mark('sent')", "sent"),
        ("v", "mark('void')", "void"),
    ]

    def compose_content(self) -> ComposeResult:
        with Vertical(id="invoices"):
            yield Label("invoices", classes="section-title")
            yield DataTable(id="invoice-table", cursor_type="row")
            yield Label("", id="invoice-help", classes="muted")

    def setup(self) -> None:
        self._table_columns: tuple[str, ...] = ()

    async def render_data(self) -> None:
        rows = await svc.list_invoices()
        rate = get_settings().tax.set_aside_rate
        estimates = [taxes_svc.estimate_invoice(invoice, rate) for invoice, _ in rows]

        columns = ("number", "client", "period", "total", "status")
        if any(e is not None for e in estimates):
            columns = ("number", "client", "period", "total", "est. tax", "take-home", "status")
        table = self.query_one("#invoice-table", DataTable)
        if columns != self._table_columns:
            table.clear(columns=True)
            table.add_columns(*columns)
            self._table_columns = columns
        table.clear()
        for (invoice, client), estimate in zip(rows, estimates, strict=True):
            status = enum_value(invoice.status)
            row = [
                invoice.number,
                client.slug,
                f"{invoice.period_start:%b %-d} – {invoice.period_end:%b %-d %Y}",
                format_money(invoice.total, invoice.currency),
            ]
            if "est. tax" in columns:
                row += _estimate_cells(invoice, estimate)
            row.append(f"[{PILL.get(status, 'dim')}]{status}[/]")
            table.add_row(*row, key=invoice.number)
        self.query_one("#invoice-help", Label).update(
            f"{len(rows)} invoice{'s' if len(rows) != 1 else ''}   "
            "[dim]n new · o detail · u update · m preview md · e render · "
            "t sent · p paid · v void[/dim]"
        )

    def _selected_number(self) -> str | None:
        table = self.query_one("#invoice-table", DataTable)
        if table.row_count == 0 or table.cursor_row is None:
            return None
        return str(table.get_row_at(table.cursor_row)[0])

    async def action_open_detail(self) -> None:
        number = self._selected_number()
        if number is None:
            return
        view = await svc.get_invoice(number)
        self.app.push_screen(InvoiceDetailModal(view))

    async def action_preview_markdown(self) -> None:
        number = self._selected_number()
        if number is None:
            return
        view = await svc.get_invoice(number)
        markdown = render_markdown(view, get_settings())
        self.app.push_screen(MarkdownPreviewModal(f"markdown preview · {number}", markdown))

    async def action_render_files(self) -> None:
        number = self._selected_number()
        if number is None:
            return
        settings = get_settings()
        view = await svc.get_invoice(number)
        has_receipts = await svc.invoice_has_receipts(view)

        async def _render(choice: dict | None) -> None:
            if choice is None:
                return
            wrote = await _write_selected_formats(view, settings, choice)
            self.notify("wrote " + ", ".join(wrote), title="rendered")

        self.app.push_screen(RenderFormatModal(has_receipts), _render)

    async def action_refresh_invoice(self) -> None:
        number = self._selected_number()
        if number is None:
            return
        try:
            preview = await svc.preview_refresh(number, get_settings())
        except TtdError as exc:
            self.notify(str(exc), severity="error")
            return

        async def _done(accepted: svc.RefreshPreview | None) -> None:
            if accepted is None or not accepted.can_apply:
                return
            try:
                await svc.apply_refresh(number, accepted, get_settings())
                self.notify(f"updated {number}", title="refresh")
            except TtdError as exc:
                self.notify(str(exc), severity="error")
            await self.refresh_data()

        self.app.push_screen(InvoiceRefreshModal(preview), _done)

    async def action_mark(self, status: str) -> None:
        number = self._selected_number()
        if number is None:
            return

        async def _do(yes: bool | None = True) -> None:
            if not yes:
                return
            try:
                invoice = await svc.mark_invoice(
                    number, status, set_aside_rate=get_settings().tax.set_aside_rate
                )
                message = f"{number} marked {status}"
                if status == "paid" and invoice.set_aside:
                    message += f" · set aside {format_money(invoice.set_aside, invoice.currency)}"
                self.notify(message)
            except TtdError as exc:
                self.notify(str(exc), severity="error")
            await self.refresh_data()

        if status == "void":
            self.app.push_screen(ConfirmModal(f"Void {number} and release its entries?"), _do)
        else:
            await _do()

    async def action_new_invoice(self) -> None:
        clients = [
            (c.slug, f"{c.name} ({c.slug})")
            for c in sorted(await Client.all(), key=lambda c: c.name.lower())
            if c.archived_at is None
        ]
        if not clients:
            self.notify("no clients yet", severity="warning")
            return

        async def _picked(slug: str | None) -> None:
            if slug is None:
                return

            async def _done(draft: svc.Draft | None) -> None:
                if draft is None:
                    return
                try:
                    invoice = await svc.persist_draft(draft, get_settings())
                    self.notify(f"created {invoice.number}", title="invoice")
                except TtdError as exc:
                    self.notify(str(exc), severity="error")
                await self.refresh_data()

            self.app.push_screen(NewInvoiceModal(slug), _done)

        self.app.push_screen(PickerModal("invoice which client?", clients), _picked)
