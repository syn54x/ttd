from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from ttd.services import clients as client_svc
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
