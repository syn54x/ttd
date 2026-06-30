# Billable Expenses (Client Chargebacks) — Design

**Status:** Approved design, pre-implementation
**Date:** 2026-06-30
**Scope:** Track purchased items for a project and bill them back to the client on invoices.

## Problem

A solo developer pays for things on a client's behalf (e.g. a $100/month Claude Code
subscription on their own card) and needs to charge those costs back to the client.
Today `ttd` only bills *time*. We need a second kind of billable thing — an **expense** —
that flows onto invoices alongside time entries.

## Decisions (settled during brainstorming)

| Decision | Choice | Rationale |
|---|---|---|
| Markup | **Pure pass-through** — one `amount` | What you paid is what you bill. No cost/markup split. |
| Attachment | **To a project** (client derived) | Mirrors `Entry`; reuses all project→client invoicing plumbing. |
| Tax | **Expenses untaxed** | Reimbursements; tax applies only to the time subtotal. Expenses add on after tax. |
| Recurrence | **One-off logging + history recall** | No scheduler. When adding, offer recent `(description, amount)` for the project/client to reuse. |
| Receipts | **Stored in DB, opt-in attachment** | Base64 text in a side table (see "Ferro constraint"). Travels in the single SQLite backup. |
| Invoice integration | **Approach 1 — separate line table** | `InvoiceExpenseLine` parallels `InvoiceLine`; keeps each shape honest, existing time logic untouched. |
| FK style | **Plain `*_id` columns** (codebase convention) | Matches every existing model; relationship migration tracked separately (ttd#13). |
| Scope | **A now, designed for C** | Invoicing + JSON backup now. Reports + full interchange deferred as later increments. |

### Ferro constraint (ferro-orm#160)

`Model.save()` serializes the whole instance via `model_dump_json()`, which cannot
represent non-UTF-8 `bytes`. Real binary (PDF/image receipts) therefore cannot be stored
in a raw `bytes` field through the ORM. **Workaround:** store receipts **base64-encoded in
a `text` column**, in a dedicated side table so list queries never load receipt bytes.
Tracked upstream as ferro-orm#160; the related ttd convention/refactor is ttd#13.

## Scope

**In scope (A):**
- `Expense`, `ExpenseReceipt`, `InvoiceExpenseLine` models + one `Invoice` field.
- `services/expenses.py` (CRUD, receipts, recall).
- `ttd expense` CLI sub-app (+ interactive form with recall, + `receipt` subcommands).
- Invoicing lifecycle: draft → persist → refresh → void, including untaxed totals.
- Invoice rendering: PDF expense section + opt-in receipt pages; markdown expense section.
- Invoice generation: explicit format choice (default PDF); markdown disabled when receipts present.
- JSON backup: expenses + receipts in the envelope (v2).
- TUI: invoice detail shows expenses; quick-add expense entry.

**Deferred (later increments):**
- **Reports awareness** (B): expense totals in `ttd report …` and `summary.py`.
- **Full interchange** (C): expenses in CSV/XLSX/Numbers export *and* import.
- TUI: dedicated full expenses management screen (v1 ships quick-add only).
- Recurring-expense scheduling/generation (explicitly out — recall covers the need).
- Expense markup, per-expense taxable flag, cost-vs-billed split.

## Data model

New module `storage/models/expense.py`:

```python
class Expense(Model):
    """A purchased item billed back to a client, attached to a project.
    `invoice_id` set means billed & locked — mirrors Entry."""
    id: Annotated[UUID | None, FerroField(primary_key=True)] = None
    project_id: Annotated[UUID, FerroField(index=True)]
    incurred_date: Annotated[date, FerroField(db_type="date", index=True)]
    description: str
    amount: Decimal
    note: str = ""
    invoice_id: Annotated[UUID | None, FerroField(index=True)] = None
    created_at: datetime
    updated_at: datetime

class ExpenseReceipt(Model):
    """Optional receipt blob; own table so `expense list` never loads bytes.
    Base64 text per ferro-orm#160."""
    id: Annotated[UUID | None, FerroField(primary_key=True)] = None
    expense_id: Annotated[UUID, FerroField(unique=True, index=True)]
    filename: str
    content_type: str
    data_b64: Annotated[str, FerroField(db_type="text")]
```

Add to `storage/models/invoice.py`:

```python
class InvoiceExpenseLine(Model):
    """One expense frozen onto an invoice; amount frozen at invoice time."""
    id: Annotated[UUID | None, FerroField(primary_key=True)] = None
    invoice_id: Annotated[UUID, FerroField(index=True)]
    expense_id: Annotated[UUID, FerroField(index=True)]
    incurred_date: Annotated[date, FerroField(db_type="date")]
    description: str
    amount: Decimal
```

Add one field to `Invoice` (default keeps existing rows valid):

```python
    expenses_subtotal: Decimal = Decimal("0")
```

**Invoice totals contract (after this change):**
- `subtotal` — time lines only; remains the **taxed** base. *(unchanged meaning)*
- `tax` — `to_cents(subtotal * tax_rate)`. *(unchanged math; time only)*
- `expenses_subtotal` — sum of expense lines; **untaxed**.
- `total` — `subtotal + tax + expenses_subtotal`.

**Migration:** Ferro `migrate_updates=True` adds the new tables and the defaulted
`expenses_subtotal` column on connect. No manual migration script (consistent with the project).

## Services (`services/expenses.py`)

All under `@in_db_session`, mirroring `services/entries.py`:

```python
async def add_expense(project_slug, description, amount, *, incurred_date=None,
                      note="", receipt_path=None) -> Expense
async def list_expenses(*, client=None, project=None, date_from=None,
                        date_to=None, unbilled_only=False) -> list[ExpenseView]
async def edit_expense(expense_id, **fields) -> Expense   # blocked if invoice_id set
async def delete_expense(expense_id) -> None              # also deletes its receipt (manual cascade)
async def recent_expenses(project_slug=None, client_slug=None, limit=8) -> list[ExpenseSuggestion]

# Receipts
async def add_receipt(expense_id, path) -> ExpenseReceipt
async def get_receipt(expense_id) -> tuple[str, str, bytes] | None   # (filename, content_type, bytes)
async def remove_receipt(expense_id) -> None
```

- `ExpenseView` = `expense + project + client + has_receipt`, resolved via the manual
  dict-join pattern used elsewhere — list/table rendering needs no extra queries.
- **Locking parity:** `edit_expense`/`delete_expense` raise if `invoice_id` is set
  (same "void and re-invoice" rule as invoiced entries).
- **Receipts:** read file → base64 → sniff `content_type` from extension → one
  `ExpenseReceipt` row. Size guard (~5 MB) rejects oversized files.
- **Recall:** `recent_expenses` returns distinct `(description, amount)` pairs from prior
  expenses, newest-first, scoped to project then falling back to client. Pure read; no
  dedup/template table.

## CLI (`cli/expenses.py`)

New `ttd expense` sub-app, registered in `cli/app.py`:

```sh
ttd expense add "Claude Code" 100 -p api-rewrite
ttd expense add "Claude Code" 100 -p api-rewrite --on 2026-06-15 \
    --note "June sub" --receipt ~/Downloads/claude-receipt.pdf
ttd expense add -i                       # interactive form; recall picker after project

ttd expense list -p api-rewrite
ttd expense list --client acme-corp --from 2026-06-01 --to 2026-06-30
ttd expense list --unbilled
ttd expense list --json

ttd expense edit <id> --amount 120 --note "..."   # refuses if invoiced
ttd expense rm <id>                                # refuses if invoiced

ttd expense receipt add <id> ~/Downloads/receipt.pdf
ttd expense receipt get <id> --out ./receipt.pdf  # decode base64 → file
ttd expense receipt rm <id>
```

- `add` takes `description` + `amount` positionally; `-p/--project`, `--on` (incurred
  date, default today), `--note`, `--receipt` as options.
- `list` renders `table("ID", "Date", "Project", "Description", "Amount", "")` with an
  `·inv` flag on invoiced rows and a footer total; `--json` emits structured form.
- `-i` triggers the interactive form; passed flags pre-fill it; recall picker sourced from
  `recent_expenses`.
- `receipt` is a nested command group (like `invoice mark`).

## Invoicing integration (`services/invoicing.py`)

- **Draft (`build_draft`):** after time lines, pull uninvoiced billable expenses for the
  client's projects in the period (`invoice_id is None`, within period). Build trivial
  expense draft lines (no rollup/rounding/rate). `Draft` gains `expense_lines` and
  `expenses_subtotal`. **Drafts may be expenses-only** — the "no billable entries" guard
  relaxes to "no entries *and* no expenses".
- **Persist (`persist_draft`):** in the existing transaction, write one
  `InvoiceExpenseLine` per expense line and stamp `expense.invoice_id = invoice.id`
  (mirrors the entry-locking loop). Store `invoice.expenses_subtotal`.
- **Void (`mark_invoice`):** add a loop nulling `expense.invoice_id` for linked expenses,
  releasing them exactly as entries are released (manual cascade; ttd#13 would make it a
  DB action later).
- **Refresh (`preview_refresh`/`apply_refresh`):** expense lines join the diff model; the
  only mutable billing field is `amount`. Paid invoices block amount changes (description
  edits allowed), reusing `PAID_REFRESH_BLOCKED`. Added/removed expenses show as
  add/remove diffs.

## Invoice rendering & generation

**PDF (`invoicing/pdf.py`):** a "Reimbursable expenses" table after time lines (date /
description / amount); totals block becomes Subtotal (time) / Tax / Expenses
(reimbursable) / Total. No expenses → section and line omitted (existing invoices render
byte-identically).

**Markdown (`invoicing/markdown.py`):** same expense section in text. **Markdown never
renders receipts.**

**Receipt inclusion (opt-in):**
- `--receipts` flag on `invoice create` / `invoice render`; `[invoice].attach_receipts`
  config default.
- **PDF only.** Image receipts via fpdf2 `image()`; PDF receipts merged via **`pypdf`**
  (new pure-python dependency — honors the "no system dependencies" rule), behind a
  "Receipts" divider page.
- `--receipts` with no PDF target → error.

**Format is an explicit choice (no auto-both):**
- Remove `render`'s `if not pdf and not md: pdf = md = True`. When no format flag is
  given, **default to PDF only** (canonical, sendable). Apply the same default to `create`
  so a bare `invoice create --client x` produces a PDF.
- `--md` opts into markdown; `--pdf --md` for both.

**Markdown disabled when receipts present:**
- Condition: `--receipts` (or config) active **and** the invoice has ≥1 linked expense
  with an `ExpenseReceipt`.
- Explicit `--md` then → **hard error** (fail fast): *"Invoice N has K receipts; Markdown
  can't render them. Drop --md, or omit --receipts to generate Markdown without them."*
- Interactive `create` form disables/hides the "Render Markdown?" option in that state.
- Receipts active but invoice has no receipts → markdown stays available.
- `svc.invoice_has_receipts(view) -> bool` centralizes the check for CLI + form.

## TUI

- **Invoices screen:** invoice detail gains a read-only "Reimbursable expenses" table and
  the expanded totals block (parity with PDF).
- **Quick-add expense** affixed to timesheet/dashboard (key `e` → expense form with project
  picker + recall list) so the recall UX exists in the TUI.
- `tui/_data.py` gains read helpers (expenses for an invoice / period).
- Full dedicated expenses screen deferred.

## JSON backup (`interchange/json_io.py`)

- Envelope gains an `expenses` array (project slug, incurred_date, description, amount,
  note, invoice_number) **and** receipts (base64, keyed to expense), so backups round-trip
  everything.
- `read_json` restores expenses + receipts; `ENVELOPE_VERSION` → 2; v1 envelopes still
  read (no `expenses` key → none imported).
- CSV/XLSX/Numbers untouched (deferred to increment C).

## Testing

- `test_storage/` — Expense/ExpenseReceipt/InvoiceExpenseLine CRUD; base64 receipt
  round-trip; locking (edit/delete refused when invoiced).
- `test_services` — draft with expenses (incl. expenses-only); untaxed-total math; void
  releases expenses; refresh diffs (add/remove/amount); paid-invoice block; `recent_expenses`.
- invoicing render — PDF with image + PDF receipts (page count grows / merge ran); markdown
  omits receipts; md-disabled-on-receipted-invoice guard; no-expense invoice renders
  byte-identically (regression guard).
- `test_interchange` — JSON v2 round-trips expenses + receipts; v1 envelope still imports.

## New dependency

- `pypdf` — pure-python, for merging PDF receipts into the invoice PDF. Pure-python keeps
  the project's "no system dependencies" constraint intact.

## Related issues

- **ferro-orm#160** — `Model.save()` can't persist binary `bytes` (drives the base64 receipt workaround).
- **ttd#13** — migrate models to Ferro relationships + cascades (would replace the manual
  expense/receipt/invoice cascade logic).
