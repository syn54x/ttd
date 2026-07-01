from datetime import date
from decimal import Decimal

from ttd.config.schema import Settings
from ttd.reporting import periods
from ttd.services import clients as client_svc
from ttd.services import expenses as expense_svc
from ttd.services import invoicing as svc
from ttd.services import projects as project_svc


async def _invoice_with_receipt(db, tmp_path):
    await client_svc.create_client("Acme Corp", hourly_rate=Decimal("150"))
    await project_svc.create_project("API Rewrite", "acme-corp")
    exp = await expense_svc.add_expense(
        "api-rewrite", "Claude", Decimal("100"), incurred_date=date(2026, 6, 15)
    )
    rp = tmp_path / "r.pdf"
    rp.write_bytes(b"%PDF-1.4\n\xff\xd8 binary")
    await expense_svc.add_receipt(str(exp.id)[:8], rp)
    period = periods.range_period(date(2026, 6, 1), date(2026, 6, 30))
    settings = Settings()
    invoice = await svc.persist_draft(
        await svc.build_draft("acme-corp", period, settings), settings
    )
    return await svc.get_invoice(invoice.number)


async def test_load_invoice_receipts_returns_decoded(db, tmp_path):
    view = await _invoice_with_receipt(db, tmp_path)
    receipts = await expense_svc.load_invoice_receipts(view.expense_lines)
    assert len(receipts) == 1
    filename, content_type, data = receipts[0]
    assert filename == "r.pdf"
    assert content_type == "application/pdf"
    assert data == b"%PDF-1.4\n\xff\xd8 binary"


async def test_load_invoice_receipts_empty_when_none(db):
    assert await expense_svc.load_invoice_receipts([]) == []
