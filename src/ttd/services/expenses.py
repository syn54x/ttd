"""Logging and managing billable expenses (client chargebacks)."""

import base64
import mimetypes
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from ttd.core.errors import ConflictError, InvoicedExpenseError, NotFoundError, TtdError
from ttd.services.projects import get_project
from ttd.storage.db import in_db_session
from ttd.storage.models import Client, Expense, ExpenseReceipt, Project, pk


@dataclass
class ExpenseView:
    expense: Expense
    project: Project
    client: Client
    has_receipt: bool


@dataclass
class ExpenseSuggestion:
    description: str
    amount: Decimal


@in_db_session
async def add_expense(
    project_slug: str,
    description: str,
    amount: Decimal,
    *,
    client_slug: str | None = None,
    incurred_date: date | None = None,
    note: str = "",
) -> Expense:
    project = await get_project(project_slug, client_slug)
    stamp = datetime.now()
    expense = Expense(
        id=uuid4(),
        project_id=pk(project),
        incurred_date=incurred_date or date.today(),
        description=description.strip(),
        amount=amount,
        note=note,
        created_at=stamp,
        updated_at=stamp,
    )
    await expense.save()
    return expense


@in_db_session
async def find_expense(uid_prefix: str) -> Expense:
    needle = uid_prefix.lower().replace("-", "")
    if not needle:
        raise NotFoundError("Empty expense id")
    matches = [e for e in await Expense.all() if str(e.id).replace("-", "").startswith(needle)]
    if not matches:
        raise NotFoundError(f"No expense matching '{uid_prefix}'")
    if len(matches) > 1:
        raise ConflictError(f"'{uid_prefix}' matches {len(matches)} expenses — use more characters")
    return matches[0]


@in_db_session
async def list_expenses(
    *,
    project_slug: str | None = None,
    client_slug: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    unbilled_only: bool = False,
) -> list[ExpenseView]:
    expenses = await Expense.all()
    projects = {p.id: p for p in await Project.all()}
    clients = {c.id: c for c in await Client.all()}
    receipted = {r.expense_id for r in await ExpenseReceipt.all()}

    if project_slug is not None:
        project = await get_project(project_slug, client_slug)
        expenses = [e for e in expenses if e.project_id == project.id]
    elif client_slug is not None:
        wanted = {
            p.id
            for p in projects.values()
            if (c := clients.get(p.client_id)) is not None and c.slug == client_slug
        }
        expenses = [e for e in expenses if e.project_id in wanted]
    if date_from is not None:
        expenses = [e for e in expenses if e.incurred_date >= date_from]
    if date_to is not None:
        expenses = [e for e in expenses if e.incurred_date <= date_to]
    if unbilled_only:
        expenses = [e for e in expenses if e.invoice_id is None]

    rows: list[ExpenseView] = []
    for e in sorted(expenses, key=lambda e: (e.incurred_date, e.created_at)):
        project = projects.get(e.project_id)
        if project is None:
            continue
        client = clients.get(project.client_id)
        if client is None:
            continue
        rows.append(ExpenseView(e, project, client, e.id in receipted))
    return rows


def _ensure_unlocked(expense: Expense) -> None:
    if expense.invoice_id is not None:
        raise InvoicedExpenseError(
            f"Expense {str(expense.id)[:8]} is on an invoice — void the invoice first"
        )


@in_db_session
async def edit_expense(
    uid_prefix: str,
    *,
    amount: Decimal | None = None,
    description: str | None = None,
    note: str | None = None,
    incurred_date: date | None = None,
    project_slug: str | None = None,
    client_slug: str | None = None,
) -> Expense:
    expense = await find_expense(uid_prefix)
    _ensure_unlocked(expense)
    if amount is not None:
        expense.amount = amount
    if description is not None:
        expense.description = description.strip()
    if note is not None:
        expense.note = note
    if incurred_date is not None:
        expense.incurred_date = incurred_date
    if project_slug is not None:
        project = await get_project(project_slug, client_slug)
        expense.project_id = pk(project)
    expense.updated_at = datetime.now()
    await expense.save()
    return expense


@in_db_session
async def delete_expense(uid_prefix: str) -> Expense:
    expense = await find_expense(uid_prefix)
    _ensure_unlocked(expense)
    for receipt in await ExpenseReceipt.where(lambda r: r.expense_id == expense.id).all():
        await receipt.delete()  # manual cascade (ttd#13 would make this a DB action)
    await expense.delete()
    return expense


@in_db_session
async def recent_expenses(
    *,
    project_slug: str | None = None,
    client_slug: str | None = None,
    limit: int = 8,
) -> list[ExpenseSuggestion]:
    """Distinct (description, amount) pairs from prior expenses, newest first.

    Scoped to the project; if no project given, scoped to the client.
    """
    views = await list_expenses(project_slug=project_slug, client_slug=client_slug)
    seen: set[tuple[str, Decimal]] = set()
    out: list[ExpenseSuggestion] = []
    for view in reversed(views):  # list_expenses is oldest-first; we want newest-first
        key = (view.expense.description, view.expense.amount)
        if key in seen:
            continue
        seen.add(key)
        out.append(ExpenseSuggestion(view.expense.description, view.expense.amount))
        if len(out) >= limit:
            break
    return out


MAX_RECEIPT_BYTES = 5 * 1024 * 1024  # 5 MiB — receipts are meant to be small


@in_db_session
async def add_receipt(uid_prefix: str, path: Path) -> ExpenseReceipt:
    expense = await find_expense(uid_prefix)
    raw = path.read_bytes()
    if len(raw) > MAX_RECEIPT_BYTES:
        raise TtdError(
            f"Receipt is {len(raw) // 1024} KB; the limit is "
            f"{MAX_RECEIPT_BYTES // (1024 * 1024)} MB"
        )
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    for existing in await ExpenseReceipt.where(lambda r: r.expense_id == expense.id).all():
        await existing.delete()  # one receipt per expense; replace
    receipt = ExpenseReceipt(
        id=uuid4(),
        expense_id=pk(expense),
        filename=path.name,
        content_type=content_type,
        data_b64=base64.b64encode(raw).decode("ascii"),
    )
    await receipt.save()
    return receipt


@in_db_session
async def get_receipt(uid_prefix: str) -> tuple[str, str, bytes] | None:
    expense = await find_expense(uid_prefix)
    receipt = await ExpenseReceipt.where(lambda r: r.expense_id == expense.id).first()
    if receipt is None:
        return None
    return receipt.filename, receipt.content_type, base64.b64decode(receipt.data_b64)


@in_db_session
async def remove_receipt(uid_prefix: str) -> None:
    expense = await find_expense(uid_prefix)
    for receipt in await ExpenseReceipt.where(lambda r: r.expense_id == expense.id).all():
        await receipt.delete()


@in_db_session
async def load_invoice_receipts(expense_lines) -> list[tuple[str, str, bytes]]:
    """Decoded (filename, content_type, bytes) receipts for an invoice's expense
    lines, in line order; expense lines without a receipt are skipped."""
    out: list[tuple[str, str, bytes]] = []
    for line in expense_lines:
        got = await get_receipt(str(line.expense_id)[:8])
        if got is not None:
            out.append(got)
    return out
