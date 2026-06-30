from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from ttd.core.errors import InvoicedExpenseError, TtdError
from ttd.services import clients as client_svc
from ttd.services import expenses as expense_svc
from ttd.services import projects as project_svc
from ttd.storage.models import Expense, ExpenseReceipt, pk


async def _project(db):
    await client_svc.create_client("Acme Corp", hourly_rate=Decimal("150"))
    return await project_svc.create_project("API Rewrite", "acme-corp")


async def test_expense_roundtrips(db):
    project = await _project(db)
    now = datetime.now()
    exp = Expense(
        id=uuid4(),
        project_id=pk(project),
        incurred_date=date(2026, 6, 15),
        description="Claude Code",
        amount=Decimal("100.00"),
        created_at=now,
        updated_at=now,
    )
    await exp.save()

    fetched = (await Expense.all())[0]
    assert fetched.description == "Claude Code"
    assert fetched.amount == Decimal("100.00")
    assert fetched.incurred_date == date(2026, 6, 15)
    assert fetched.invoice_id is None


async def test_receipt_roundtrips_as_base64(db):
    project = await _project(db)
    now = datetime.now()
    exp = Expense(
        id=uuid4(),
        project_id=pk(project),
        incurred_date=date(2026, 6, 15),
        description="x",
        amount=Decimal("1"),
        created_at=now,
        updated_at=now,
    )
    await exp.save()
    receipt = ExpenseReceipt(
        id=uuid4(),
        expense_id=pk(exp),
        filename="r.pdf",
        content_type="application/pdf",
        data_b64="JVBERi0xLjQ=",
    )
    await receipt.save()
    assert (await ExpenseReceipt.all())[0].data_b64 == "JVBERi0xLjQ="


async def test_add_and_list_expense(db):
    await _project(db)
    exp = await expense_svc.add_expense("api-rewrite", "Claude Code", Decimal("100"))
    assert exp.amount == Decimal("100")
    views = await expense_svc.list_expenses()
    assert len(views) == 1
    assert views[0].client.slug == "acme-corp"
    assert views[0].has_receipt is False


async def test_edit_and_delete_expense(db):
    await _project(db)
    exp = await expense_svc.add_expense("api-rewrite", "Claude", Decimal("100"))
    await expense_svc.edit_expense(str(exp.id)[:8], amount=Decimal("120"))
    assert (await expense_svc.list_expenses())[0].expense.amount == Decimal("120")
    await expense_svc.delete_expense(str(exp.id)[:8])
    assert await expense_svc.list_expenses() == []


async def test_locked_expense_refuses_edit_and_delete(db):
    await _project(db)
    exp = await expense_svc.add_expense("api-rewrite", "Claude", Decimal("100"))
    exp.invoice_id = uuid4()
    await exp.save()
    with pytest.raises(InvoicedExpenseError):
        await expense_svc.edit_expense(str(exp.id)[:8], amount=Decimal("1"))
    with pytest.raises(InvoicedExpenseError):
        await expense_svc.delete_expense(str(exp.id)[:8])


async def test_recent_expenses_returns_distinct_pairs(db):
    await _project(db)
    await expense_svc.add_expense("api-rewrite", "Claude Code", Decimal("100"))
    await expense_svc.add_expense("api-rewrite", "Claude Code", Decimal("100"))
    await expense_svc.add_expense("api-rewrite", "Figma", Decimal("15"))
    suggestions = await expense_svc.recent_expenses(project_slug="api-rewrite")
    pairs = [(s.description, s.amount) for s in suggestions]
    assert pairs == [("Figma", Decimal("15")), ("Claude Code", Decimal("100"))]


async def test_receipt_add_get_roundtrip(db, tmp_path):
    await _project(db)
    exp = await expense_svc.add_expense("api-rewrite", "Claude", Decimal("100"))
    src = tmp_path / "receipt.pdf"
    payload = b"%PDF-1.4\n\xff\xd8 binary"
    src.write_bytes(payload)

    await expense_svc.add_receipt(str(exp.id)[:8], src)
    filename, content_type, data = await expense_svc.get_receipt(str(exp.id)[:8])
    assert filename == "receipt.pdf"
    assert content_type == "application/pdf"
    assert data == payload
    assert (await expense_svc.list_expenses())[0].has_receipt is True


async def test_receipt_remove(db, tmp_path):
    await _project(db)
    exp = await expense_svc.add_expense("api-rewrite", "Claude", Decimal("100"))
    src = tmp_path / "r.png"
    src.write_bytes(b"\x89PNG\r\n")
    await expense_svc.add_receipt(str(exp.id)[:8], src)
    await expense_svc.remove_receipt(str(exp.id)[:8])
    assert await expense_svc.get_receipt(str(exp.id)[:8]) is None


async def test_oversized_receipt_rejected(db, tmp_path):
    await _project(db)
    exp = await expense_svc.add_expense("api-rewrite", "Claude", Decimal("100"))
    big = tmp_path / "big.pdf"
    big.write_bytes(b"0" * (expense_svc.MAX_RECEIPT_BYTES + 1))
    with pytest.raises(TtdError):
        await expense_svc.add_receipt(str(exp.id)[:8], big)


async def test_cli_app_registers_expense_commands():
    from ttd.cli.expenses import app as expense_app

    # The sub-app must be importable and named "expense".
    # Cyclopts stores name as a tuple, string, or list depending on version.
    name = expense_app.name
    assert name == "expense" or name == ["expense"] or name == ("expense",)
