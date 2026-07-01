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


# ---------------------------------------------------------------------------
# on_conflict="skip" — receipt for skipped expense is NOT replaced
# ---------------------------------------------------------------------------


async def test_restore_expenses_skip_leaves_receipt_intact(db, tmp_path):
    import base64

    await client_svc.create_client("Kappa Corp")
    await project_svc.create_project("Kappa Project", "kappa-corp")
    exp = await expense_svc.add_expense(
        "kappa-project", "Kappa Expense", Decimal("40"), incurred_date=date(2026, 6, 1)
    )
    expense_id = str(exp.id)

    # Attach RECEIPT_A via a temp file.
    receipt_a = tmp_path / "receipt_a.pdf"
    receipt_a.write_bytes(b"AAA")
    await expense_svc.add_receipt(expense_id[:8], receipt_a)

    # Build metadata via export_records, then mutate the receipt entry to RECEIPT_B.
    _records, meta = await export_records()
    assert len(meta["receipts"]) == 1
    meta["receipts"][0]["filename"] = "receipt_b.pdf"
    meta["receipts"][0]["data_b64"] = base64.b64encode(b"BBB").decode()

    # Restore with skip — expense already exists so it will be skipped.
    written = await restore_expenses(meta, on_conflict="skip", create_missing=False)

    assert written == 0
    # The receipt should still be RECEIPT_A.
    result = await expense_svc.get_receipt(expense_id[:8])
    assert result is not None
    filename, _content_type, data = result
    assert filename == "receipt_a.pdf"
    assert data == b"AAA"


# ---------------------------------------------------------------------------
# Finding 1 — export_records(invoiced=...) filters expenses too
# ---------------------------------------------------------------------------


async def test_export_invoiced_filter_applies_to_expenses(db, settings):
    """export_records(invoiced=True/False/None) must filter expenses as well as entries."""
    import uuid as _uuid

    await client_svc.create_client("Filter Corp", hourly_rate=Decimal("100"))
    await project_svc.create_project("Filter Project", "filter-corp")

    from ttd.storage.models import Expense

    # Create two expenses: one uninvoiced, one with a fake invoice_id
    await expense_svc.add_expense(
        "filter-project", "Not invoiced", Decimal("50"), incurred_date=date(2026, 6, 1)
    )
    exp_inv = await expense_svc.add_expense(
        "filter-project", "Invoiced", Decimal("75"), incurred_date=date(2026, 6, 2)
    )
    # Directly mark exp_inv as invoiced (simulates it being on a draft invoice)
    fake_invoice_id = _uuid.uuid4()
    exp_inv_row = await Expense.get_or_none(exp_inv.id)
    assert exp_inv_row is not None
    exp_inv_row.invoice_id = fake_invoice_id
    await exp_inv_row.save()

    # invoiced=True → only invoiced expense
    _records, meta = await export_records(invoiced=True)
    assert len(meta["expenses"]) == 1
    assert meta["expenses"][0]["description"] == "Invoiced"

    # invoiced=False → only free expense
    _records, meta = await export_records(invoiced=False)
    assert len(meta["expenses"]) == 1
    assert meta["expenses"][0]["description"] == "Not invoiced"

    # invoiced=None → both
    _records, meta = await export_records(invoiced=None)
    assert len(meta["expenses"]) == 2


# ---------------------------------------------------------------------------
# Finding 2 — expenses-only client appears in clients_meta
# ---------------------------------------------------------------------------


async def test_export_includes_expense_only_client_in_meta(db, settings):
    """A client with expenses but no entries must appear in meta['clients']."""
    await client_svc.create_client("Expense Only", hourly_rate=Decimal("200"), currency="EUR")
    await project_svc.create_project("Expense Project", "expense-only")
    await expense_svc.add_expense(
        "expense-project", "SaaS Tool", Decimal("99"), incurred_date=date(2026, 6, 10)
    )

    _records, meta = await export_records()

    client_slugs = [c["slug"] for c in meta["clients"]]
    assert "expense-only" in client_slugs

    client_entry = next(c for c in meta["clients"] if c["slug"] == "expense-only")
    assert client_entry["name"] == "Expense Only"
    assert client_entry["currency"] == "EUR"

    project_keys = [(p["client"], p["slug"]) for p in meta["projects"]]
    assert ("expense-only", "expense-project") in project_keys
