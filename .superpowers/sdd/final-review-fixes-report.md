# Final Review Fixes Report

## Finding 1 — `--invoiced` filter now applied to expenses on export

**File:** `src/ttd/services/interchange_svc.py`

Moved `expense_views = await list_expenses(...)` before the `used_clients`/`used_projects` sets are built. Added a filter immediately after fetching: `if invoiced is not None: expense_views = [v for v in expense_views if (v.expense.invoice_id is not None) == invoiced]`. The existing `receipts_meta` is derived from `expense_ids` which is now computed from the filtered `expense_views`, so receipts for filtered-out expenses are correctly excluded.

**Test added:** `test_export_invoiced_filter_applies_to_expenses` in `tests/test_interchange/test_expense_backup.py` — creates one uninvoiced expense and one with a fake `invoice_id`, then asserts `invoiced=True` returns only the invoiced one, `invoiced=False` only the free one, and `invoiced=None` returns both.

---

## Finding 2 — Expense-only clients now included in JSON backup metadata

**File:** `src/ttd/services/interchange_svc.py`

After the expense filter, added:
```python
used_clients |= {v.client.slug for v in expense_views}
used_projects |= {(v.client.slug, v.project.slug) for v in expense_views}
```
before building `clients_meta`/`projects_meta`. Also deduplicated the `Client.all()` call (was called twice; now uses `all_clients` local variable).

**Test added:** `test_export_includes_expense_only_client_in_meta` in `tests/test_interchange/test_expense_backup.py` — creates a client with `currency="EUR"` that has an expense but no entries, then asserts the client and project appear in `meta["clients"]` and `meta["projects"]` with correct name and currency.

---

## Finding 3 — Refresh diff now prints Expenses line when expense subtotal changes

**File:** `src/ttd/cli/invoices.py`, function `_print_refresh_diff`

Added a block inside the `if preview.totals_changed:` branch:
```python
if preview.before_expenses_subtotal != preview.after_expenses_subtotal:
    console.print(
        f"Expenses: {format_money(preview.before_expenses_subtotal, currency)} → "
        f"[bold]{format_money(preview.after_expenses_subtotal, currency)}[/bold]"
    )
```
Placed between the Subtotal and Tax lines, matching the existing arrow style.

**Test added:** `test_print_refresh_diff_shows_expenses_line_when_expense_subtotal_changes` in `tests/test_cli/test_invoice_cli.py` — builds a `RefreshPreview` with `before_expenses_subtotal=100` and `after_expenses_subtotal=50`, calls `_print_refresh_diff`, and asserts "Expenses" appears in the captured stdout.

---

## Finding 4 — Hardcoded 'USD' replaced in expense CLI messages

**File:** `src/ttd/cli/expenses.py`

- Moved `get_settings` import to module level (was only inside `add`).
- `add` success message: `format_money(expense.amount, get_settings().business.currency)` (extracted to `currency` local for line-length).
- `list` footer total: uses `rows[0].client.currency` when rows exist; falls back to `"USD"` only in the impossible case that rows is empty (the function returns early if no rows).
- `rm` success message: `format_money(expense.amount, get_settings().business.currency)` (extracted to `currency` local).

No test added (behavior is cosmetic and covered by existing CLI integration tests).

---

## Final Results

- **pytest:** 361 passed, 0 failed
- **Coverage:** 84.60% (threshold: 84%)
- **ty check:** All checks passed
- **ruff check:** All checks passed
