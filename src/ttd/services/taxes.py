"""Tax set-aside summaries and IRS estimated-tax payments.

Amounts are summed naively across currencies and formatted by surfaces in
``settings.business.currency`` — same single-currency assumption the reports
make. IRS remittances are USD in practice.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from ttd.config.schema import Settings
from ttd.core.errors import ConflictError, NotFoundError, TtdError
from ttd.core.taxes import TaxQuarter, compute_set_aside, quarters_of
from ttd.storage.db import in_db_session
from ttd.storage.models import Invoice, InvoiceStatus, TaxPayment, enum_value, pk


@dataclass
class QuarterSummary:
    quarter: TaxQuarter
    income: Decimal  # paid subtotals received in the quarter (set-aside base)
    set_aside: Decimal
    remitted: Decimal
    balance: Decimal  # set_aside - remitted
    invoice_count: int
    payment_count: int


@dataclass
class InvoiceEstimate:
    """Estimated tax and take-home for one invoice.

    Both are based on the subtotal — invoice sales tax is pass-through money,
    not income.
    """

    set_aside: Decimal
    take_home: Decimal  # subtotal - set_aside


def estimate_invoice(invoice: Invoice, fallback_rate: Decimal) -> InvoiceEstimate | None:
    """Per-invoice set-aside estimate, or ``None`` when there is nothing to show.

    Paid invoices use their frozen snapshot; everything else previews at the
    current configured rate. Void invoices and 0% rates yield ``None`` — for
    those rows the feature is off, not zero.
    """
    status = enum_value(invoice.status)
    if status == InvoiceStatus.VOID.value:
        return None
    if (
        status == InvoiceStatus.PAID.value
        and invoice.set_aside is not None
        and invoice.set_aside_rate is not None
    ):
        if invoice.set_aside_rate == 0:
            return None
        return InvoiceEstimate(invoice.set_aside, invoice.subtotal - invoice.set_aside)
    if fallback_rate <= 0:
        return None
    set_aside = compute_set_aside(invoice.subtotal, fallback_rate)
    return InvoiceEstimate(set_aside, invoice.subtotal - set_aside)


def paid_facts(invoice: Invoice, fallback_rate: Decimal) -> tuple[date, Decimal, Decimal]:
    """``(paid_date, rate, set_aside)`` for a paid invoice.

    Invoices paid before the feature existed have no snapshot; they fall back
    to ``issued_date`` and the current configured rate. Re-marking paid with
    an explicit date makes the snapshot permanent.
    """
    paid = invoice.paid_date or invoice.issued_date
    if invoice.set_aside is not None and invoice.set_aside_rate is not None:
        return paid, invoice.set_aside_rate, invoice.set_aside
    return paid, fallback_rate, compute_set_aside(invoice.subtotal, fallback_rate)


@in_db_session
async def year_summary(year: int, settings: Settings) -> list[QuarterSummary]:
    """Exactly four ``QuarterSummary`` rows for ``year`` (zeros included)."""
    fallback_rate = settings.tax.set_aside_rate
    buckets: dict[int, list[tuple[Decimal, Decimal]]] = {1: [], 2: [], 3: [], 4: []}
    for invoice in await Invoice.all():
        if enum_value(invoice.status) != InvoiceStatus.PAID.value:
            continue
        paid, _rate, set_aside = paid_facts(invoice, fallback_rate)
        if paid.year != year:
            continue
        buckets[TaxQuarter.from_date(paid).quarter].append((invoice.subtotal, set_aside))

    payments = await TaxPayment.where(lambda p: p.year == year).all()
    remitted: dict[int, list[Decimal]] = {1: [], 2: [], 3: [], 4: []}
    for payment in payments:
        remitted[payment.quarter].append(payment.amount)

    summaries = []
    for quarter in quarters_of(year):
        invoices = buckets[quarter.quarter]
        set_aside = sum((s for _, s in invoices), Decimal("0"))
        paid_out = sum(remitted[quarter.quarter], Decimal("0"))
        summaries.append(
            QuarterSummary(
                quarter=quarter,
                income=sum((sub for sub, _ in invoices), Decimal("0")),
                set_aside=set_aside,
                remitted=paid_out,
                balance=set_aside - paid_out,
                invoice_count=len(invoices),
                payment_count=len(remitted[quarter.quarter]),
            )
        )
    return summaries


@in_db_session
async def record_payment(
    quarter: TaxQuarter,
    amount: Decimal,
    *,
    paid_on: date | None = None,
    note: str = "",
) -> TaxPayment:
    if amount <= 0:
        raise TtdError(f"Payment amount must be positive (got {amount})")
    payment = TaxPayment(
        id=uuid4(),
        year=quarter.year,
        quarter=quarter.quarter,
        amount=amount,
        paid_on=paid_on or date.today(),
        note=note,
        created_at=datetime.now(),
    )
    await payment.save()
    return payment


@in_db_session
async def list_payments(year: int | None = None) -> list[TaxPayment]:
    if year is None:
        payments = await TaxPayment.all()
    else:
        payments = await TaxPayment.where(lambda p: p.year == year).all()
    return sorted(payments, key=lambda p: (p.year, p.quarter, p.paid_on))


@in_db_session
async def remove_payment(id_prefix: str) -> TaxPayment:
    matches = [p for p in await TaxPayment.all() if str(pk(p)).startswith(id_prefix.lower())]
    if not matches:
        raise NotFoundError(f"No tax payment with id starting '{id_prefix}'")
    if len(matches) > 1:
        raise ConflictError(f"Id prefix '{id_prefix}' is ambiguous ({len(matches)} matches)")
    payment = matches[0]
    await TaxPayment.where(lambda p: p.id == payment.id).delete()
    return payment
