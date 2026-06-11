from datetime import date, datetime
from decimal import Decimal

import pytest

from ttd.config.schema import BillingConfig, InvoiceConfig, Settings, UserConfig
from ttd.core.errors import ConflictError, TtdError
from ttd.invoicing.markdown import render_markdown
from ttd.invoicing.numbering import next_number
from ttd.reporting.periods import month_period
from ttd.services import clients as client_svc
from ttd.services import entries as entry_svc
from ttd.services import invoicing as svc
from ttd.services import projects as project_svc

NOW = datetime(2026, 6, 9, 15, 0)
JUNE = month_period(date(2026, 6, 9))

SETTINGS = Settings(
    user=UserConfig(name="Taylor", email="taylor@alumbraai.com"),
    billing=BillingConfig(rounding="up", increment_minutes=15),
    invoice=InvoiceConfig(payment_terms_days=30),
)


@pytest.fixture
async def seeded(db):
    await client_svc.create_client("Acme", hourly_rate=Decimal("150"))
    await project_svc.create_project("API", "acme")
    await entry_svc.log_entry("2026-06-08 9am to 11:50am", "api", now=NOW)  # 2h50 → 3h up
    await entry_svc.log_entry("2026-06-08 1pm to 2pm", "api", now=NOW)
    await entry_svc.log_entry("2026-06-09 2h", "api", now=NOW)
    await entry_svc.log_entry("2026-06-09 1h", "api", now=NOW, billable=False)
    return db


# --- numbering ---------------------------------------------------------------


def test_numbering_sequences_within_year():
    fmt = "{year}-{seq:03d}"
    issued = date(2026, 6, 9)
    assert next_number(fmt, set(), issued) == "2026-001"
    assert next_number(fmt, {"2026-001", "2026-002"}, issued) == "2026-003"
    assert next_number(fmt, {"2025-001"}, issued) == "2026-001"  # new year restarts


def test_numbering_bad_format():
    with pytest.raises(Exception, match="number_format"):
        next_number("{nope}", set(), date(2026, 6, 9))


# --- drafts ------------------------------------------------------------------


async def test_draft_rolls_up_days_and_rounds(seeded):
    draft = await svc.build_draft("acme", JUNE, SETTINGS)
    assert len(draft.lines) == 2  # two work days
    day1 = draft.lines[0]
    # 2h50m + 1h = 3h50m → rounds up to 4h at day level
    assert day1.billed_seconds == 4 * 3600
    assert day1.amount == Decimal("600.00")
    day2 = draft.lines[1]
    assert day2.billed_seconds == 2 * 3600  # non-billable hour excluded
    assert draft.subtotal == Decimal("900.00")
    assert draft.total == Decimal("900.00")


async def test_draft_requires_rate(db):
    await client_svc.create_client("Acme")  # no rate anywhere
    await project_svc.create_project("API", "acme")
    await entry_svc.log_entry("2026-06-08 1h", "api", now=NOW)
    with pytest.raises(TtdError, match="No hourly rate"):
        await svc.build_draft("acme", JUNE, Settings())


async def test_draft_empty_period_errors(seeded):
    with pytest.raises(TtdError, match="No uninvoiced billable entries"):
        await svc.build_draft("acme", month_period(date(2026, 1, 1)), SETTINGS)


# --- persistence -------------------------------------------------------------


async def test_persist_locks_entries_and_numbers(seeded):
    draft = await svc.build_draft("acme", JUNE, SETTINGS)
    invoice = await svc.persist_draft(draft, SETTINGS, now=NOW)
    assert invoice.number == "2026-001"

    rows = await entry_svc.list_entries()
    locked = [r for r in rows if r.entry.invoice_id is not None]
    assert len(locked) == 3  # the non-billable entry stays free

    # locked entries refuse edits
    with pytest.raises(Exception, match="invoice"):
        await entry_svc.edit_entry(str(locked[0].entry.id)[:8], now=NOW, note="x")

    # second invoice for same period has nothing to bill
    with pytest.raises(TtdError, match="No uninvoiced"):
        await svc.build_draft("acme", JUNE, SETTINGS)


async def test_number_collision_rejected(seeded):
    draft = await svc.build_draft("acme", JUNE, SETTINGS)
    await svc.persist_draft(draft, SETTINGS, now=NOW, number="INV-7")
    await entry_svc.log_entry("2026-06-09 30m", "api", now=NOW)
    draft2 = await svc.build_draft("acme", JUNE, SETTINGS)
    with pytest.raises(ConflictError, match="already exists"):
        await svc.persist_draft(draft2, SETTINGS, now=NOW, number="INV-7")


async def test_void_releases_entries(seeded):
    draft = await svc.build_draft("acme", JUNE, SETTINGS)
    invoice = await svc.persist_draft(draft, SETTINGS, now=NOW)
    await svc.mark_invoice(invoice.number, "void")

    rows = await entry_svc.list_entries()
    assert all(r.entry.invoice_id is None for r in rows)
    # numbers are never reused
    draft2 = await svc.build_draft("acme", JUNE, SETTINGS)
    invoice2 = await svc.persist_draft(draft2, SETTINGS, now=NOW)
    assert invoice2.number == "2026-002"
    # void is terminal
    with pytest.raises(ConflictError, match="void"):
        await svc.mark_invoice(invoice.number, "paid")


async def test_mark_sent_and_paid(seeded):
    draft = await svc.build_draft("acme", JUNE, SETTINGS)
    invoice = await svc.persist_draft(draft, SETTINGS, now=NOW)
    await svc.mark_invoice(invoice.number, "sent")
    await svc.mark_invoice(invoice.number, "paid")
    view = await svc.get_invoice(invoice.number)
    from ttd.storage.models import enum_value

    assert enum_value(view.invoice.status) == "paid"


async def test_tax_applied(seeded):
    taxed = SETTINGS.model_copy(update={"invoice": InvoiceConfig(tax_rate=Decimal("0.10"))})
    draft = await svc.build_draft("acme", JUNE, taxed)
    assert draft.tax == Decimal("90.00")
    assert draft.total == Decimal("990.00")


# --- rendering ---------------------------------------------------------------


async def test_markdown_snapshot(seeded):
    draft = await svc.build_draft("acme", JUNE, SETTINGS)
    invoice = await svc.persist_draft(draft, SETTINGS, now=NOW)
    view = await svc.get_invoice(invoice.number)
    md = render_markdown(view, SETTINGS)
    assert "# Invoice 2026-001" in md
    assert "**Bill to:** Acme" in md
    assert "$150.00" in md
    assert "$900.00" in md
    assert "API — 2 entries" in md
    assert "Payment due within 30 days" in md


async def test_pdf_smoke(seeded, tmp_path):
    from ttd.invoicing.pdf import render_pdf

    draft = await svc.build_draft("acme", JUNE, SETTINGS)
    invoice = await svc.persist_draft(draft, SETTINGS, now=NOW)
    view = await svc.get_invoice(invoice.number)
    out = render_pdf(view, SETTINGS, tmp_path / "invoice.pdf")
    data = out.read_bytes()
    assert data.startswith(b"%PDF-")
    assert len(data) > 1500
    assert b"/Page" in data
