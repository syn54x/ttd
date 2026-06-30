from datetime import date
from decimal import Decimal

from ttd.config.schema import Settings
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
