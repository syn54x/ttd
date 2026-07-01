# Billable Expenses (Client Chargebacks) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a solo developer record purchased items against a project and bill them back to the client as untaxed, pass-through line items on invoices (with optional receipts).

**Architecture:** A new `Expense` model parallels `Entry` (attached to a project, locked to an invoice via `invoice_id`). Expenses ride a *separate* line table (`InvoiceExpenseLine`) onto invoices alongside time lines — time stays the taxed `subtotal`, expenses become a new untaxed `expenses_subtotal`. Receipts are stored base64 in a side table (`ExpenseReceipt`) because ferro-orm#160 blocks raw binary through `Model.save()`. CRUD, services, CLI, invoicing lifecycle, rendering, and JSON backup are all touched; reports and CSV/XLSX interchange are out of scope.

**Tech Stack:** Python 3.13, Ferro-ORM 0.12.x over SQLite, Cyclopts (CLI), Rich (output), Textual (TUI), fpdf2 (PDF), Jinja2 (markdown), `pypdf` (new — PDF receipt merging), pytest + pytest-asyncio.

## Global Constraints

- **Pass-through only:** an expense has one money figure, `amount`. No markup, no cost-vs-billed split.
- **Expenses are untaxed:** `tax = to_cents(subtotal * tax_rate)` stays time-only. `total = subtotal + tax + expenses_subtotal`.
- **Plain-id FK convention:** new models use `*_id: UUID` columns + manual service-layer cascade. No Ferro relationships (tracked separately in ttd#13).
- **Receipts are base64 text** in `ExpenseReceipt.data_b64` (ferro-orm#160 — raw `bytes` can't be saved via the ORM). Never add a raw `bytes` field to a model.
- **Locking parity with entries:** editing/deleting an expense whose `invoice_id` is set raises; voiding an invoice releases its expenses. Same rule and wording style as `InvoicedEntryError`.
- **No new system dependencies:** `pypdf` is pure-python and acceptable; nothing requiring a system library.
- **Existing invoices must render byte-identically** when an invoice has no expenses.
- **Migrations are automatic:** Ferro `migrate_updates=True` (in `init_db`) creates new tables and adds the defaulted `expenses_subtotal` column on connect. No manual migration script.
- **Tests:** `asyncio_mode = "auto"` — write `async def test_...(db)`; the `db` fixture (from `tests/conftest.py`) yields `Settings` with a temp SQLite DB. Money is `Decimal`. Set up clients/projects via `client_svc.create_client(name, hourly_rate=...)` and `project_svc.create_project(name, client_slug)`.
- **Commit style:** Conventional Commits (`feat:`, `test:`, `docs:`). Pre-commit runs ruff + ty + docs build; keep imports sorted and types clean.

---

## File Structure

**Create:**
- `src/ttd/storage/models/expense.py` — `Expense`, `ExpenseReceipt`.
- `src/ttd/services/expenses.py` — expense CRUD, recall, receipts.
- `src/ttd/cli/expenses.py` — `ttd expense` sub-app + `receipt` group.
- `tests/test_storage/test_expenses.py` — model + service CRUD/locking/receipts.
- `tests/test_services/test_invoicing_expenses.py` — draft/persist/void/refresh with expenses.
- `tests/test_invoicing/test_expense_render.py` — PDF/markdown expense sections + receipt gating.
- `tests/test_interchange/test_expense_backup.py` — JSON v2 round-trip.

**Modify:**
- `src/ttd/storage/models/invoice.py` — add `InvoiceExpenseLine`; add `Invoice.expenses_subtotal`.
- `src/ttd/storage/models/__init__.py` — export new models.
- `src/ttd/core/errors.py` — add `InvoicedExpenseError`.
- `src/ttd/services/invoicing.py` — expense draft lines, untaxed totals, persist/void/refresh, `InvoiceView.expense_lines`, `invoice_has_receipts`.
- `src/ttd/config/schema.py` — `InvoiceConfig.attach_receipts`.
- `src/ttd/cli/app.py` — register expense sub-app.
- `src/ttd/cli/invoices.py` — format choice (default PDF), `--receipts`, markdown gating.
- `src/ttd/invoicing/pdf.py` — expense section + receipt pages.
- `src/ttd/invoicing/markdown.py` + `templates/invoice.md.j2` — expense section.
- `src/ttd/interchange/json_io.py` — expenses + receipts in envelope (v2).
- `src/ttd/tui/screens/invoices.py`, `src/ttd/tui/_data.py` — invoice detail expenses + quick-add.
- `pyproject.toml` — add `pypdf` dependency.

---

## Task 1: Data model — Expense, ExpenseReceipt, InvoiceExpenseLine

**Files:**
- Create: `src/ttd/storage/models/expense.py`
- Modify: `src/ttd/storage/models/invoice.py`
- Modify: `src/ttd/storage/models/__init__.py`
- Test: `tests/test_storage/test_expenses.py`

**Interfaces:**
- Produces: `Expense(id, project_id, incurred_date, description, amount, note, invoice_id, created_at, updated_at)`; `ExpenseReceipt(id, expense_id, filename, content_type, data_b64)`; `InvoiceExpenseLine(id, invoice_id, expense_id, incurred_date, description, amount)`; `Invoice.expenses_subtotal: Decimal`. All exported from `ttd.storage.models`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_storage/test_expenses.py
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
        id=uuid4(), project_id=pk(project), incurred_date=date(2026, 6, 15),
        description="x", amount=Decimal("1"), created_at=now, updated_at=now,
    )
    await exp.save()
    receipt = ExpenseReceipt(
        id=uuid4(), expense_id=pk(exp), filename="r.pdf",
        content_type="application/pdf", data_b64="JVBERi0xLjQ=",
    )
    await receipt.save()
    assert (await ExpenseReceipt.all())[0].data_b64 == "JVBERi0xLjQ="
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_storage/test_expenses.py -v`
Expected: FAIL with `ImportError: cannot import name 'Expense'`.

- [ ] **Step 3: Create the expense models**

```python
# src/ttd/storage/models/expense.py
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from ferro import FerroField
from ferro.models import Model


class Expense(Model):
    """A purchased item billed back to a client, attached to a project.

    ``invoice_id`` set means billed & locked — mirrors ``Entry``. ``amount`` is
    pure pass-through: what you paid is what the client is billed.
    """

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
    """Optional receipt for an expense, stored base64 in its own table.

    Separate table so ``expense list`` never loads receipt bytes. Base64 text
    rather than raw ``bytes`` because ferro-orm#160 blocks binary via the ORM.
    """

    id: Annotated[UUID | None, FerroField(primary_key=True)] = None
    expense_id: Annotated[UUID, FerroField(unique=True, index=True)]
    filename: str
    content_type: str
    data_b64: Annotated[str, FerroField(db_type="text")]
```

- [ ] **Step 4: Add `InvoiceExpenseLine` and the `Invoice` field**

In `src/ttd/storage/models/invoice.py`, add the `expenses_subtotal` field to `Invoice` (place it next to `subtotal`/`total`):

```python
    subtotal: Decimal
    tax_rate: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")
    expenses_subtotal: Decimal = Decimal("0")  # untaxed pass-through expenses
    total: Decimal
```

And append a new model at the end of the file:

```python
class InvoiceExpenseLine(Model):
    """One expense frozen onto an invoice; ``amount`` is frozen at invoice time."""

    id: Annotated[UUID | None, FerroField(primary_key=True)] = None
    invoice_id: Annotated[UUID, FerroField(index=True)]
    expense_id: Annotated[UUID, FerroField(index=True)]
    incurred_date: Annotated[date, FerroField(db_type="date")]
    description: str
    amount: Decimal
```

- [ ] **Step 5: Export from the models package**

In `src/ttd/storage/models/__init__.py` add imports and `__all__` entries:

```python
from ttd.storage.models.expense import Expense, ExpenseReceipt
from ttd.storage.models.invoice import Invoice, InvoiceExpenseLine, InvoiceLine
```

Add `"Expense"`, `"ExpenseReceipt"`, `"InvoiceExpenseLine"` to `__all__` (keep it alphabetized).

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_storage/test_expenses.py -v`
Expected: PASS (2 passed).

- [ ] **Step 7: Commit**

```bash
git add src/ttd/storage/models/ tests/test_storage/test_expenses.py
git commit -m "feat: add Expense, ExpenseReceipt, InvoiceExpenseLine models"
```

---

## Task 2: Expense service — CRUD + recall

**Files:**
- Create: `src/ttd/services/expenses.py`
- Modify: `src/ttd/core/errors.py`
- Test: `tests/test_storage/test_expenses.py` (append)

**Interfaces:**
- Consumes: `Expense`, `pk` (Task 1); `project_svc.get_project`, `client_svc`.
- Produces:
  - `InvoicedExpenseError(TtdError)`
  - `@dataclass ExpenseView(expense: Expense, project: Project, client: Client, has_receipt: bool)`
  - `@dataclass ExpenseSuggestion(description: str, amount: Decimal)`
  - `async add_expense(project_slug, description, amount, *, incurred_date=None, note="") -> Expense`
  - `async find_expense(uid_prefix) -> Expense`
  - `async list_expenses(*, project_slug=None, client_slug=None, date_from=None, date_to=None, unbilled_only=False) -> list[ExpenseView]`
  - `async edit_expense(uid_prefix, *, amount=None, description=None, note=None, incurred_date=None, project_slug=None, client_slug=None) -> Expense`
  - `async delete_expense(uid_prefix) -> Expense`
  - `async recent_expenses(*, project_slug=None, client_slug=None, limit=8) -> list[ExpenseSuggestion]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_storage/test_expenses.py (append)
import pytest
from ttd.core.errors import InvoicedExpenseError, NotFoundError
from ttd.services import expenses as expense_svc


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_storage/test_expenses.py -v`
Expected: FAIL with `ImportError: cannot import name 'InvoicedExpenseError'`.

- [ ] **Step 3: Add the error type**

In `src/ttd/core/errors.py`, after `InvoicedEntryError`:

```python
class InvoicedExpenseError(TtdError):
    """Attempted to modify an expense that is locked to an invoice."""
```

- [ ] **Step 4: Write the service**

```python
# src/ttd/services/expenses.py
"""Logging and managing billable expenses (client chargebacks)."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from ttd.core.errors import ConflictError, InvoicedExpenseError, NotFoundError
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
    incurred_date: date | None = None,
    note: str = "",
) -> Expense:
    project = await get_project(project_slug)
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
        wanted = {p.id for p in projects.values() if clients[p.client_id].slug == client_slug}
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
        rows.append(ExpenseView(e, project, clients[project.client_id], e.id in receipted))
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_storage/test_expenses.py -v`
Expected: PASS (all expense tests green).

- [ ] **Step 6: Commit**

```bash
git add src/ttd/services/expenses.py src/ttd/core/errors.py tests/test_storage/test_expenses.py
git commit -m "feat: expense CRUD service with history recall"
```

---

## Task 3: Expense service — receipts

**Files:**
- Modify: `src/ttd/services/expenses.py`
- Test: `tests/test_storage/test_expenses.py` (append)

**Interfaces:**
- Consumes: `ExpenseReceipt`, `add_expense`, `find_expense` (Tasks 1–2).
- Produces:
  - `MAX_RECEIPT_BYTES = 5 * 1024 * 1024`
  - `async add_receipt(uid_prefix: str, path: Path) -> ExpenseReceipt`
  - `async get_receipt(uid_prefix: str) -> tuple[str, str, bytes] | None`  (filename, content_type, raw bytes)
  - `async remove_receipt(uid_prefix: str) -> None`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_storage/test_expenses.py (append)
from pathlib import Path


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
    with pytest.raises(Exception):  # TtdError subclass
        await expense_svc.add_receipt(str(exp.id)[:8], big)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_storage/test_expenses.py -k receipt -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'add_receipt'`.

- [ ] **Step 3: Implement receipt functions**

Add imports at the top of `src/ttd/services/expenses.py`:

```python
import base64
import mimetypes
from pathlib import Path

from ttd.core.errors import TtdError
```

Append:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_storage/test_expenses.py -k receipt -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ttd/services/expenses.py tests/test_storage/test_expenses.py
git commit -m "feat: expense receipt storage (base64, size-guarded)"
```

---

## Task 4: CLI — `ttd expense` sub-app

**Files:**
- Create: `src/ttd/cli/expenses.py`
- Modify: `src/ttd/cli/app.py`
- Test: `tests/test_storage/test_expenses.py` (append a CLI smoke test) — or `tests/test_cli/` if present; use the `isolated_config` fixture.

**Interfaces:**
- Consumes: `expense_svc` (Tasks 2–3), `TtdApp`, `with_db`, `console`, `success`, `table` (existing CLI helpers).
- Produces: a Cyclopts `app` named `expense` with commands `add`, `list`, `edit`, `rm`, and a nested `receipt` group (`add`, `get`, `rm`); registered in the root app.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_storage/test_expenses.py (append)
async def test_cli_app_registers_expense_commands():
    from ttd.cli.expenses import app as expense_app
    names = set(expense_app._commands) if hasattr(expense_app, "_commands") else None
    # Fallback: the sub-app must at least be importable and named "expense"
    assert expense_app.name == "expense" or expense_app.name == ["expense"]
```

> Note: if `TtdApp` doesn't expose `_commands`, keep the import + name assertion only. The real behavioral coverage for CLI lives in the service tests; this test guards that the module imports cleanly (catches typos/bad imports in the command module).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_storage/test_expenses.py -k cli_app -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ttd.cli.expenses'`.

- [ ] **Step 3: Write the CLI module**

```python
# src/ttd/cli/expenses.py
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
        project_slug=project, client_slug=client,
        date_from=_parse_date(date_from), date_to=_parse_date(date_to),
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
async def receipt_get(uid: str, *, out: Annotated[Path | None, Parameter(help="Output file")] = None) -> None:
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
```

> **Interactive form + recall:** add an `-i` form to `add` mirroring `InvoiceCreateInput` in `cli/invoices.py` (a pydantic model fed to `interactive_fill`), with a select widget whose choices come from `svc.recent_expenses(...)`. Fold this in here only if `interactive_fill` supports dynamic per-field choices the way `client_choices` is used; otherwise leave a follow-up note and ship the explicit CLI. Do not block this task on the form.

- [ ] **Step 4: Register the sub-app**

In `src/ttd/cli/app.py`, add `expenses` to the import tuple in `_register_subcommands` and register it after `entries`:

```python
    from ttd.cli import (
        clients, config_cmds, db_cmds, entries, expenses, export, import_,
        invoices, log, projects, reports, taxes, timer,
    )
    ...
    app.command(entries.app)
    app.command(expenses.app)
```

- [ ] **Step 5: Run test + lint**

Run: `uv run pytest tests/test_storage/test_expenses.py -k cli_app -v && uv run ruff check src/ttd/cli/expenses.py && uv run ty check`
Expected: test PASS, lint clean.

- [ ] **Step 6: Manual smoke (optional but recommended)**

Run:
```bash
uv run ttd client add "Acme Corp" --rate 150 && uv run ttd project add "API Rewrite" --client acme-corp
uv run ttd expense add "Claude Code" 100 -p api-rewrite && uv run ttd expense list
```
Expected: a one-row table totaling $100.00.

- [ ] **Step 7: Commit**

```bash
git add src/ttd/cli/expenses.py src/ttd/cli/app.py tests/test_storage/test_expenses.py
git commit -m "feat: ttd expense CLI (add/list/edit/rm + receipt group)"
```

---

## Task 5: Invoicing — expense draft lines, untaxed totals, persist

**Files:**
- Modify: `src/ttd/services/invoicing.py`
- Test: `tests/test_services/test_invoicing_expenses.py`

**Interfaces:**
- Consumes: `Expense`, `InvoiceExpenseLine`, `pk` (Task 1); `build_draft`, `persist_draft`, `get_invoice`, `Draft`, `InvoiceView` (existing).
- Produces:
  - `@dataclass DraftExpenseLine(expense: Expense, incurred_date: date, description: str, amount: Decimal)`
  - `Draft.expense_lines: list[DraftExpenseLine]` and `Draft.expenses_subtotal: Decimal`
  - `InvoiceView.expense_lines: list[InvoiceExpenseLine]`
  - Updated totals helper so `total = subtotal + tax + expenses_subtotal`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_services/test_invoicing_expenses.py
from datetime import date
from decimal import Decimal

from ttd.config.schema import Settings
from ttd.reporting import periods
from ttd.services import expenses as expense_svc
from ttd.services import invoicing as svc
from ttd.services import clients as client_svc
from ttd.services import projects as project_svc
from ttd.storage.models import Expense


async def _client_project(db):
    await client_svc.create_client("Acme Corp", hourly_rate=Decimal("150"))
    await project_svc.create_project("API Rewrite", "acme-corp")


def _june() -> periods.Period:
    return periods.range_period(date(2026, 6, 1), date(2026, 6, 30))


async def test_draft_includes_unbilled_expenses_untaxed(db):
    await _client_project(db)
    await expense_svc.add_expense(
        "api-rewrite", "Claude Code", Decimal("100"), incurred_date=date(2026, 6, 15)
    )
    settings = Settings()  # tax_rate defaults to 0
    draft = await svc.build_draft("acme-corp", _june(), settings)
    assert draft.expenses_subtotal == Decimal("100")
    assert draft.subtotal == Decimal("0")        # no time entries
    assert draft.total == Decimal("100")


async def test_persist_locks_expenses_and_stores_subtotal(db):
    await _client_project(db)
    exp = await expense_svc.add_expense(
        "api-rewrite", "Claude Code", Decimal("100"), incurred_date=date(2026, 6, 15)
    )
    settings = Settings()
    draft = await svc.build_draft("acme-corp", _june(), settings)
    invoice = await svc.persist_draft(draft, settings)

    refetched = await Expense.get_or_none(exp.id)
    assert refetched.invoice_id == invoice.id           # locked
    assert invoice.expenses_subtotal == Decimal("100")
    view = await svc.get_invoice(invoice.number)
    assert len(view.expense_lines) == 1
    assert view.expense_lines[0].amount == Decimal("100")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_services/test_invoicing_expenses.py -v`
Expected: FAIL — `AttributeError: 'Draft' object has no attribute 'expenses_subtotal'`.

- [ ] **Step 3: Extend the dataclasses**

In `src/ttd/services/invoicing.py`, import the new model and add the dataclass + fields:

```python
from ttd.storage.models import (  # add to existing import
    ...,
    Expense,
    InvoiceExpenseLine,
)
```

```python
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
    expense_lines: list[DraftExpenseLine]      # NEW
    subtotal: Decimal
    expenses_subtotal: Decimal                 # NEW
    tax: Decimal
    total: Decimal
    number: str | None = None
```

Add `expense_lines` to `InvoiceView`:

```python
@dataclass
class InvoiceView:
    invoice: Invoice
    client: Client
    lines: list[InvoiceLine]
    expense_lines: list[InvoiceExpenseLine]    # NEW
    project_names: dict
```

- [ ] **Step 4: Build expense lines in `build_draft`; update totals**

Replace `_draft_totals` and the tail of `build_draft`:

```python
def _draft_totals(
    lines: list[DraftLine], expense_lines: list["DraftExpenseLine"], tax_rate: Decimal
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    subtotal = sum((line.amount for line in lines), Decimal("0"))
    expenses_subtotal = sum((e.amount for e in expense_lines), Decimal("0"))
    tax = to_cents(subtotal * tax_rate)  # time only — expenses are untaxed
    total = subtotal + tax + expenses_subtotal
    return subtotal, expenses_subtotal, tax, total
```

In `build_draft`, after building `lines`, gather expenses and relax the empty-guard:

```python
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
```

> The current `build_draft` raises when `not entries`; replace that guard with the combined one above. Remove the old `if not entries:` block.

- [ ] **Step 5: Persist expense lines and lock expenses**

In `persist_draft`, set `expenses_subtotal` on the `Invoice(...)` constructor:

```python
        expenses_subtotal=draft.expenses_subtotal,
```

Inside the `async with transaction():` block, after the `InvoiceLine` loop, add:

```python
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
```

- [ ] **Step 6: Load expense lines in `get_invoice`**

In `get_invoice`, after loading `lines`, add and pass through:

```python
    expense_lines = await InvoiceExpenseLine.where(lambda li: li.invoice_id == invoice.id).all()
    expense_lines.sort(key=lambda li: (li.incurred_date, li.description))
    ...
    return InvoiceView(invoice, client, lines, expense_lines, names)
```

- [ ] **Step 7: Fix other `_draft_totals` / `InvoiceView` / `Draft` callers**

`preview_refresh` calls `_draft_totals(after_lines, settings.invoice.tax_rate)` — update it to pass an expense-lines argument. For now (refresh expense support lands in Task 6) pass the invoice's existing expense lines so totals stay correct:

```python
    after_subtotal, after_expenses, after_tax, after_total = _draft_totals(
        after_lines, [], settings.invoice.tax_rate
    )
```

(Task 6 replaces the `[]` with real refreshed expense lines.) Update any other construction of `Draft(...)` or `InvoiceView(...)` in the file (search for them) to include the new fields. The `_print_draft` CLI helper is updated in Task 7.

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/test_services/test_invoicing_expenses.py tests/test_storage -v && uv run ty check`
Expected: PASS. Also run the full existing invoicing suite to catch signature breaks: `uv run pytest tests/test_services -v`.

- [ ] **Step 9: Commit**

```bash
git add src/ttd/services/invoicing.py tests/test_services/test_invoicing_expenses.py
git commit -m "feat: bill expenses on invoices (untaxed totals, lock on persist)"
```

---

## Task 6: Invoicing — void release + refresh

**Files:**
- Modify: `src/ttd/services/invoicing.py`
- Test: `tests/test_services/test_invoicing_expenses.py` (append)

**Interfaces:**
- Consumes: everything from Task 5.
- Produces: void nulls `expense.invoice_id`; refresh rebuilds expense lines, updates `expenses_subtotal`/`total`, and blocks amount changes on paid invoices.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_services/test_invoicing_expenses.py (append)
async def test_void_releases_expenses(db):
    await _client_project(db)
    exp = await expense_svc.add_expense(
        "api-rewrite", "Claude", Decimal("100"), incurred_date=date(2026, 6, 15)
    )
    settings = Settings()
    invoice = await svc.persist_draft(await svc.build_draft("acme-corp", _june(), settings), settings)
    await svc.mark_invoice(invoice.number, "void")
    assert (await Expense.get_or_none(exp.id)).invoice_id is None


async def test_refresh_drops_deleted_expense(db):
    await _client_project(db)
    exp = await expense_svc.add_expense(
        "api-rewrite", "Claude", Decimal("100"), incurred_date=date(2026, 6, 15)
    )
    settings = Settings()
    invoice = await svc.persist_draft(await svc.build_draft("acme-corp", _june(), settings), settings)
    # Release + delete the expense, then refresh.
    await svc.mark_invoice(invoice.number, "void")
    # Re-invoice fresh so the expense is linked again, then delete underlying expense via direct unlink
    # (simulating an expense removed from the period):
    invoice2 = await svc.persist_draft(await svc.build_draft("acme-corp", _june(), settings), settings)
    locked = await Expense.get_or_none(exp.id)
    locked.invoice_id = None
    await locked.save()
    await locked.delete()
    preview = await svc.preview_refresh(invoice2.number, settings)
    fresh = await svc.apply_refresh(invoice2.number, preview, settings)
    assert fresh.expenses_subtotal == Decimal("0")
    assert fresh.total == Decimal("0")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_services/test_invoicing_expenses.py -k "void or refresh" -v`
Expected: FAIL — void leaves `invoice_id` set / refresh totals wrong.

- [ ] **Step 3: Release expenses on void**

In `mark_invoice`, inside the `if status == "void":` transaction block, after the entry-release loop add:

```python
            for expense in await Expense.where(lambda e: e.invoice_id == invoice.id).all():
                expense.invoice_id = None
                await expense.save()
```

- [ ] **Step 4: Rebuild expense lines on refresh**

In `preview_refresh`, after computing `after_lines`, build the current expense lines from the invoice's linked expenses:

```python
    linked_expenses = await Expense.where(lambda e: e.invoice_id == invoice.id).all()
    after_expense_lines = [
        DraftExpenseLine(e, e.incurred_date, e.description, e.amount)
        for e in sorted(linked_expenses, key=lambda e: (e.incurred_date, e.created_at))
    ]
    after_subtotal, after_expenses, after_tax, after_total = _draft_totals(
        after_lines, after_expense_lines, settings.invoice.tax_rate
    )
```

Add `after_expenses` to `RefreshPreview` (a new field `after_expenses_subtotal: Decimal` and a `before_expenses_subtotal: Decimal = invoice.expenses_subtotal`), and fold expenses into `totals_changed`:

```python
    totals_changed = (
        before_subtotal != after_subtotal
        or before_tax != after_tax
        or before_total != after_total
        or invoice.expenses_subtotal != after_expenses
    )
```

Stash `after_expense_lines` on the preview (add a field `after_expense_lines: list[DraftExpenseLine]`) so `apply_refresh` can persist them without recomputing.

- [ ] **Step 5: Persist expense changes in `apply_refresh`**

In the non-paid branch of `apply_refresh`, after reconciling `InvoiceLine`s and before saving the invoice, reconcile expense lines (delete all + rewrite is simplest and safe — expense lines have no per-line history):

```python
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
```

And update the invoice-total assignments already present to use the refreshed values:

```python
            invoice.subtotal = fresh.after_subtotal
            invoice.tax = fresh.after_tax
            invoice.total = fresh.after_total
```

> Paid invoices: expense **amounts** are billing fields, so they fall under the existing paid-invoice block (`PAID_REFRESH_BLOCKED`) — no expense rewrite happens in the paid branch, matching time-line behavior.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_services/test_invoicing_expenses.py -v && uv run pytest tests/test_services -v`
Expected: PASS (all green, including pre-existing invoicing tests).

- [ ] **Step 7: Commit**

```bash
git add src/ttd/services/invoicing.py tests/test_services/test_invoicing_expenses.py
git commit -m "feat: release and refresh expenses through invoice lifecycle"
```

---

## Task 7: Rendering — PDF + markdown expense section (no receipts yet)

**Files:**
- Modify: `src/ttd/invoicing/pdf.py`
- Modify: `src/ttd/invoicing/markdown.py`, `src/ttd/invoicing/templates/invoice.md.j2`
- Modify: `src/ttd/cli/invoices.py` (`_print_draft` to show expenses)
- Test: `tests/test_invoicing/test_expense_render.py`

**Interfaces:**
- Consumes: `InvoiceView.expense_lines`, `Invoice.expenses_subtotal` (Tasks 5–6).
- Produces: PDF + markdown both render an "Reimbursable expenses" section and the expenses line in totals, omitted entirely when there are no expenses.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_invoicing/test_expense_render.py
from datetime import date
from decimal import Decimal

from ttd.config.schema import Settings
from ttd.invoicing.markdown import render_markdown
from ttd.invoicing.pdf import render_pdf
from ttd.reporting import periods
from ttd.services import clients as client_svc
from ttd.services import expenses as expense_svc
from ttd.services import invoicing as svc
from ttd.services import projects as project_svc


async def _invoice_with_expense(db):
    await client_svc.create_client("Acme Corp", hourly_rate=Decimal("150"))
    await project_svc.create_project("API Rewrite", "acme-corp")
    await expense_svc.add_expense(
        "api-rewrite", "Claude Code", Decimal("100"), incurred_date=date(2026, 6, 15)
    )
    period = periods.range_period(date(2026, 6, 1), date(2026, 6, 30))
    settings = Settings()
    invoice = await svc.persist_draft(await svc.build_draft("acme-corp", period, settings), settings)
    return await svc.get_invoice(invoice.number), settings


async def test_markdown_shows_expense_section(db):
    view, settings = await _invoice_with_expense(db)
    md = render_markdown(view, settings)
    assert "Reimbursable expenses" in md
    assert "Claude Code" in md
    assert "Expenses" in md  # totals line


async def test_pdf_renders_with_expenses(db, tmp_path):
    view, settings = await _invoice_with_expense(db)
    out = render_pdf(view, settings, tmp_path / "inv.pdf")
    assert out.exists() and out.stat().st_size > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_invoicing/test_expense_render.py -v`
Expected: FAIL — markdown lacks "Reimbursable expenses".

- [ ] **Step 3: Update the markdown template**

In `src/ttd/invoicing/templates/invoice.md.j2`, after the `## Work` loop and before the totals table, add a guarded expenses section:

```jinja
{% if expense_lines %}
## Reimbursable expenses

{% for e in expense_lines -%}
**{{ e.incurred_date.strftime("%b %-d") }}** · {{ e.description }} · **{{ money(e.amount) }}**

{% endfor %}
{% endif -%}
```

In the totals table, add the expenses row before `Total due`:

```jinja
| Subtotal | {{ money(invoice.subtotal) }} |
{% if invoice.tax -%}
| Tax ({{ "%.2f" | format(invoice.tax_rate * 100) }}%) | {{ money(invoice.tax) }} |
{% endif -%}
{% if invoice.expenses_subtotal -%}
| Expenses (reimbursable) | {{ money(invoice.expenses_subtotal) }} |
{% endif -%}
| **Total due** | **{{ money(invoice.total) }}** |
```

- [ ] **Step 4: Pass `expense_lines` to the template**

In `src/ttd/invoicing/markdown.py`, add `expense_lines=view.expense_lines` to `template.render(...)`.

- [ ] **Step 5: Update the PDF renderer**

In `src/ttd/invoicing/pdf.py`, after the time `lines` table and before the totals box, render an expenses table when present:

```python
    if view.expense_lines:
        pdf.ln(3)
        pdf.set_font("helvetica", style="B", size=9)
        pdf.cell(0, 6, "REIMBURSABLE EXPENSES", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("helvetica", size=9)
        with pdf.table(
            col_widths=(20, 138, 22),
            text_align=("LEFT", "LEFT", "RIGHT"),
            borders_layout="HORIZONTAL_LINES",
            line_height=6.5,
            padding=1.2,
        ) as etable:
            header = etable.row()
            pdf.set_font("helvetica", style="B", size=8)
            for col in ("DATE", "DESCRIPTION", "AMOUNT"):
                header.cell(col)
            pdf.set_font("helvetica", size=9)
            for eline in view.expense_lines:
                row = etable.row()
                row.cell(eline.incurred_date.strftime("%b %-d"))
                row.cell(_latin(eline.description))
                row.cell(_money(eline.amount, currency))
```

In the totals box, insert an expenses line between tax and total:

```python
    rows = [("Subtotal", _money(invoice.subtotal, currency))]
    if invoice.tax:
        rows.append((f"Tax ({invoice.tax_rate * 100:.2f}%)", _money(invoice.tax, currency)))
    if invoice.expenses_subtotal:
        rows.append(("Expenses", _money(invoice.expenses_subtotal, currency)))
    rows.append(("Total due", _money(invoice.total, currency)))
```

- [ ] **Step 6: Update `_print_draft` in the CLI**

In `src/ttd/cli/invoices.py`, in `_print_draft`, after the time-lines table, print expenses when present:

```python
    if draft.expense_lines:
        et = table("Date", "Description", "Amount")
        for e in draft.expense_lines:
            et.add_row(
                e.incurred_date.strftime("%a %b %-d"), e.description, format_money(e.amount, currency)
            )
        console.print(et)
        console.print(f"Expenses: {format_money(draft.expenses_subtotal, currency)}")
```

- [ ] **Step 7: Add a regression test — no expenses renders unchanged**

```python
# tests/test_invoicing/test_expense_render.py (append)
async def test_no_expense_invoice_omits_section(db, tmp_path):
    await client_svc.create_client("Acme Corp", hourly_rate=Decimal("150"))
    await project_svc.create_project("API Rewrite", "acme-corp")
    from ttd.services import entries as entry_svc
    from datetime import datetime
    await entry_svc.log_entry(
        "2026-06-10 9am-11am", "api-rewrite", now=datetime(2026, 6, 10, 12, 0)
    )
    period = periods.range_period(date(2026, 6, 1), date(2026, 6, 30))
    settings = Settings()
    invoice = await svc.persist_draft(await svc.build_draft("acme-corp", period, settings), settings)
    view = await svc.get_invoice(invoice.number)
    md = render_markdown(view, settings)
    assert "Reimbursable expenses" not in md
    assert "Expenses (reimbursable)" not in md
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/test_invoicing -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/ttd/invoicing/ src/ttd/cli/invoices.py tests/test_invoicing/test_expense_render.py
git commit -m "feat: render expense section on PDF and markdown invoices"
```

---

## Task 8: Receipt pages in PDF + config + pypdf

**Files:**
- Modify: `pyproject.toml` (add `pypdf`)
- Modify: `src/ttd/config/schema.py` (`InvoiceConfig.attach_receipts`)
- Modify: `src/ttd/invoicing/pdf.py` (receipt pages)
- Modify: `src/ttd/services/invoicing.py` (`invoice_has_receipts`)
- Test: `tests/test_invoicing/test_expense_render.py` (append)

**Interfaces:**
- Consumes: `get_receipt` (Task 3), `InvoiceView` (Task 5).
- Produces:
  - `settings.invoice.attach_receipts: bool` (default `False`)
  - `async svc.invoice_has_receipts(view: InvoiceView) -> bool`
  - `render_pdf(view, settings, path, *, receipts: bool = False) -> Path` (new keyword)

- [ ] **Step 1: Add the dependency**

Run: `uv add pypdf`
Expected: `pyproject.toml` gains `pypdf` under dependencies; lockfile updates.

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_invoicing/test_expense_render.py (append)
from pypdf import PdfReader
from ttd.services import invoicing as svc2  # alias to avoid clashing if needed


async def test_pdf_appends_pdf_receipt_pages(db, tmp_path):
    await client_svc.create_client("Acme Corp", hourly_rate=Decimal("150"))
    await project_svc.create_project("API Rewrite", "acme-corp")
    exp = await expense_svc.add_expense(
        "api-rewrite", "Claude", Decimal("100"), incurred_date=date(2026, 6, 15)
    )
    # a real 1-page PDF as the receipt
    from fpdf import FPDF
    receipt_pdf = tmp_path / "receipt.pdf"
    r = FPDF(); r.add_page(); r.set_font("helvetica", size=12); r.cell(0, 10, "RECEIPT"); r.output(str(receipt_pdf))
    await expense_svc.add_receipt(str(exp.id)[:8], receipt_pdf)

    period = periods.range_period(date(2026, 6, 1), date(2026, 6, 30))
    settings = Settings()
    invoice = await svc.persist_draft(await svc.build_draft("acme-corp", period, settings), settings)
    view = await svc.get_invoice(invoice.number)

    without = render_pdf(view, settings, tmp_path / "no.pdf", receipts=False)
    with_r = render_pdf(view, settings, tmp_path / "yes.pdf", receipts=True)
    assert len(PdfReader(str(with_r)).pages) > len(PdfReader(str(without)).pages)


async def test_invoice_has_receipts(db, tmp_path):
    view, settings = await _invoice_with_expense(db)  # expense, no receipt
    assert await svc.invoice_has_receipts(view) is False
```

- [ ] **Step 3: Add the config field**

In `src/ttd/config/schema.py`, `InvoiceConfig`:

```python
    attach_receipts: bool = False
    """Append expense receipts as pages when rendering invoice PDFs."""
```

- [ ] **Step 4: Add `invoice_has_receipts`**

In `src/ttd/services/invoicing.py`:

```python
from ttd.storage.models import ExpenseReceipt  # add to imports


@in_db_session
async def invoice_has_receipts(view: InvoiceView) -> bool:
    """True if any of the invoice's linked expenses has a stored receipt."""
    if not view.expense_lines:
        return False
    expense_ids = {li.expense_id for li in view.expense_lines}
    receipts = await ExpenseReceipt.all()
    return any(r.expense_id in expense_ids for r in receipts)
```

- [ ] **Step 5: Append receipt pages in `render_pdf`**

The renderer must NOT touch the DB. Receipts arrive already decoded from the caller
(the CLI loads them inside its async session — Task 9). Change the signature to accept a
list of `(filename, content_type, bytes)` and split image vs PDF receipts:

```python
import io

from pypdf import PdfReader, PdfWriter

Receipt = tuple[str, str, bytes]  # (filename, content_type, raw bytes)


def render_pdf(
    view: InvoiceView,
    settings: Settings,
    path: Path,
    *,
    receipts: list[Receipt] | None = None,
) -> Path:
    ...  # all existing rendering up to the footer note is unchanged
    path.parent.mkdir(parents=True, exist_ok=True)
    if not receipts:
        pdf.output(str(path))
        return path
    _write_with_receipts(pdf, receipts, path)
    return path


def _write_with_receipts(pdf: "FPDF", receipts: list[Receipt], path: Path) -> None:
    """Append image receipts as fpdf2 pages, then merge PDF receipts via pypdf."""
    images = [r for r in receipts if r[1].startswith("image/")]
    pdfs = [r for r in receipts if r[1] == "application/pdf"]

    for _filename, _ct, data in images:
        pdf.add_page()
        pdf.image(io.BytesIO(data), x=18, y=24, w=pdf.w - 36)

    invoice_bytes = bytes(pdf.output())  # fpdf2 returns the PDF as bytes when no dest given

    writer = PdfWriter()
    for page in PdfReader(io.BytesIO(invoice_bytes)).pages:
        writer.add_page(page)
    for _filename, _ct, data in pdfs:
        for page in PdfReader(io.BytesIO(data)).pages:
            writer.add_page(page)
    with open(path, "wb") as fh:
        writer.write(fh)
```

> Receipts whose `content_type` is neither image nor PDF are silently skipped — only
> image and PDF receipts can be embedded. (Most receipts are PDFs or images.)

- [ ] **Step 6: Align the Step 2 test with the parameter form**

The test in Step 2 must build the decoded receipt list and pass it in:

```python
    decoded = [await expense_svc.get_receipt(str(exp.id)[:8])]
    with_r = render_pdf(view, settings, tmp_path / "yes.pdf", receipts=decoded)
    without = render_pdf(view, settings, tmp_path / "no.pdf", receipts=None)
    assert len(PdfReader(str(with_r)).pages) > len(PdfReader(str(without)).pages)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/test_invoicing/test_expense_render.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock src/ttd/config/schema.py src/ttd/invoicing/pdf.py src/ttd/services/invoicing.py tests/test_invoicing/test_expense_render.py
git commit -m "feat: append expense receipts to invoice PDFs (opt-in)"
```

---

## Task 9: CLI invoices — format choice + receipts + markdown gating

**Files:**
- Modify: `src/ttd/cli/invoices.py`
- Test: `tests/test_invoicing/test_expense_render.py` (append a gating unit test on a helper)

**Interfaces:**
- Consumes: `invoice_has_receipts`, `get_receipt`, `render_pdf(..., receipts=...)`, `settings.invoice.attach_receipts`.
- Produces: updated `create`/`render` commands — default PDF, `--receipts` flag, markdown disabled (hard error) when receipts present.

- [ ] **Step 1: Write the failing test (gating helper)**

Factor the gating decision into a pure helper so it's unit-testable without invoking Cyclopts:

```python
# tests/test_invoicing/test_expense_render.py (append)
import pytest
from ttd.cli.invoices import _resolve_formats
from ttd.core.errors import TtdError


def test_resolve_formats_defaults_to_pdf():
    assert _resolve_formats(pdf=False, md=False, receipts=False, has_receipts=False) == (True, False)


def test_resolve_formats_md_blocked_when_receipts_present():
    with pytest.raises(TtdError):
        _resolve_formats(pdf=False, md=True, receipts=True, has_receipts=True)


def test_resolve_formats_md_ok_when_no_receipts_on_invoice():
    assert _resolve_formats(pdf=True, md=True, receipts=True, has_receipts=False) == (True, True)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_invoicing/test_expense_render.py -k resolve_formats -v`
Expected: FAIL — `ImportError: cannot import name '_resolve_formats'`.

- [ ] **Step 3: Add the gating helper**

In `src/ttd/cli/invoices.py`:

```python
def _resolve_formats(*, pdf: bool, md: bool, receipts: bool, has_receipts: bool) -> tuple[bool, bool]:
    """Decide which formats to render. Default to PDF; block markdown when an
    invoice carries receipts (markdown can't render them)."""
    if not pdf and not md:
        pdf = True  # default to the canonical, sendable artifact
    if md and receipts and has_receipts:
        raise TtdError(
            "This invoice has receipts; Markdown can't render them. "
            "Drop --md, or omit --receipts to generate Markdown without them."
        )
    return pdf, md
```

- [ ] **Step 4: Wire receipts + formats into `_render_files`**

Rewrite `_render_files` to take the resolved flags and load receipts when asked:

```python
async def _render_files(
    view: svc.InvoiceView, *, pdf: bool, md: bool, receipts: bool, out: Path | None
) -> None:
    settings = get_settings()
    stem = _output_paths(view, out)
    if pdf:
        decoded = None
        if receipts:
            from ttd.services import expenses as expense_svc

            decoded = []
            for line in view.expense_lines:
                got = await expense_svc.get_receipt(str(line.expense_id)[:8])
                if got is not None:
                    decoded.append(got)
        path = render_pdf(view, settings, stem.with_suffix(".pdf"), receipts=decoded)
        success(f"Wrote {path}")
    if md:
        path = write_markdown(view, settings, stem.with_suffix(".md"))
        success(f"Wrote {path}")
```

- [ ] **Step 5: Update `create` and `render` commands**

In both `create` and `render`, add a `receipts` parameter and call the gating helper. For `create` (after `view` is obtained):

```python
    receipts_on = receipts or settings.invoice.attach_receipts
    has_r = await svc.invoice_has_receipts(view)
    pdf, md = _resolve_formats(pdf=pdf, md=md, receipts=receipts_on, has_receipts=has_r)
    await _render_files(view, pdf=pdf, md=md, receipts=receipts_on, out=out)
```

Add the flag to the signature of both commands:

```python
    receipts: Annotated[bool, Parameter(help="Append expense receipts to the PDF")] = False,
```

For `render`, remove the old `if not pdf and not md: pdf = md = True` line — `_resolve_formats` now owns the default. Load the view first, compute `has_r`, then resolve and render.

> `_render_files` is now async and awaited; ensure both call sites `await` it (they're already inside `@with_db` async commands).

- [ ] **Step 6: Run tests + full suite**

Run: `uv run pytest tests/test_invoicing -v && uv run ty check && uv run ruff check src/ttd/cli/invoices.py`
Expected: PASS, clean.

- [ ] **Step 7: Commit**

```bash
git add src/ttd/cli/invoices.py tests/test_invoicing/test_expense_render.py
git commit -m "feat: invoice format choice (default PDF) with receipt-aware markdown gating"
```

---

## Task 10: JSON backup — expenses + receipts (envelope v2)

**Architecture note (verified):** Export flows `export_records() -> (records, meta)`, then
the CLI calls `fmt_obj.writer(records, path, meta)`. `meta` already carries
`clients`/`projects`; we add `expenses`/`receipts` to it, and only `write_json` reads them
(CSV/XLSX/Numbers writers ignore the extra keys). Import flows through
`importer.build_plan`/`apply_plan`, which are **`EntryRecord`-only**. Expenses therefore get
a **separate restore function**, not a shoehorn into `ImportPlan`. The JSON `meta` is read
back via `json_io.read_metadata`.

**Files:**
- Modify: `src/ttd/services/interchange_svc.py` (`export_records` adds expenses/receipts to meta)
- Modify: `src/ttd/interchange/json_io.py` (envelope v2 + `read_metadata`)
- Modify: `src/ttd/interchange/importer.py` (add `restore_expenses`)
- Modify: `src/ttd/cli/import_.py` (call `restore_expenses` for JSON files)
- Test: `tests/test_interchange/test_expense_backup.py`

**Interfaces:**
- Consumes: `Expense`, `ExpenseReceipt` (Task 1); `list_expenses` (Task 2); `read_metadata` (existing).
- Produces:
  - `export_records(...)` meta gains `"expenses": list[dict]` and `"receipts": list[dict]`.
  - `ENVELOPE_VERSION = 2`; `read_metadata` returns `expenses`/`receipts` (empty for v1).
  - `async importer.restore_expenses(metadata, *, on_conflict="skip", create_missing=False) -> int`

- [ ] **Step 1: Write the failing test (through the real seams)**

```python
# tests/test_interchange/test_expense_backup.py
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
    src = tmp_path / "r.pdf"; src.write_bytes(b"%PDF-1.4\n\xff")
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
    p = tmp_path / "v1.json"; p.write_text(json.dumps(payload))
    written = await restore_expenses(json_io.read_metadata(p), create_missing=True)
    assert written == 0
    assert await Expense.all() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_interchange/test_expense_backup.py -v`
Expected: FAIL — `KeyError: 'expenses'` (meta has no expenses) / `ImportError` for `restore_expenses`.

- [ ] **Step 3: Add expenses + receipts to the export meta**

In `src/ttd/services/interchange_svc.py`, import the new models and expense service, then
extend the returned meta. After building `projects_meta`, add:

```python
from ttd.services.expenses import list_expenses          # add import
from ttd.storage.models import Client, Expense, ExpenseReceipt, Invoice, Project  # extend

    # ... after projects_meta, before the return ...
    expense_views = await list_expenses(
        project_slug=project_slug, client_slug=client_slug,
        date_from=date_from, date_to=date_to,
    )
    invoice_numbers = {i.id: i.number for i in await Invoice.all()}
    expenses_meta = [
        {
            "id": str(v.expense.id),
            "client": v.client.slug,
            "project": v.project.slug,
            "incurred_date": v.expense.incurred_date.isoformat(),
            "description": v.expense.description,
            "amount": str(v.expense.amount),
            "note": v.expense.note,
            "invoice_number": invoice_numbers.get(v.expense.invoice_id, "")
            if v.expense.invoice_id else "",
        }
        for v in expense_views
    ]
    expense_ids = {str(v.expense.id) for v in expense_views}
    receipts_meta = [
        {
            "expense_id": str(r.expense_id),
            "filename": r.filename,
            "content_type": r.content_type,
            "data_b64": r.data_b64,
        }
        for r in await ExpenseReceipt.all()
        if str(r.expense_id) in expense_ids
    ]
    return records, {
        "clients": clients_meta,
        "projects": projects_meta,
        "expenses": expenses_meta,
        "receipts": receipts_meta,
    }
```

(Replace the existing `return records, {"clients": ..., "projects": ...}` with the above.)

- [ ] **Step 4: Extend the JSON envelope**

In `src/ttd/interchange/json_io.py`, bump version and write/read the new keys:

```python
ENVELOPE_VERSION = 2


def write_json(records, path, meta):
    payload = {
        "ttd_export": ENVELOPE_VERSION,
        "clients": meta.get("clients", []),
        "projects": meta.get("projects", []),
        "entries": [
            {**r.to_cells(), "seconds": r.seconds, "billable": r.billable} for r in records
        ],
        "expenses": meta.get("expenses", []),
        "receipts": meta.get("receipts", []),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
```

In `read_metadata`, return the new keys (empty lists for v1 files):

```python
    if isinstance(payload, dict):
        return {
            "clients": payload.get("clients", []),
            "projects": payload.get("projects", []),
            "expenses": payload.get("expenses", []),
            "receipts": payload.get("receipts", []),
        }
```

- [ ] **Step 5: Add `restore_expenses` to the importer**

In `src/ttd/interchange/importer.py`, following the `_create_missing` pattern (resolve
project by `(client, project)` slug, create missing clients/projects from metadata):

```python
from datetime import date as date_t  # add to imports
from ttd.storage.models import Expense, ExpenseReceipt  # add


async def restore_expenses(
    metadata: dict[str, Any],
    *,
    on_conflict: OnConflict = "skip",
    create_missing: bool = False,
) -> int:
    """Restore expenses + receipts from a JSON backup's metadata. Returns count written.

    Never sets ``invoice_id`` — imports keep ``invoice_number`` informational only,
    mirroring entry import.
    """
    expenses = metadata.get("expenses", [])
    if not expenses:
        return 0

    if create_missing:
        # reuse the client/project bootstrap by faking a plan of the referenced pairs
        plan = ImportPlan()
        existing_clients = {c.slug for c in await Client.all()}
        projects_present = set()
        for p in await Project.all():
            cslug = next((c.slug for c in await Client.all() if c.id == p.client_id), None)
            if cslug:
                projects_present.add((cslug, p.slug))
        for row in expenses:
            if row["client"] not in existing_clients:
                plan.missing_clients.add(row["client"])
            if (row["client"], row["project"]) not in projects_present:
                plan.missing_projects.add((row["client"], row["project"]))
        if plan.missing_clients or plan.missing_projects:
            await _create_missing(plan, metadata)

    clients = {c.slug: c for c in await Client.all()}
    project_map = {}
    for p in await Project.all():
        cslug = next((s for s, c in clients.items() if c.id == p.client_id), None)
        project_map[(cslug, p.slug)] = p

    existing = {str(e.id): e for e in await Expense.all()}
    stamp = datetime.now()
    written = 0
    for row in expenses:
        key = (row["client"], row["project"])
        if key not in project_map:
            continue  # unresolved project; skip silently (create_missing handles real ones)
        project = project_map[key]
        match = existing.get(row["id"])
        if match is not None and match.invoice_id is not None:
            continue  # never touch invoiced expenses
        if match is not None and on_conflict == "skip":
            continue
        if match is not None and on_conflict == "update":
            match.project_id = pk(project)
            match.incurred_date = date_t.fromisoformat(row["incurred_date"])
            match.description = row["description"]
            match.amount = Decimal(row["amount"])
            match.note = row.get("note", "")
            match.updated_at = stamp
            await match.save()
        else:  # new (or duplicate)
            from uuid import UUID
            await Expense(
                id=UUID(row["id"]),
                project_id=pk(project),
                incurred_date=date_t.fromisoformat(row["incurred_date"]),
                description=row["description"],
                amount=Decimal(row["amount"]),
                note=row.get("note", ""),
                created_at=stamp,
                updated_at=stamp,
            ).save()
        written += 1

    # receipts (replace any existing for that expense)
    valid_ids = {row["id"] for row in expenses}
    for r in metadata.get("receipts", []):
        if r["expense_id"] not in valid_ids:
            continue
        from uuid import UUID, uuid4
        for old in await ExpenseReceipt.where(
            lambda rec, eid=UUID(r["expense_id"]): rec.expense_id == eid
        ).all():
            await old.delete()
        await ExpenseReceipt(
            id=uuid4(),
            expense_id=UUID(r["expense_id"]),
            filename=r["filename"],
            content_type=r["content_type"],
            data_b64=r["data_b64"],
        ).save()
    return written
```

> Move the `from uuid import UUID, uuid4` imports to the top of the file instead of inline;
> they're inline here only to keep the diff localized in the plan.

- [ ] **Step 6: Wire into the import CLI**

In `src/ttd/cli/import_.py`, after `apply_plan(...)` runs, restore expenses when the file
carried them. Read the existing import command to match its variable names; the addition is:

```python
    from ttd.interchange.importer import restore_expenses
    from ttd.interchange.json_io import read_metadata

    metadata = read_metadata(path)  # empty dict for non-JSON formats
    if metadata.get("expenses"):
        n = await restore_expenses(metadata, on_conflict=on_conflict, create_missing=create_missing)
        if n:
            success(f"Restored {n} expense{'s' if n != 1 else ''}")
```

(Place it inside the existing `@with_db` import command, using its `on_conflict`/`create_missing`/`path` variables. Skip during `--dry-run`.)

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/test_interchange -v`
Expected: PASS (new + existing interchange tests green).

- [ ] **Step 8: Commit**

```bash
git add src/ttd/interchange/ src/ttd/services/interchange_svc.py src/ttd/cli/import_.py tests/test_interchange/test_expense_backup.py
git commit -m "feat: include expenses and receipts in JSON backup (envelope v2)"
```

---

## Task 11: TUI — invoice detail expenses + quick-add

**Files:**
- Modify: `src/ttd/tui/_data.py`
- Modify: `src/ttd/tui/screens/invoices.py`
- Modify: `src/ttd/tui/screens/timesheet.py` (or dashboard) for quick-add binding
- Test: `tests/test_tui/test_expense_data.py`

**Interfaces:**
- Consumes: `expense_svc`, `invoicing.get_invoice` (`InvoiceView.expense_lines`).
- Produces: `_data` read helpers for expenses; invoice detail shows an expenses table; a quick-add keybinding (`e`) opens an expense form.

- [ ] **Step 1: Inspect TUI data + invoice screen patterns**

Run: `uv run grep -rn "def \|BINDINGS\|DataTable" src/ttd/tui/_data.py src/ttd/tui/screens/invoices.py | head -60`
Read both files to learn the exact data-access and screen-composition patterns (the screens call `_data` helpers, which wrap services in a DB session).

- [ ] **Step 2: Write the failing test (data helper)**

TUI widgets are hard to unit test; cover the data helper that the screen consumes.

```python
# tests/test_tui/test_expense_data.py
from datetime import date
from decimal import Decimal

from ttd.services import clients as client_svc
from ttd.services import expenses as expense_svc
from ttd.services import projects as project_svc
from ttd.tui import _data


async def test_recent_expense_choices(db):
    await client_svc.create_client("Acme Corp", hourly_rate=Decimal("150"))
    await project_svc.create_project("API Rewrite", "acme-corp")
    await expense_svc.add_expense(
        "api-rewrite", "Claude Code", Decimal("100"), incurred_date=date(2026, 6, 15)
    )
    suggestions = await _data.recent_expense_suggestions(project_slug="api-rewrite")
    assert [(s.description, s.amount) for s in suggestions] == [("Claude Code", Decimal("100"))]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_tui/test_expense_data.py -v`
Expected: FAIL — `AttributeError: module 'ttd.tui._data' has no attribute 'recent_expense_suggestions'`.

- [ ] **Step 4: Add the data helpers**

In `src/ttd/tui/_data.py`, following the existing helper pattern (wrap in the DB session the file already uses):

```python
async def recent_expense_suggestions(*, project_slug=None, client_slug=None, limit=8):
    from ttd.services import expenses as expense_svc

    return await expense_svc.recent_expenses(
        project_slug=project_slug, client_slug=client_slug, limit=limit
    )


async def expenses_for_invoice(view):
    # view.expense_lines is already loaded by get_invoice; this is a thin accessor
    return view.expense_lines
```

- [ ] **Step 5: Show expenses in the invoice detail screen**

In `src/ttd/tui/screens/invoices.py`, where the invoice detail renders the line-items `DataTable`, add a second table (or section) populated from `view.expense_lines` with columns Date / Description / Amount, shown only when non-empty. Follow the existing table-building code in that screen verbatim for styling.

- [ ] **Step 6: Add quick-add binding**

In the timesheet (or dashboard) screen, add a binding `("e", "quick_expense", "Expense")` and an `action_quick_expense` that opens a modal form: project picker → optional recall select (from `recent_expense_suggestions`) → description/amount/date, then calls `expense_svc.add_expense` and refreshes. Mirror the existing quick-log modal in the same screen.

- [ ] **Step 7: Run tests + TUI smoke**

Run: `uv run pytest tests/test_tui -v`
Expected: PASS. Optional manual: `just tui` (or `uv run ttd`), seed demo, open Invoices, confirm an expense-bearing invoice shows the expenses table; press `e` to add one.

- [ ] **Step 8: Commit**

```bash
git add src/ttd/tui/ tests/test_tui/test_expense_data.py
git commit -m "feat: TUI invoice expenses view and quick-add"
```

---

## Final verification

- [ ] **Run the full suite + lint:**

Run: `just test && just lint`
Expected: all tests pass; ruff + ty clean.

- [ ] **Regenerate CLI docs** (pre-commit hook `cli reference docs` runs this; do it explicitly if needed):

Run: `uv run python scripts/gen_cli_docs.py` (confirm exact script entrypoint), then commit any doc changes.

- [ ] **Update CHANGELOG.md** with a `feat: billable expenses (client chargebacks)` entry under the next version.

- [ ] **Commit docs:**

```bash
git add CHANGELOG.md docs/
git commit -m "docs: document billable expenses"
```

---

## Self-Review Notes (coverage against the spec)

- **Data model** → Task 1 (Expense, ExpenseReceipt, InvoiceExpenseLine, `expenses_subtotal`).
- **Services CRUD + recall** → Task 2; **receipts** → Task 3.
- **CLI** (`expense` sub-app, receipt group) → Task 4; interactive recall flagged as fold-in.
- **Invoicing: draft/persist/untaxed totals** → Task 5; **void/refresh** → Task 6.
- **Rendering: PDF/markdown expense section** → Task 7; **receipt pages + config + pypdf** → Task 8.
- **Invoice generation: format choice + `--receipts` + markdown gating** → Task 9.
- **JSON backup v2** → Task 10 (verified against the real `export_records`/`meta` export path and the `EntryRecord`-only importer; expenses get a dedicated `restore_expenses` rather than reusing `ImportPlan`).
- **TUI** → Task 11. The data helper is TDD'd concretely; the screen/keybinding wiring is descriptive by necessity (Textual widgets aren't unit-testable here) and instructs the implementer to mirror the existing invoice-detail table and quick-log modal verbatim.
- **Deferred (not in this plan, per spec):** reports awareness, CSV/XLSX/Numbers interchange, dedicated TUI expenses screen, recurrence, markup.
- **Receipt rendering wiring (resolved):** the CLI loads receipts via `get_receipt` inside its async session and passes them to `render_pdf(..., receipts=[(filename, content_type, bytes), ...])`. The renderer never touches the DB — image receipts become fpdf2 pages, PDF receipts are merged with `pypdf`.
- **Cross-task type consistency checked:** `_draft_totals` returns `(subtotal, expenses_subtotal, tax, total)` everywhere; `Draft`/`InvoiceView`/`RefreshPreview` gain expense fields used consistently by later tasks; `render_pdf`'s `receipts` keyword is introduced in Task 8 and consumed in Task 9; `_render_files` becomes async with both call sites updated.
