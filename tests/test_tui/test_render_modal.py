"""Tests for RenderFormatModal reactivity and _write_selected_formats."""

from datetime import date
from decimal import Decimal

from textual.app import App
from textual.widgets import Static, Switch

from ttd.config.schema import InvoiceConfig, Settings


class ModalHostApp(App):
    """Bare host app that pushes a modal on mount, for isolated modal testing."""

    CSS_PATH = "../../src/ttd/tui/ttd.tcss"

    def __init__(self, modal):
        super().__init__()
        self._modal = modal
        self.result = "UNSET"

    async def on_mount(self) -> None:
        def _done(value):
            self.result = value

        await self.push_screen(self._modal, _done)


async def test_modal_receipts_on_disables_markdown():
    from ttd.tui.screens.invoices import RenderFormatModal

    modal = RenderFormatModal(has_receipts=True)
    app = ModalHostApp(modal)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, RenderFormatModal)
        # receipts enabled + on; markdown disabled at start (receipts default on)
        assert modal.query_one("#receipts", Switch).disabled is False
        assert modal.query_one("#receipts", Switch).value is True
        assert modal.query_one("#md", Switch).disabled is True
        # turn receipts off -> markdown re-enabled
        modal.query_one("#receipts", Switch).value = False
        await pilot.pause()
        assert modal.query_one("#md", Switch).disabled is False


async def test_modal_no_receipts_disables_receipts_switch():
    from ttd.tui.screens.invoices import RenderFormatModal

    modal = RenderFormatModal(has_receipts=False)
    app = ModalHostApp(modal)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert modal.query_one("#receipts", Switch).disabled is True
        assert modal.query_one("#md", Switch).disabled is False


async def test_write_selected_formats_pdf_with_receipts(db, tmp_path):
    # build an invoice whose expense has a receipt, then render via the helper
    from fpdf import FPDF
    from pypdf import PdfReader

    from ttd.reporting import periods
    from ttd.services import clients as client_svc
    from ttd.services import expenses as expense_svc
    from ttd.services import invoicing as svc
    from ttd.services import projects as project_svc
    from ttd.tui.screens.invoices import _write_selected_formats

    await client_svc.create_client("Acme Corp", hourly_rate=Decimal("150"))
    await project_svc.create_project("API Rewrite", "acme-corp")
    exp = await expense_svc.add_expense(
        "api-rewrite", "Claude", Decimal("100"), incurred_date=date(2026, 6, 15)
    )
    rp = tmp_path / "r.pdf"
    r = FPDF()
    r.add_page()
    r.set_font("helvetica", size=12)
    r.cell(0, 10, "RECEIPT")
    r.output(str(rp))
    await expense_svc.add_receipt(str(exp.id)[:8], rp)
    period = periods.range_period(date(2026, 6, 1), date(2026, 6, 30))
    settings = Settings(invoice=InvoiceConfig(output_dir=tmp_path / "out"))
    invoice = await svc.persist_draft(
        await svc.build_draft("acme-corp", period, settings), settings
    )
    view = await svc.get_invoice(invoice.number)

    await _write_selected_formats(view, settings, {"pdf": True, "md": False, "receipts": False})
    base_pdf = tmp_path / "out" / f"{invoice.number}-acme-corp.pdf"
    base_pages = len(PdfReader(str(base_pdf)).pages)
    with_r = await _write_selected_formats(
        view, settings, {"pdf": True, "md": False, "receipts": True}
    )
    assert len(PdfReader(str(base_pdf)).pages) > base_pages  # receipts appended
    assert any(".pdf" in name for name in with_r)


async def test_render_modal_no_format_selected():
    from ttd.tui.screens.invoices import RenderFormatModal

    modal = RenderFormatModal(has_receipts=False)
    app = ModalHostApp(modal)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, RenderFormatModal)
        # turn both switches off
        modal.query_one("#pdf", Switch).value = False
        modal.query_one("#md", Switch).value = False
        await pilot.pause()
        # click render button
        await pilot.click("#render")
        await pilot.pause()
        # modal should still be displayed (not dismissed)
        assert isinstance(app.screen, RenderFormatModal)
        # error message should be non-empty
        error_widget = modal.query_one("#render-error", Static)
        assert error_widget.content


async def test_write_selected_formats_markdown(db, tmp_path):
    from ttd.reporting import periods
    from ttd.services import clients as client_svc
    from ttd.services import expenses as expense_svc
    from ttd.services import invoicing as svc
    from ttd.services import projects as project_svc
    from ttd.tui.screens.invoices import _write_selected_formats

    await client_svc.create_client("Acme Corp", hourly_rate=Decimal("150"))
    await project_svc.create_project("API Rewrite", "acme-corp")
    await expense_svc.add_expense(
        "api-rewrite", "Claude", Decimal("100"), incurred_date=date(2026, 6, 15)
    )
    period = periods.range_period(date(2026, 6, 1), date(2026, 6, 30))
    settings = Settings(invoice=InvoiceConfig(output_dir=tmp_path / "out"))
    invoice = await svc.persist_draft(
        await svc.build_draft("acme-corp", period, settings), settings
    )
    view = await svc.get_invoice(invoice.number)
    wrote = await _write_selected_formats(
        view, settings, {"pdf": False, "md": True, "receipts": False}
    )
    assert (tmp_path / "out" / f"{invoice.number}-acme-corp.md").exists()
    assert any(name.endswith(".md") for name in wrote)
