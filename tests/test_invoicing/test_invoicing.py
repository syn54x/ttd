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
from ttd.services.invoicing import PAID_REFRESH_BLOCKED
from ttd.storage.models import InvoiceLine

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


async def test_draft_line_includes_entry_notes(db):
    await client_svc.create_client("Acme", hourly_rate=Decimal("150"))
    await project_svc.create_project("API", "acme")
    await entry_svc.log_entry("2026-06-08 9am to 11am", "api", now=NOW, note="API design")
    await entry_svc.log_entry("2026-06-08 1pm to 2pm", "api", now=NOW, note="Code review")
    draft = await svc.build_draft("acme", JUNE, SETTINGS)
    assert len(draft.lines) == 1
    assert draft.lines[0].description == "API — 2 entries\n- API design\n- Code review"


async def test_draft_line_without_notes_unchanged(seeded):
    draft = await svc.build_draft("acme", JUNE, SETTINGS)
    assert draft.lines[0].description == "API — 2 entries"


def test_flatten_line_description_shows_notes():
    text = "API — 2 entries\n- Design\n- Review"
    assert svc.flatten_line_description(text) == "API — 2 entries · - Design · - Review"
    assert svc.flatten_line_description("API — 2 entries") == "API — 2 entries"


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
    sent = await svc.mark_invoice(invoice.number, "sent")
    assert sent.paid_date is None and sent.set_aside is None
    await svc.mark_invoice(
        invoice.number, "paid", paid_date=date(2026, 6, 20), set_aside_rate=Decimal("0.32")
    )
    view = await svc.get_invoice(invoice.number)
    from ttd.storage.models import enum_value

    assert enum_value(view.invoice.status) == "paid"
    assert view.invoice.paid_date == date(2026, 6, 20)
    assert view.invoice.set_aside_rate == Decimal("0.32")
    assert view.invoice.set_aside == Decimal("288.00")  # 32% of the 900.00 subtotal


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


async def test_markdown_renders_multiline_notes(db):
    await client_svc.create_client("Acme", hourly_rate=Decimal("150"))
    await project_svc.create_project("API", "acme")
    await entry_svc.log_entry("2026-06-08 9am to 11am", "api", now=NOW, note="Design")
    await entry_svc.log_entry("2026-06-08 1pm to 2pm", "api", now=NOW, note="Review")
    draft = await svc.build_draft("acme", JUNE, SETTINGS)
    invoice = await svc.persist_draft(draft, SETTINGS, now=NOW)
    view = await svc.get_invoice(invoice.number)
    md = render_markdown(view, SETTINGS)
    assert "API — 2 entries\n- Design\n- Review" in md


async def test_set_aside_never_reaches_client_renders(seeded, tmp_path):
    """The tax set-aside is internal — it must not leak onto client invoices."""
    from ttd.invoicing.pdf import render_pdf

    draft = await svc.build_draft("acme", JUNE, SETTINGS)
    invoice = await svc.persist_draft(draft, SETTINGS, now=NOW)
    await svc.mark_invoice(invoice.number, "paid", set_aside_rate=Decimal("0.32"))
    view = await svc.get_invoice(invoice.number)
    md = render_markdown(view, SETTINGS)
    assert "set aside" not in md.lower()
    render_pdf(view, SETTINGS, tmp_path / "invoice.pdf")  # must not crash on snapshot fields


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


async def test_pdf_with_entry_notes(db, tmp_path):
    from ttd.invoicing.pdf import render_pdf

    await client_svc.create_client("Acme", hourly_rate=Decimal("150"))
    await project_svc.create_project("API", "acme")
    await entry_svc.log_entry("2026-06-08 9am to 11am", "api", now=NOW, note="Design work")
    draft = await svc.build_draft("acme", JUNE, SETTINGS)
    invoice = await svc.persist_draft(draft, SETTINGS, now=NOW)
    view = await svc.get_invoice(invoice.number)
    out = render_pdf(view, SETTINGS, tmp_path / "invoice-with-notes.pdf")
    assert out.read_bytes().startswith(b"%PDF-")


# --- refresh ---------------------------------------------------------------


async def _legacy_line_descriptions(invoice_id) -> None:
    """Strip notes from stored lines to simulate pre-notes invoices."""
    for line in await InvoiceLine.where(lambda li: li.invoice_id == invoice_id).all():
        line.description = line.description.splitlines()[0]
        await line.save()


