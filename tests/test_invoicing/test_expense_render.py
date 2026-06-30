from datetime import date
from decimal import Decimal

import pytest
from fpdf import FPDF
from pypdf import PdfReader

from ttd.cli.invoices import _resolve_formats
from ttd.config.schema import Settings
from ttd.core.errors import TtdError
from ttd.invoicing.markdown import render_markdown
from ttd.invoicing.pdf import render_pdf
from ttd.reporting import periods
from ttd.services import clients as client_svc
from ttd.services import expenses as expense_svc
from ttd.services import invoicing as svc
from ttd.services import projects as project_svc


async def _invoice_with_expense(db):
    await client_svc.create_client("Acme Corp", hourly_rate=Decimal("150"))
    await project_svc.create_project("API Rewrite", "acme-corp")
    await expense_svc.add_expense(
        "api-rewrite", "Claude Code", Decimal("100"), incurred_date=date(2026, 6, 15)
    )
    period = periods.range_period(date(2026, 6, 1), date(2026, 6, 30))
    settings = Settings()
    invoice = await svc.persist_draft(
        await svc.build_draft("acme-corp", period, settings), settings
    )
    return await svc.get_invoice(invoice.number), settings


async def test_markdown_shows_expense_section(db):
    view, settings = await _invoice_with_expense(db)
    md = render_markdown(view, settings)
    assert "Reimbursable expenses" in md
    assert "Claude Code" in md
    assert "Expenses" in md  # totals line


async def test_pdf_renders_with_expenses(db, tmp_path):
    view, settings = await _invoice_with_expense(db)
    out = render_pdf(view, settings, tmp_path / "inv.pdf")
    assert out.exists() and out.stat().st_size > 0


async def test_no_expense_invoice_omits_section(db, tmp_path):
    await client_svc.create_client("Acme Corp", hourly_rate=Decimal("150"))
    await project_svc.create_project("API Rewrite", "acme-corp")
    from datetime import datetime

    from ttd.services import entries as entry_svc

    await entry_svc.log_entry(
        "2026-06-10 9am-11am", "api-rewrite", now=datetime(2026, 6, 10, 12, 0)
    )
    period = periods.range_period(date(2026, 6, 1), date(2026, 6, 30))
    settings = Settings()
    invoice = await svc.persist_draft(
        await svc.build_draft("acme-corp", period, settings), settings
    )
    view = await svc.get_invoice(invoice.number)
    md = render_markdown(view, settings)
    assert "Reimbursable expenses" not in md
    assert "Expenses (reimbursable)" not in md


async def test_pdf_appends_pdf_receipt_pages(db, tmp_path):
    await client_svc.create_client("Acme Corp", hourly_rate=Decimal("150"))
    await project_svc.create_project("API Rewrite", "acme-corp")
    exp = await expense_svc.add_expense(
        "api-rewrite", "Claude", Decimal("100"), incurred_date=date(2026, 6, 15)
    )
    # a real 1-page PDF as the receipt
    receipt_pdf = tmp_path / "receipt.pdf"
    r = FPDF()
    r.add_page()
    r.set_font("helvetica", size=12)
    r.cell(0, 10, "RECEIPT")
    r.output(str(receipt_pdf))
    await expense_svc.add_receipt(str(exp.id)[:8], receipt_pdf)

    period = periods.range_period(date(2026, 6, 1), date(2026, 6, 30))
    settings = Settings()
    invoice = await svc.persist_draft(
        await svc.build_draft("acme-corp", period, settings), settings
    )
    view = await svc.get_invoice(invoice.number)

    decoded = [await expense_svc.get_receipt(str(exp.id)[:8])]
    with_r = render_pdf(view, settings, tmp_path / "yes.pdf", receipts=decoded)
    without = render_pdf(view, settings, tmp_path / "no.pdf", receipts=None)
    assert len(PdfReader(str(with_r)).pages) > len(PdfReader(str(without)).pages)


async def test_invoice_has_receipts(db, tmp_path):
    view, _settings = await _invoice_with_expense(db)  # expense, no receipt
    assert await svc.invoice_has_receipts(view) is False


def test_resolve_formats_defaults_to_pdf():
    assert _resolve_formats(pdf=False, md=False, receipts=False, has_receipts=False) == (
        True,
        False,
    )


def test_resolve_formats_md_blocked_when_receipts_present():
    with pytest.raises(TtdError):
        _resolve_formats(pdf=False, md=True, receipts=True, has_receipts=True)


def test_resolve_formats_md_ok_when_no_receipts_on_invoice():
    assert _resolve_formats(pdf=True, md=True, receipts=True, has_receipts=False) == (True, True)
