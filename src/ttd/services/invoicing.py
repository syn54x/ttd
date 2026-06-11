"""Build, persist, and manage invoices."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from ferro import transaction

from ttd.config.schema import Settings
from ttd.core.errors import ConflictError, NotFoundError, TtdError
from ttd.core.money import to_cents
from ttd.core.rollup import EntryFacts, rollup_days
from ttd.core.taxes import compute_set_aside
from ttd.invoicing.numbering import next_number
from ttd.reporting.periods import Period
from ttd.services.clients import get_client
from ttd.services.projects import effective_rate
from ttd.storage.models import (
    Client,
    Entry,
    Invoice,
    InvoiceLine,
    InvoiceStatus,
    Project,
    enum_value,
    pk,
)


@dataclass
class DraftLine:
    project: Project
    work_date: date
    raw_seconds: int
    billed_seconds: int
    rate: Decimal
    amount: Decimal
    description: str
    entry_ids: list


@dataclass
class Draft:
    client: Client
    period: Period
    lines: list[DraftLine]
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    number: str | None = None  # set when persisted


@dataclass
class InvoiceView:
    invoice: Invoice
    client: Client
    lines: list[InvoiceLine]
    project_names: dict


async def build_draft(client_slug: str, period: Period, settings: Settings) -> Draft:
    client = await get_client(client_slug)
    projects = {pk(p): p for p in await Project.where(lambda p: p.client_id == client.id).all()}
    if not projects:
        raise TtdError(f"Client '{client_slug}' has no projects")

    entries = [
        e
        for e in await Entry.all()
        if e.project_id in projects
        and e.invoice_id is None
        and e.billable
        and period.start <= e.work_date <= period.end
    ]
    if not entries:
        raise TtdError(f"No uninvoiced billable entries for '{client_slug}' in {period.label}")

    facts = [
        EntryFacts(e.project_id, pk(client), e.work_date, e.seconds, e.billable) for e in entries
    ]
    cells = rollup_days(facts)

    lines: list[DraftLine] = []
    subtotal = Decimal("0")
    for cell in cells:
        project = projects[cell.project_id]
        rate = await effective_rate(project)
        if rate is None:
            rate = settings.business.default_hourly_rate
        if rate is None:
            raise TtdError(
                f"No hourly rate for project '{project.slug}' — set one on the project, "
                "the client, or [business].default_hourly_rate"
            )
        billed = cell.billed_seconds(settings.billing)
        if billed == 0:
            continue
        amount = to_cents(Decimal(billed) / Decimal(3600) * rate)
        entry_ids = [
            pk(e)
            for e in entries
            if e.project_id == cell.project_id and e.work_date == cell.work_date
        ]
        lines.append(
            DraftLine(
                project=project,
                work_date=cell.work_date,
                raw_seconds=cell.seconds,
                billed_seconds=billed,
                rate=rate,
                amount=amount,
                description=f"{project.name} — {cell.entry_count} "
                f"entr{'y' if cell.entry_count == 1 else 'ies'}",
                entry_ids=entry_ids,
            )
        )
        subtotal += amount

    tax = to_cents(subtotal * settings.invoice.tax_rate)
    return Draft(
        client=client,
        period=period,
        lines=lines,
        subtotal=subtotal,
        tax=tax,
        total=subtotal + tax,
    )


async def persist_draft(
    draft: Draft, settings: Settings, *, number: str | None = None, now: datetime | None = None
) -> Invoice:
    now = now or datetime.now()
    issued = now.date()
    existing = {i.number for i in await Invoice.all()}
    if number is not None and number in existing:
        raise ConflictError(f"Invoice number '{number}' already exists")
    final_number = number or next_number(settings.invoice.number_format, existing, issued)

    invoice = Invoice(
        id=uuid4(),
        number=final_number,
        client_id=pk(draft.client),
        period_start=draft.period.start,
        period_end=draft.period.end,
        issued_date=issued,
        due_date=issued + timedelta(days=settings.invoice.payment_terms_days),
        currency=draft.client.currency,
        subtotal=draft.subtotal,
        tax_rate=settings.invoice.tax_rate,
        tax=draft.tax,
        total=draft.total,
        status=InvoiceStatus.DRAFT,
        created_at=now,
    )
    async with transaction():
        await invoice.save()
        for line in draft.lines:
            await InvoiceLine(
                id=uuid4(),
                invoice_id=pk(invoice),
                project_id=pk(line.project),
                work_date=line.work_date,
                billed_seconds=line.billed_seconds,
                rate=line.rate,
                amount=line.amount,
                description=line.description,
            ).save()
            for entry_id in line.entry_ids:
                entry = await Entry.get_or_none(entry_id)
                if entry is not None:
                    entry.invoice_id = invoice.id
                    await entry.save()
    draft.number = final_number
    return invoice


async def get_invoice(number: str) -> InvoiceView:
    invoice = await Invoice.where(lambda i: i.number == number).first()
    if invoice is None:
        raise NotFoundError(f"No invoice '{number}'")
    client = await Client.get_or_none(invoice.client_id)
    assert client is not None
    lines = await InvoiceLine.where(lambda li: li.invoice_id == invoice.id).all()
    lines.sort(key=lambda li: (li.work_date, li.description))
    names = {pk(p): p.name for p in await Project.all()}
    return InvoiceView(invoice, client, lines, names)


async def list_invoices() -> list[tuple[Invoice, Client]]:
    invoices = await Invoice.all()
    clients = {c.id: c for c in await Client.all()}
    return sorted(
        ((i, clients[i.client_id]) for i in invoices),
        key=lambda pair: (pair[0].issued_date, pair[0].number),
        reverse=True,
    )


VALID_MARKS = ("sent", "paid", "void")


async def mark_invoice(
    number: str,
    status: str,
    *,
    paid_date: date | None = None,
    set_aside_rate: Decimal = Decimal("0"),
) -> Invoice:
    if status not in VALID_MARKS:
        raise TtdError(f"Status must be one of {', '.join(VALID_MARKS)} (got '{status}')")
    if paid_date is not None and status != "paid":
        raise TtdError("A paid date only applies when marking paid")
    view = await get_invoice(number)
    invoice = view.invoice
    current = enum_value(invoice.status)
    if current == "void":
        raise ConflictError(f"Invoice {number} is void and can't change status")
    if status == "void":
        async with transaction():
            for entry in await Entry.where(lambda e: e.invoice_id == invoice.id).all():
                entry.invoice_id = None
                await entry.save()
            invoice.status = InvoiceStatus.VOID
            _clear_paid_snapshot(invoice)
            await invoice.save()
    else:
        invoice.status = InvoiceStatus(status)
        if status == "paid":
            # Snapshot at paid-time; re-marking paid re-snapshots (the
            # documented correction path for backfilled dates or rates).
            invoice.paid_date = paid_date or date.today()
            invoice.set_aside_rate = set_aside_rate
            invoice.set_aside = compute_set_aside(invoice.subtotal, set_aside_rate)
        else:
            _clear_paid_snapshot(invoice)
        await invoice.save()
    return invoice


def _clear_paid_snapshot(invoice: Invoice) -> None:
    invoice.paid_date = None
    invoice.set_aside_rate = None
    invoice.set_aside = None
