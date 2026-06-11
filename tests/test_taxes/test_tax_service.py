"""Tax service: paid-time snapshots, quarter bucketing, and IRS payments."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from ttd.config.schema import BillingConfig, Settings, TaxConfig
from ttd.core.errors import ConflictError, NotFoundError, TtdError
from ttd.core.taxes import TaxQuarter
from ttd.services import clients as client_svc
from ttd.services import entries as entry_svc
from ttd.services import invoicing as invoice_svc
from ttd.services import projects as project_svc
from ttd.services import taxes as svc
from ttd.storage.models import InvoiceStatus, TaxPayment

NOW = datetime(2026, 6, 9, 15, 0)

SETTINGS = Settings(
    billing=BillingConfig(rounding="up", increment_minutes=15),
    tax=TaxConfig(set_aside_rate=Decimal("0.32")),
)
RERATED = SETTINGS.model_copy(update={"tax": TaxConfig(set_aside_rate=Decimal("0.25"))})


@pytest.fixture
async def invoice(db):
    """A persisted draft invoice: subtotal $900.00."""
    await client_svc.create_client("Acme", hourly_rate=Decimal("150"))
    await project_svc.create_project("API", "acme")
    await entry_svc.log_entry("2026-06-08 9am to 1pm", "api", now=NOW)
    await entry_svc.log_entry("2026-06-09 2h", "api", now=NOW)
    from ttd.reporting.periods import month_period

    draft = await invoice_svc.build_draft("acme", month_period(NOW.date()), SETTINGS)
    return await invoice_svc.persist_draft(draft, SETTINGS, now=NOW)


# --- paid-time snapshot -------------------------------------------------------


async def test_mark_paid_snapshots_rate_and_amount(invoice):
    marked = await invoice_svc.mark_invoice(
        invoice.number, "paid", paid_date=date(2026, 5, 10), set_aside_rate=Decimal("0.32")
    )
    assert marked.paid_date == date(2026, 5, 10)
    assert marked.set_aside_rate == Decimal("0.32")
    assert marked.set_aside == Decimal("288.00")


async def test_snapshot_frozen_across_rate_changes(invoice):
    await invoice_svc.mark_invoice(
        invoice.number, "paid", paid_date=date(2026, 5, 10), set_aside_rate=Decimal("0.32")
    )
    # the user later changes their configured rate — history must not move
    summaries = await svc.year_summary(2026, RERATED)
    q2 = summaries[1]
    assert q2.set_aside == Decimal("288.00")
    assert q2.income == Decimal("900.00")
    assert q2.invoice_count == 1


async def test_paid_date_default_and_quarter_bucketing(invoice):
    marked = await invoice_svc.mark_invoice(invoice.number, "paid", set_aside_rate=Decimal("0.32"))
    assert marked.paid_date == date.today()

    # re-marking paid is the correction path: moves the income across quarters
    await invoice_svc.mark_invoice(
        invoice.number, "paid", paid_date=date(2026, 7, 1), set_aside_rate=Decimal("0.32")
    )
    summaries = await svc.year_summary(2026, SETTINGS)
    assert summaries[2].invoice_count == 1  # Q3 (Jun-Aug)
    assert sum(s.invoice_count for s in summaries) == 1


async def test_paid_date_rejected_for_other_statuses(invoice):
    with pytest.raises(TtdError, match="paid"):
        await invoice_svc.mark_invoice(invoice.number, "sent", paid_date=date(2026, 5, 10))


async def test_sent_after_paid_clears_snapshot(invoice):
    await invoice_svc.mark_invoice(invoice.number, "paid", set_aside_rate=Decimal("0.32"))
    reverted = await invoice_svc.mark_invoice(invoice.number, "sent")
    assert reverted.paid_date is None
    assert reverted.set_aside_rate is None
    assert reverted.set_aside is None
    summaries = await svc.year_summary(2026, SETTINGS)
    assert all(s.invoice_count == 0 for s in summaries)


async def test_void_clears_snapshot_and_drops_from_summary(invoice):
    await invoice_svc.mark_invoice(
        invoice.number, "paid", paid_date=date(2026, 5, 10), set_aside_rate=Decimal("0.32")
    )
    voided = await invoice_svc.mark_invoice(invoice.number, "void")
    assert voided.set_aside is None
    summaries = await svc.year_summary(2026, SETTINGS)
    assert all(s.invoice_count == 0 for s in summaries)


# --- pre-feature fallback -----------------------------------------------------


async def test_pre_feature_paid_invoice_falls_back(invoice):
    # simulate an invoice marked paid before the feature existed: status only
    invoice.status = InvoiceStatus.PAID
    await invoice.save()

    paid_on, rate, set_aside = svc.paid_facts(invoice, Decimal("0.25"))
    assert paid_on == invoice.issued_date
    assert rate == Decimal("0.25")
    assert set_aside == Decimal("225.00")

    # issued 2026-06-09 → Q3, computed at the *current* configured rate
    summaries = await svc.year_summary(2026, RERATED)
    assert summaries[2].set_aside == Decimal("225.00")
    assert summaries[2].invoice_count == 1


# --- payments -----------------------------------------------------------------


async def test_record_and_sum_payments(invoice):
    await invoice_svc.mark_invoice(
        invoice.number, "paid", paid_date=date(2026, 5, 10), set_aside_rate=Decimal("0.32")
    )
    q2 = TaxQuarter(2026, 2)
    await svc.record_payment(q2, Decimal("100"), paid_on=date(2026, 6, 1))
    await svc.record_payment(q2, Decimal("88"), note="second EFTPS draft")

    summaries = await svc.year_summary(2026, SETTINGS)
    assert summaries[1].remitted == Decimal("188")
    assert summaries[1].balance == Decimal("100.00")
    assert summaries[1].payment_count == 2

    listed = await svc.list_payments(2026)
    assert [p.amount for p in listed] == [Decimal("100"), Decimal("88")]
    assert await svc.list_payments(2025) == []


async def test_payment_amount_must_be_positive(db):
    with pytest.raises(TtdError, match="positive"):
        await svc.record_payment(TaxQuarter(2026, 2), Decimal("0"))


async def test_remove_payment_by_prefix(db):
    a = TaxPayment(
        id=UUID("aaaaaaaa-0000-0000-0000-000000000001"),
        year=2026,
        quarter=2,
        amount=Decimal("100"),
        paid_on=date(2026, 6, 1),
        created_at=NOW,
    )
    b = TaxPayment(
        id=UUID("aaaaaaaa-0000-0000-0000-000000000002"),
        year=2026,
        quarter=3,
        amount=Decimal("50"),
        paid_on=date(2026, 9, 1),
        created_at=NOW,
    )
    await a.save()
    await b.save()

    with pytest.raises(ConflictError, match="ambiguous"):
        await svc.remove_payment("aaaaaaaa")
    with pytest.raises(NotFoundError):
        await svc.remove_payment("bbbbbbbb")

    removed = await svc.remove_payment("aaaaaaaa-0000-0000-0000-000000000001")
    assert removed.amount == Decimal("100")
    assert len(await svc.list_payments()) == 1