async def test_refresh_updates_descriptions_from_notes(db):
    await client_svc.create_client("Acme", hourly_rate=Decimal("150"))
    await project_svc.create_project("API", "acme")
    await entry_svc.log_entry("2026-06-08 9am to 11am", "api", now=NOW, note="Design")
    await entry_svc.log_entry("2026-06-08 1pm to 2pm", "api", now=NOW, note="Review")
    draft = await svc.build_draft("acme", JUNE, SETTINGS)
    invoice = await svc.persist_draft(draft, SETTINGS, now=NOW)
    await _legacy_line_descriptions(invoice.id)

    preview = await svc.preview_refresh(invoice.number, SETTINGS)
    expected = "API — 2 entries\n- Design\n- Review"
    assert preview.has_changes and preview.can_apply
    assert preview.lines[0].changed == frozenset({"description"})
    assert preview.lines[0].after.description == expected

    await svc.apply_refresh(invoice.number, preview, SETTINGS)
    view = await svc.get_invoice(invoice.number)
    assert view.lines[0].description == expected


async def test_refresh_recalcs_totals_when_rate_changes(seeded):
    draft = await svc.build_draft("acme", JUNE, SETTINGS)
    invoice = await svc.persist_draft(draft, SETTINGS, now=NOW)
    await client_svc.update_client("acme", hourly_rate=Decimal("200"))

    preview = await svc.preview_refresh(invoice.number, SETTINGS)
    assert preview.totals_changed and preview.can_apply
    assert preview.after_total > preview.before_total

    await svc.apply_refresh(invoice.number, preview, SETTINGS)
    view = await svc.get_invoice(invoice.number)
    assert view.invoice.total == preview.after_total


async def test_refresh_noop(seeded):
    draft = await svc.build_draft("acme", JUNE, SETTINGS)
    invoice = await svc.persist_draft(draft, SETTINGS, now=NOW)
    preview = await svc.preview_refresh(invoice.number, SETTINGS)
    assert not preview.has_changes
    assert not preview.can_apply


async def test_refresh_void_rejected(seeded):
    draft = await svc.build_draft("acme", JUNE, SETTINGS)
    invoice = await svc.persist_draft(draft, SETTINGS, now=NOW)
    await svc.mark_invoice(invoice.number, "void")
    with pytest.raises(ConflictError, match="void"):
        await svc.preview_refresh(invoice.number, SETTINGS)


async def test_refresh_paid_description_only(db):
    await client_svc.create_client("Acme", hourly_rate=Decimal("150"))
    await project_svc.create_project("API", "acme")
    await entry_svc.log_entry("2026-06-08 9am to 11am", "api", now=NOW, note="Design")
    draft = await svc.build_draft("acme", JUNE, SETTINGS)
    invoice = await svc.persist_draft(draft, SETTINGS, now=NOW)
    await svc.mark_invoice(invoice.number, "paid", set_aside_rate=Decimal("0.32"))
    await _legacy_line_descriptions(invoice.id)
    before = await svc.get_invoice(invoice.number)

    preview = await svc.preview_refresh(invoice.number, SETTINGS)
    assert preview.can_apply and not preview.totals_changed
    await svc.apply_refresh(invoice.number, preview, SETTINGS)

    after = await svc.get_invoice(invoice.number)
    assert after.invoice.total == before.invoice.total
    assert after.invoice.set_aside == before.invoice.set_aside
    assert after.lines[0].description == "API — 1 entry\n- Design"


async def test_refresh_paid_blocks_billing_changes(seeded):
    draft = await svc.build_draft("acme", JUNE, SETTINGS)
    invoice = await svc.persist_draft(draft, SETTINGS, now=NOW)
    await svc.mark_invoice(invoice.number, "paid")
    await client_svc.update_client("acme", hourly_rate=Decimal("200"))

    preview = await svc.preview_refresh(invoice.number, SETTINGS)
    assert preview.has_changes
    assert not preview.can_apply
    assert preview.blocked_reason == PAID_REFRESH_BLOCKED
    with pytest.raises(TtdError, match="Paid invoices"):
        await svc.apply_refresh(invoice.number, preview, SETTINGS)


async def test_refresh_apply_stale_rejected(seeded):
    draft = await svc.build_draft("acme", JUNE, SETTINGS)
    invoice = await svc.persist_draft(draft, SETTINGS, now=NOW)
    await client_svc.update_client("acme", hourly_rate=Decimal("200"))
    preview = await svc.preview_refresh(invoice.number, SETTINGS)
    assert preview.can_apply

    await svc.mark_invoice(invoice.number, "paid")
    with pytest.raises(TtdError, match="Paid invoices"):
        await svc.apply_refresh(invoice.number, preview, SETTINGS)
