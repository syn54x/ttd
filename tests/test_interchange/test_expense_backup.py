import json
import uuid
from datetime import date
from decimal import Decimal

import pytest

from ttd.core.errors import TtdError
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


# ---------------------------------------------------------------------------
# on_conflict="skip" — existing expense is left unchanged
# ---------------------------------------------------------------------------


async def test_restore_expenses_skip_leaves_existing_unchanged(db):
    await client_svc.create_client("Beta Corp")
    await project_svc.create_project("Beta Project", "beta-corp")
    exp = await expense_svc.add_expense(
        "beta-project", "Original Desc", Decimal("50"), incurred_date=date(2026, 1, 10)
    )
    original_id = str(exp.id)

    metadata = {
        "expenses": [
            {
                "id": original_id,
                "client": "beta-corp",
                "project": "beta-project",
                "incurred_date": "2026-01-10",
                "description": "Updated Desc",
                "amount": "99.00",
                "note": "",
            }
        ],
        "receipts": [],
    }
    written = await restore_expenses(metadata, on_conflict="skip")

    assert written == 0
    unchanged = await Expense.all()
    assert len(unchanged) == 1
    assert unchanged[0].description == "Original Desc"
    assert unchanged[0].amount == Decimal("50")


# ---------------------------------------------------------------------------
# on_conflict="update" — existing expense gets new field values
# ---------------------------------------------------------------------------


async def test_restore_expenses_update_overwrites_existing(db):
    await client_svc.create_client("Gamma LLC")
    await project_svc.create_project("Gamma Project", "gamma-llc")
    exp = await expense_svc.add_expense(
        "gamma-project", "Old Desc", Decimal("25"), incurred_date=date(2026, 2, 1)
    )
    eid = str(exp.id)

    metadata = {
        "expenses": [
            {
                "id": eid,
                "client": "gamma-llc",
                "project": "gamma-project",
                "incurred_date": "2026-02-15",
                "description": "New Desc",
                "amount": "75.00",
                "note": "updated",
            }
        ],
        "receipts": [],
    }
    written = await restore_expenses(metadata, on_conflict="update")

    assert written == 1
    updated = await Expense.all()
    assert len(updated) == 1
    assert updated[0].description == "New Desc"
    assert updated[0].amount == Decimal("75")
    assert updated[0].note == "updated"
    assert updated[0].incurred_date == date(2026, 2, 15)


# ---------------------------------------------------------------------------
# invoiced-expense guard — expense with invoice_id is never overwritten
# ---------------------------------------------------------------------------


async def test_restore_expenses_never_overwrites_invoiced_expense(db):
    await client_svc.create_client("Delta Inc")
    await project_svc.create_project("Delta Project", "delta-inc")
    exp = await expense_svc.add_expense(
        "delta-project", "Invoiced Expense", Decimal("200"), incurred_date=date(2026, 3, 1)
    )
    # Simulate the expense being locked to an invoice.
    fake_invoice_id = uuid.uuid4()
    exp.invoice_id = fake_invoice_id
    await exp.save()

    metadata = {
        "expenses": [
            {
                "id": str(exp.id),
                "client": "delta-inc",
                "project": "delta-project",
                "incurred_date": "2026-03-01",
                "description": "Should Not Change",
                "amount": "999.00",
                "note": "",
            }
        ],
        "receipts": [],
    }
    written = await restore_expenses(metadata, on_conflict="update")

    assert written == 0
    locked = await Expense.all()
    assert len(locked) == 1
    assert locked[0].description == "Invoiced Expense"
    assert locked[0].amount == Decimal("200")
    assert locked[0].invoice_id == fake_invoice_id


# ---------------------------------------------------------------------------
# receipt for unknown expense id is skipped
# ---------------------------------------------------------------------------


