"""Build, persist, and manage invoices."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

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
from ttd.storage.db import in_db_session
from ttd.storage.models import (
    Client,
    Entry,
    Expense,
    Invoice,
    InvoiceExpenseLine,
    InvoiceLine,
    InvoiceStatus,
    Project,
    enum_value,
    pk,
)

PAID_REFRESH_BLOCKED = (
    "Paid invoices can only be updated for description changes. "
    "Totals or line amounts would change — void and re-invoice to change billing."
)

BILLING_FIELDS = frozenset({"billed_seconds", "rate", "amount"})


def _line_description(project_name: str, entry_count: int, notes: list[str]) -> str:
    base = f"{project_name} — {entry_count} entr{'y' if entry_count == 1 else 'ies'}"
    if not notes:
        return base
    bullets = "\n".join(f"- {note}" for note in notes)
    return f"{base}\n{bullets}"


def flatten_line_description(text: str) -> str:
    """Single-line form for tables and terminals."""
    if not text:
        return ""
    lines = text.splitlines()
    if len(lines) == 1:
        return lines[0]
    return f"{lines[0]} · {' · '.join(lines[1:])}"


def _entry_sort_key(entry: Entry) -> tuple:
    started = entry.started_at or datetime.combine(entry.work_date, datetime.min.time())
    return (entry.work_date, started, entry.created_at)


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
class DraftExpenseLine:
    expense: Expense
    incurred_date: date
    description: str
    amount: Decimal


@dataclass
class Draft:
    client: Client
    period: Period
    lines: list[DraftLine]
    expense_lines: list[DraftExpenseLine]
    subtotal: Decimal
    expenses_subtotal: Decimal
    tax: Decimal
    total: Decimal
    number: str | None = None  # set when persisted


@dataclass
class InvoiceView:
    invoice: Invoice
    client: Client
    lines: list[InvoiceLine]
    expense_lines: list[InvoiceExpenseLine]
    project_names: dict


@dataclass
class LineDiff:
    project_id: UUID
    work_date: date
    project_name: str
    before: InvoiceLine | None
    after: DraftLine
    changed: frozenset[str]


@dataclass
class RefreshPreview:
    invoice: Invoice
    client: Client
    lines: list[LineDiff]
    before_subtotal: Decimal
    after_subtotal: Decimal
    before_tax: Decimal
    after_tax: Decimal
    before_total: Decimal
    after_total: Decimal
    before_expenses_subtotal: Decimal
    after_expenses_subtotal: Decimal
    after_expense_lines: list[DraftExpenseLine]
    totals_changed: bool
    billing_fields_changed: bool
    has_changes: bool
    can_apply: bool
    blocked_reason: str | None


def _line_key(project_id: UUID, work_date: date) -> tuple[UUID, date]:
    return (project_id, work_date)


def _draft_totals(
    lines: list[DraftLine], expense_lines: list["DraftExpenseLine"], tax_rate: Decimal
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    subtotal = sum((line.amount for line in lines), Decimal("0"))
    expenses_subtotal = sum((e.amount for e in expense_lines), Decimal("0"))
    tax = to_cents(subtotal * tax_rate)  # time only — expenses are untaxed
    total = subtotal + tax + expenses_subtotal
    return subtotal, expenses_subtotal, tax, total


def _line_changed(before: InvoiceLine | None, after: DraftLine) -> frozenset[str]:
    if before is None:
        return frozenset({"description", "billed_seconds", "rate", "amount"})
    changed: set[str] = set()
    if before.description != after.description:
        changed.add("description")
    if before.billed_seconds != after.billed_seconds:
        changed.add("billed_seconds")
    if before.rate != after.rate:
        changed.add("rate")
    if before.amount != after.amount:
        changed.add("amount")
    return frozenset(changed)


async def _build_lines_from_entries(
    entries: list[Entry],
    client: Client,
    projects: dict[UUID, Project],
    settings: Settings,
) -> list[DraftLine]:
    entries = sorted(entries, key=_entry_sort_key)
    facts = [
        EntryFacts(e.project_id, pk(client), e.work_date, e.seconds, e.billable, e.note)
        for e in entries
    ]
    cells = rollup_days(facts)

    lines: list[DraftLine] = []
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
                description=_line_description(project.name, cell.entry_count, cell.notes),
                entry_ids=entry_ids,
            )
        )
    return lines


@in_db_session
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
    expenses = [
        e
        for e in await Expense.all()
        if e.project_id in projects
        and e.invoice_id is None
        and period.start <= e.incurred_date <= period.end
    ]
    if not entries and not expenses:
        raise TtdError(
            f"No uninvoiced billable entries or expenses for '{client_slug}' in {period.label}"
        )

    lines = await _build_lines_from_entries(entries, client, projects, settings)
    expense_lines = [
        DraftExpenseLine(e, e.incurred_date, e.description, e.amount)
        for e in sorted(expenses, key=lambda e: (e.incurred_date, e.created_at))
    ]
    subtotal, expenses_subtotal, tax, total = _draft_totals(
        lines, expense_lines, settings.invoice.tax_rate
    )
    return Draft(
        client=client,
        period=period,
        lines=lines,
        expense_lines=expense_lines,
        subtotal=subtotal,
        expenses_subtotal=expenses_subtotal,
        tax=tax,
        total=total,
    )


@in_db_session
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
        expenses_subtotal=draft.expenses_subtotal,
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
        for eline in draft.expense_lines:
            await InvoiceExpenseLine(
                id=uuid4(),
                invoice_id=pk(invoice),
                expense_id=pk(eline.expense),
                incurred_date=eline.incurred_date,
                description=eline.description,
                amount=eline.amount,
            ).save()
            expense = await Expense.get_or_none(pk(eline.expense))
            if expense is not None:
                expense.invoice_id = invoice.id
                await expense.save()
    draft.number = final_number
    return invoice


@in_db_session
async def get_invoice(number: str) -> InvoiceView:
    invoice = await Invoice.where(lambda i: i.number == number).first()
    if invoice is None:
        raise NotFoundError(f"No invoice '{number}'")
    client = await Client.get_or_none(invoice.client_id)
    assert client is not None
    lines = await InvoiceLine.where(lambda li: li.invoice_id == invoice.id).all()
    lines.sort(key=lambda li: (li.work_date, li.description))
    expense_lines = await InvoiceExpenseLine.where(lambda li: li.invoice_id == invoice.id).all()
    expense_lines.sort(key=lambda li: (li.incurred_date, li.description))
    names = {pk(p): p.name for p in await Project.all()}
    return InvoiceView(invoice, client, lines, expense_lines, names)


@in_db_session
async def list_invoices() -> list[tuple[Invoice, Client]]:
    invoices = await Invoice.all()
    clients = {c.id: c for c in await Client.all()}
    return sorted(
        ((i, clients[i.client_id]) for i in invoices),
        key=lambda pair: (pair[0].issued_date, pair[0].number),
        reverse=True,
    )


VALID_MARKS = ("sent", "paid", "void")


@in_db_session
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
            for expense in await Expense.where(lambda e: e.invoice_id == invoice.id).all():
                expense.invoice_id = None
                await expense.save()
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


@in_db_session
async def preview_refresh(number: str, settings: Settings) -> RefreshPreview:
    view = await get_invoice(number)
    invoice, client = view.invoice, view.client
    status = enum_value(invoice.status)
    if status == "void":
        raise ConflictError(f"Invoice {number} is void and can't be refreshed")

    entries = await Entry.where(lambda e: e.invoice_id == invoice.id).all()
    if not entries and not view.lines and not view.expense_lines:
        raise TtdError(f"Invoice {number} has no linked entries or expenses")

    project_ids = {e.project_id for e in entries}
    projects = {pk(p): p for p in await Project.all() if pk(p) in project_ids}
    after_lines = await _build_lines_from_entries(entries, client, projects, settings)

    before_by_key = {_line_key(li.project_id, li.work_date): li for li in view.lines}
    after_by_key = {_line_key(pk(line.project), line.work_date): line for line in after_lines}

    all_keys = sorted(set(before_by_key) | set(after_by_key), key=lambda k: (k[1], str(k[0])))

    diffs: list[LineDiff] = []
    billing_fields_changed = False
    for key in all_keys:
        project_id, work_date = key
        before = before_by_key.get(key)
        after = after_by_key.get(key)
        project_name = view.project_names.get(project_id, projects[project_id].name)

        if after is None:
            assert before is not None
            billing_fields_changed = True
            diffs.append(
                LineDiff(
                    project_id=project_id,
                    work_date=work_date,
                    project_name=project_name,
                    before=before,
                    after=DraftLine(
                        project=projects[project_id],
                        work_date=work_date,
                        raw_seconds=before.billed_seconds,
                        billed_seconds=0,
                        rate=before.rate,
                        amount=Decimal("0"),
                        description="",
                        entry_ids=[],
                    ),
                    changed=frozenset({"description", "billed_seconds", "rate", "amount"}),
                )
            )
            continue

        changed = _line_changed(before, after)
        if changed & BILLING_FIELDS:
            billing_fields_changed = True
        diffs.append(
            LineDiff(
                project_id=project_id,
                work_date=work_date,
                project_name=project_name,
                before=before,
                after=after,
                changed=changed,
            )
        )

    before_subtotal = invoice.subtotal
    before_tax = invoice.tax
    before_total = invoice.total
    before_expenses_subtotal = invoice.expenses_subtotal

    linked_expenses = await Expense.where(lambda e: e.invoice_id == invoice.id).all()
    after_expense_lines = [
        DraftExpenseLine(e, e.incurred_date, e.description, e.amount)
        for e in sorted(linked_expenses, key=lambda e: (e.incurred_date, e.created_at))
    ]
    after_subtotal, after_expenses, after_tax, after_total = _draft_totals(
        after_lines, after_expense_lines, settings.invoice.tax_rate
    )

    totals_changed = (
        before_subtotal != after_subtotal
        or before_tax != after_tax
        or before_total != after_total
        or invoice.expenses_subtotal != after_expenses
    )
    has_changes = any(d.changed for d in diffs) or totals_changed

    description_only = has_changes and not totals_changed and not billing_fields_changed
    can_apply = has_changes and (
        status in ("draft", "sent") or (status == "paid" and description_only)
    )
    blocked_reason: str | None = None
    if status == "paid" and has_changes and not description_only:
        blocked_reason = PAID_REFRESH_BLOCKED

    return RefreshPreview(
        invoice=invoice,
        client=client,
        lines=diffs,
        before_subtotal=before_subtotal,
        after_subtotal=after_subtotal,
        before_tax=before_tax,
        after_tax=after_tax,
        before_total=before_total,
        after_total=after_total,
        before_expenses_subtotal=before_expenses_subtotal,
        after_expenses_subtotal=after_expenses,
        after_expense_lines=after_expense_lines,
        totals_changed=totals_changed,
        billing_fields_changed=billing_fields_changed,
        has_changes=has_changes,
        can_apply=can_apply,
        blocked_reason=blocked_reason,
    )


@in_db_session
async def apply_refresh(number: str, preview: RefreshPreview, settings: Settings) -> Invoice:
    status = enum_value(preview.invoice.status)
    if status == "void":
        raise ConflictError(f"Invoice {number} is void and can't be refreshed")
    if not preview.can_apply:
        if preview.blocked_reason:
            raise TtdError(preview.blocked_reason)
        raise TtdError("No changes to apply")

    fresh = await preview_refresh(number, settings)
    if not fresh.can_apply:
        if fresh.blocked_reason:
            raise TtdError(fresh.blocked_reason)
        raise TtdError("Invoice changed since preview — refresh again")

    invoice = fresh.invoice
    status = enum_value(invoice.status)

    async with transaction():
        if status == "paid":
            before_by_key = {
                _line_key(li.project_id, li.work_date): li
                for li in await InvoiceLine.where(lambda li: li.invoice_id == invoice.id).all()
            }
            for diff in fresh.lines:
                if "description" not in diff.changed:
                    continue
                stored = before_by_key.get(_line_key(diff.project_id, diff.work_date))
                if stored is None:
                    continue
                stored.description = diff.after.description
                await stored.save()
        else:
            stored_lines = await InvoiceLine.where(lambda li: li.invoice_id == invoice.id).all()
            stored_by_key = {_line_key(li.project_id, li.work_date): li for li in stored_lines}
            seen_keys: set[tuple[UUID, date]] = set()

            for diff in fresh.lines:
                key = _line_key(diff.project_id, diff.work_date)
                after = diff.after
                if after.billed_seconds == 0 and diff.before is not None:
                    continue
                seen_keys.add(key)
                if not diff.changed:
                    continue
                if key in stored_by_key:
                    line = stored_by_key[key]
                    line.description = after.description
                    line.billed_seconds = after.billed_seconds
                    line.rate = after.rate
                    line.amount = after.amount
                    await line.save()
                else:
                    await InvoiceLine(
                        id=uuid4(),
                        invoice_id=pk(invoice),
                        project_id=diff.project_id,
                        work_date=diff.work_date,
                        billed_seconds=after.billed_seconds,
                        rate=after.rate,
                        amount=after.amount,
                        description=after.description,
                    ).save()

            for key, line in stored_by_key.items():
                if key not in seen_keys:
                    await line.delete()

            for stale in await InvoiceExpenseLine.where(
                lambda li: li.invoice_id == invoice.id
            ).all():
                await stale.delete()
            for eline in fresh.after_expense_lines:
                await InvoiceExpenseLine(
                    id=uuid4(),
                    invoice_id=pk(invoice),
                    expense_id=pk(eline.expense),
                    incurred_date=eline.incurred_date,
                    description=eline.description,
                    amount=eline.amount,
                ).save()
            invoice.expenses_subtotal = fresh.after_expenses_subtotal

            invoice.subtotal = fresh.after_subtotal
            invoice.tax_rate = settings.invoice.tax_rate
            invoice.tax = fresh.after_tax
            invoice.total = fresh.after_total
            await invoice.save()

    updated = await Invoice.where(lambda i: i.number == number).first()
    assert updated is not None
    return updated
