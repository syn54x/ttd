"""`ttd expense …` commands."""

import json
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated

from cyclopts import Parameter

from ttd.cli._output import console, success, table
from ttd.cli._run import TtdApp, with_db
from ttd.core.errors import TtdError
from ttd.core.money import format_money
from ttd.services import expenses as svc

app = TtdApp(name="expense", help="Track and bill back client expenses.")
receipt_app = TtdApp(name="receipt", help="Attach receipts to an expense.")
app.command(receipt_app)


def _parse_date(raw: str | None) -> date | None:
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise TtdError(f"Dates must be YYYY-MM-DD (got '{raw}')") from exc


def _amount(raw: str) -> Decimal:
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise TtdError(f"Amount must be a number (got '{raw}')") from exc


@app.command(name="add")
@with_db
async def add(
    description: str,
    amount: str,
    *,
    project: Annotated[str | None, Parameter(name=["--project", "-p"])] = None,
    on: Annotated[str | None, Parameter(name="--on", help="Incurred date YYYY-MM-DD")] = None,
    note: Annotated[str, Parameter(name=["--note", "-n"])] = "",
    receipt: Annotated[Path | None, Parameter(help="Receipt file to attach")] = None,
) -> None:
    """Record a purchased item to bill back to the client."""
    from ttd.config.loader import get_settings

    project = project or get_settings().defaults.project
    if project is None:
        raise TtdError("No project given and no [defaults].project — pass --project")
    expense = await svc.add_expense(
        project, description, _amount(amount), incurred_date=_parse_date(on), note=note
    )
    if receipt is not None:
        await svc.add_receipt(str(expense.id)[:8], receipt)
    success(f"Logged {format_money(expense.amount, 'USD')} — {expense.description}")


@app.command(name="list")
@with_db
async def list_(
    *,
    project: Annotated[str | None, Parameter(name=["--project", "-p"])] = None,
    client: str | None = None,
    date_from: Annotated[str | None, Parameter(name="--from")] = None,
    date_to: Annotated[str | None, Parameter(name="--to")] = None,
    unbilled: Annotated[bool, Parameter(help="Only not-yet-invoiced expenses")] = False,
    as_json: Annotated[bool, Parameter(name="--json")] = False,
) -> None:
    """List expenses, oldest first."""
    rows = await svc.list_expenses(
        project_slug=project,
        client_slug=client,
        date_from=_parse_date(date_from),
        date_to=_parse_date(date_to),
        unbilled_only=unbilled,
    )
    if as_json:
        payload = [
            {
                "id": str(r.expense.id),
                "client": r.client.slug,
                "project": r.project.slug,
                "date": r.expense.incurred_date.isoformat(),
                "description": r.expense.description,
                "amount": str(r.expense.amount),
                "note": r.expense.note,
                "invoiced": r.expense.invoice_id is not None,
                "receipt": r.has_receipt,
            }
            for r in rows
        ]
        console.print_json(json.dumps(payload))
        return
    if not rows:
        console.print('[muted]No expenses — `ttd expense add "Claude Code" 100 -p PROJECT`[/muted]')
        return
    t = table("ID", "Date", "Project", "Description", "Amount", "")
    total = Decimal("0")
    for r in rows:
        e = r.expense
        total += e.amount
        flags = (" [accent]·inv[/accent]" if e.invoice_id else "") + (
            " [muted]📎[/muted]" if r.has_receipt else ""
        )
        t.add_row(
            str(e.id)[:8],
            e.incurred_date.strftime("%a %b %-d"),
            f"{r.client.slug}/{r.project.slug}",
            e.description,
            format_money(e.amount, r.client.currency) + flags,
            "",
        )
    console.print(t)
    console.print(f"Total: [bold]{format_money(total, 'USD')}[/bold]")


@app.command(name="edit")
@with_db
async def edit(
    uid: str,
    *,
    amount: str | None = None,
    description: Annotated[str | None, Parameter(name=["--description", "-d"])] = None,
    note: Annotated[str | None, Parameter(name=["--note", "-n"])] = None,
    on: Annotated[str | None, Parameter(name="--on")] = None,
    project: Annotated[str | None, Parameter(name=["--project", "-p"])] = None,
) -> None:
    """Edit an expense (refuses if it's on an invoice)."""
    expense = await svc.edit_expense(
        uid,
        amount=_amount(amount) if amount is not None else None,
        description=description,
        note=note,
        incurred_date=_parse_date(on),
        project_slug=project,
    )
    success(f"Updated expense {str(expense.id)[:8]}")


@app.command(name="rm")
@with_db
async def rm(uid: str) -> None:
    """Delete an expense (refuses if it's on an invoice)."""
    expense = await svc.delete_expense(uid)
    success(f"Deleted expense {str(expense.id)[:8]} ({format_money(expense.amount, 'USD')})")


@receipt_app.command(name="add")
@with_db
async def receipt_add(uid: str, path: Path) -> None:
    """Attach (or replace) a receipt on an expense."""
    receipt = await svc.add_receipt(uid, path)
    success(f"Attached {receipt.filename} to expense {uid}")


@receipt_app.command(name="get")
@with_db
async def receipt_get(
    uid: str,
    *,
    out: Annotated[Path | None, Parameter(help="Output file")] = None,
) -> None:
    """Write an expense's receipt to a file."""
    result = await svc.get_receipt(uid)
    if result is None:
        raise TtdError(f"Expense {uid} has no receipt")
    filename, _content_type, data = result
    dest = out or Path(filename)
    dest.write_bytes(data)
    success(f"Wrote {dest}")


@receipt_app.command(name="rm")
@with_db
async def receipt_rm(uid: str) -> None:
    """Remove an expense's receipt."""
    await svc.remove_receipt(uid)
    success(f"Removed receipt from expense {uid}")