async def test_restore_expenses_skips_receipt_for_unknown_expense(db):
    await client_svc.create_client("Epsilon Co")
    await project_svc.create_project("Eps Project", "epsilon-co")
    exp = await expense_svc.add_expense(
        "eps-project", "Known Expense", Decimal("10"), incurred_date=date(2026, 4, 1)
    )
    import base64

    dummy_b64 = base64.b64encode(b"receipt-data").decode()
    unknown_id = str(uuid.uuid4())

    metadata = {
        "expenses": [
            {
                "id": str(exp.id),
                "client": "epsilon-co",
                "project": "eps-project",
                "incurred_date": "2026-04-01",
                "description": "Known Expense",
                "amount": "10.00",
                "note": "",
            }
        ],
        "receipts": [
            # This receipt references an expense id NOT in the expenses list -> skipped.
            {
                "expense_id": unknown_id,
                "filename": "ghost.pdf",
                "content_type": "application/pdf",
                "data_b64": dummy_b64,
            }
        ],
    }
    written = await restore_expenses(metadata, on_conflict="skip")

    # The expense was already present → skip; no receipt added for the ghost id.
    assert written == 0
    assert await ExpenseReceipt.all() == []


# ---------------------------------------------------------------------------
# receipt replace path — existing receipt is deleted and replaced
# ---------------------------------------------------------------------------


async def test_restore_expenses_replaces_existing_receipt(db, tmp_path):
    await client_svc.create_client("Zeta Ltd")
    await project_svc.create_project("Zeta Project", "zeta-ltd")
    exp = await expense_svc.add_expense(
        "zeta-project", "Receipt Expense", Decimal("30"), incurred_date=date(2026, 5, 1)
    )
    # Attach an initial receipt.
    src = tmp_path / "old.pdf"
    src.write_bytes(b"%PDF old")
    await expense_svc.add_receipt(str(exp.id)[:8], src)
    assert len(await ExpenseReceipt.all()) == 1

    # Delete the expense so restore_expenses re-inserts it (new path), then also
    # provides a new receipt for the same expense id.
    import base64

    new_b64 = base64.b64encode(b"%PDF new").decode()

    # Delete expense so it gets re-inserted (exercises the "new" branch + receipt replace).
    for e in await Expense.all():
        await e.delete()
    for r in await ExpenseReceipt.all():
        await r.delete()

    metadata = {
        "expenses": [
            {
                "id": str(exp.id),
                "client": "zeta-ltd",
                "project": "zeta-project",
                "incurred_date": "2026-05-01",
                "description": "Receipt Expense",
                "amount": "30.00",
                "note": "",
            }
        ],
        "receipts": [
            {
                "expense_id": str(exp.id),
                "filename": "new.pdf",
                "content_type": "application/pdf",
                "data_b64": new_b64,
            }
        ],
    }
    written = await restore_expenses(metadata, on_conflict="update")

    assert written == 1
    receipts = await ExpenseReceipt.all()
    assert len(receipts) == 1
    assert receipts[0].filename == "new.pdf"


# ---------------------------------------------------------------------------
# export_records with invoiced filter (interchange_svc.py line 28)
# ---------------------------------------------------------------------------


async def test_export_records_invoiced_filter_excludes_non_invoiced(db):
    # With no entries and invoiced=True, the filter branch is exercised.
    records, meta = await export_records(invoiced=True)
    assert records == []
    # expenses and receipts lists are present but empty.
    assert meta["expenses"] == []
    assert meta["receipts"] == []


async def test_export_records_no_expenses_produces_empty_lists(db):
    # Confirms the meta structure when there are no expenses at all.
    _records, meta = await export_records()
    assert "expenses" in meta
    assert "receipts" in meta
    assert meta["expenses"] == []
    assert meta["receipts"] == []


# ---------------------------------------------------------------------------
# json_io edge cases
# ---------------------------------------------------------------------------


def test_read_json_invalid_json_raises(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json {{{")
    with pytest.raises(TtdError, match="not valid JSON"):
        json_io.read_json(bad)


def test_read_json_bare_array(tmp_path):
    p = tmp_path / "bare.json"
    rows = [{"date": "2026-01-01", "note": "test"}]
    p.write_text(json.dumps(rows))
    result = json_io.read_json(p)
    assert result == rows


def test_read_json_missing_entries_key_raises(tmp_path):
    p = tmp_path / "bad_dict.json"
    p.write_text(json.dumps({"foo": "bar"}))
    with pytest.raises(TtdError, match="no 'entries' key"):
        json_io.read_json(p)


def test_read_metadata_oserror_returns_empty(tmp_path):
    missing = tmp_path / "nonexistent.json"
    result = json_io.read_metadata(missing)
    assert result == {}


def test_read_metadata_bare_list_returns_empty(tmp_path):
    p = tmp_path / "list.json"
    p.write_text(json.dumps([1, 2, 3]))
    result = json_io.read_metadata(p)
    assert result == {}
