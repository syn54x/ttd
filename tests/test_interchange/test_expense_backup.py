import json
from datetime import date
from decimal import Decimal

from ttd.interchange import json_io
from ttd.interchange.importer import restore_expenses
from ttd.services import clients as client_svc
from ttd.services import expenses as expense_svc
from ttd.services import projects as project_svc
from ttd.services.interchange_svc import export_records
from ttd.storage.models import Expense, ExpenseReceipt


async def test_json_backup_roundtrips_expenses_and_receipts(db, tmp_path):
    await client_svc.create_client("Acme Corp", hourly_rate=Decimal("150"))
    await project_svc.create_project("API Rewrite", "acme-corp")
    exp = await expense_svc.add_expense(
        "api-rewrite", "Claude Code", Decimal("100"), incurred_date=date(2026, 6, 15)
    )
    src = tmp_path / "r.pdf"
    src.write_bytes(b"%PDF-1.4\n\xff")
    await expense_svc.add_receipt(str(exp.id)[:8], src)

    # Export -> json
    records, meta = await export_records()
    assert len(meta["expenses"]) == 1
    assert len(meta["receipts"]) == 1
    backup = tmp_path / "backup.json"
    json_io.write_json(records, backup, meta)

    # Wipe, then restore from the file's metadata.
    for e in await Expense.all():
        await e.delete()
    for r in await ExpenseReceipt.all():
        await r.delete()
    restored_meta = json_io.read_metadata(backup)
    written = await restore_expenses(restored_meta, on_conflict="update", create_missing=True)

    assert written == 1
    restored = await Expense.all()
    assert len(restored) == 1 and restored[0].amount == Decimal("100")
    assert restored[0].invoice_id is None  # imports never re-link invoices
    assert len(await ExpenseReceipt.all()) == 1


async def test_v1_metadata_without_expenses_restores_nothing(db, tmp_path):
    payload = {"ttd_export": 1, "clients": [], "projects": [], "entries": []}
    p = tmp_path / "v1.json"
    p.write_text(json.dumps(payload))
    written = await restore_expenses(json_io.read_metadata(p), create_missing=True)
    assert written == 0
    assert await Expense.all() == []
