# TUI Invoice Render Format Modal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the TUI invoice render step (`e`) prompt for format, embed receipts in the PDF, and lock out Markdown when receipts are included — matching the CLI.

**Architecture:** Extract the CLI's inline receipt-loading into one shared service helper. Add a bespoke `RenderFormatModal` (PDF/Markdown/Receipts switches with live reactivity) and rewire `action_render_files` to use it, passing decoded receipts to `render_pdf`.

**Tech Stack:** Python 3.13, Textual (TUI: `ModalScreen`, `Switch`), Ferro-ORM/SQLite, pytest + pytest-asyncio (Textual pilot).

## Global Constraints

- Fix lives entirely in the render step (`e`); TUI invoice **creation stays persist-only** (unchanged).
- Bespoke modal (not the generic `FormModal`) because of live inter-switch reactivity.
- **Receipts** switch is disabled unless the invoice has ≥1 receipt; default on when available.
- Turning **Receipts on** forces **PDF on** and disables + clears **Markdown**; turning it off re-enables Markdown.
- Submit requires ≥1 format selected.
- PDF embeds receipts (decoded) only when the Receipts switch is on.
- One shared `load_invoice_receipts` used by both CLI and TUI (DRY); CLI user-facing behavior unchanged.
- Coverage gate `fail_under = 84` stays green; `ty` + `ruff` clean; avoid non-ASCII code literals (RUF001).

## File Structure

- **Modify:** `src/ttd/services/expenses.py` — add `load_invoice_receipts` (Task 1).
- **Modify:** `src/ttd/cli/invoices.py` — call the shared helper in `_render_files` (Task 1).
- **Modify:** `src/ttd/tui/screens/invoices.py` — `RenderFormatModal`, `_write_selected_formats`, rewired `action_render_files`, `Switch` import, binding label (Task 2).
- **Create:** `tests/test_storage/test_expenses.py` additions or `tests/test_invoicing/test_render_helper.py` — `load_invoice_receipts` unit test (Task 1).
- **Create:** `tests/test_tui/test_render_modal.py` — modal reactivity pilot tests + `_write_selected_formats` unit test (Task 2).

---

## Task 1: Shared `load_invoice_receipts` helper (DRY)

**Files:**
- Modify: `src/ttd/services/expenses.py`
- Modify: `src/ttd/cli/invoices.py`
- Test: `tests/test_invoicing/test_render_helper.py` (create)

**Interfaces:**
- Consumes: `get_receipt` (existing, in `services/expenses.py`); `InvoiceExpenseLine.expense_id`.
- Produces: `async load_invoice_receipts(expense_lines) -> list[tuple[str, str, bytes]]` — decoded `(filename, content_type, bytes)` for each expense line that has a receipt, in line order.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_invoicing/test_render_helper.py
from datetime import date
from decimal import Decimal

from ttd.services import clients as client_svc
from ttd.services import expenses as expense_svc
from ttd.services import invoicing as svc
from ttd.services import projects as project_svc
from ttd.reporting import periods


async def _invoice_with_receipt(db, tmp_path):
    await client_svc.create_client("Acme Corp", hourly_rate=Decimal("150"))
    await project_svc.create_project("API Rewrite", "acme-corp")
    exp = await expense_svc.add_expense(
        "api-rewrite", "Claude", Decimal("100"), incurred_date=date(2026, 6, 15)
    )
    rp = tmp_path / "r.pdf"
    rp.write_bytes(b"%PDF-1.4\n\xff\xd8 binary")
    await expense_svc.add_receipt(str(exp.id)[:8], rp)
    period = periods.range_period(date(2026, 6, 1), date(2026, 6, 30))
    from ttd.config.schema import Settings
    invoice = await svc.persist_draft(await svc.build_draft("acme-corp", period, Settings()), Settings())
    return await svc.get_invoice(invoice.number)


async def test_load_invoice_receipts_returns_decoded(db, tmp_path):
    view = await _invoice_with_receipt(db, tmp_path)
    receipts = await expense_svc.load_invoice_receipts(view.expense_lines)
    assert len(receipts) == 1
    filename, content_type, data = receipts[0]
    assert filename == "r.pdf"
    assert content_type == "application/pdf"
    assert data == b"%PDF-1.4\n\xff\xd8 binary"


async def test_load_invoice_receipts_empty_when_none(db):
    assert await expense_svc.load_invoice_receipts([]) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_invoicing/test_render_helper.py -v`
Expected: FAIL — `AttributeError: module 'ttd.services.expenses' has no attribute 'load_invoice_receipts'`.

- [ ] **Step 3: Add the helper**

In `src/ttd/services/expenses.py`, add (near `get_receipt`):

```python
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
```

- [ ] **Step 4: Use it in the CLI (behavior-preserving)**

In `src/ttd/cli/invoices.py`, `_render_files`, replace the inline receipt-loading:

```python
    if pdf:
        decoded = None
        if receipts:
            from ttd.services.expenses import load_invoice_receipts

            decoded = await load_invoice_receipts(view.expense_lines)
        path = render_pdf(view, settings, stem.with_suffix(".pdf"), receipts=decoded)
        success(f"Wrote {path}")
```

(Removes the inline `for line in view.expense_lines: get_receipt(...)` loop.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_invoicing/test_render_helper.py tests/test_cli -v && uv run pytest -q && uv run ty check && uv run ruff check`
Expected: PASS, full suite green (coverage ≥84%), clean. (The CLI receipt tests still pass — behavior is unchanged.)

- [ ] **Step 6: Commit**

```bash
git add src/ttd/services/expenses.py src/ttd/cli/invoices.py tests/test_invoicing/test_render_helper.py
git commit -m "refactor: shared load_invoice_receipts helper for CLI and TUI"
```

---

## Task 2: RenderFormatModal + rewire the TUI render action

**Files:**
- Modify: `src/ttd/tui/screens/invoices.py`
- Test: `tests/test_tui/test_render_modal.py` (create)

**Interfaces:**
- Consumes: `load_invoice_receipts` (Task 1); `svc.invoice_has_receipts`, `svc.get_invoice`, `render_pdf`, `write_markdown` (existing).
- Produces: `RenderFormatModal(has_receipts: bool)` returning `{"pdf": bool, "md": bool, "receipts": bool} | None`; module-level `async _write_selected_formats(view, settings, choice) -> list[str]` (returns the names written); rewired `action_render_files`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_tui/test_render_modal.py
from datetime import date
from decimal import Decimal

import pytest
from textual.widgets import Switch

from ttd.config.schema import InvoiceConfig, Settings, StorageConfig
from tests.test_tui._db import open_test_db


@pytest.fixture
async def app_and_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("TTD_DB_PATH", str(tmp_path / "tui.db"))
    monkeypatch.setenv("TTD_CONFIG_DIR", str(tmp_path / "config"))
    from ttd.tui.app import TtdApp
    return TtdApp()


async def test_modal_receipts_on_disables_markdown(app_and_settings):
    from ttd.tui.screens.invoices import RenderFormatModal
    app = app_and_settings
    async with app.run_test(size=(120, 40)) as pilot:
        app.push_screen(RenderFormatModal(has_receipts=True))
        await pilot.pause()
        modal = app.screen
        assert isinstance(modal, RenderFormatModal)
        # receipts enabled + on; markdown disabled at start (receipts default on)
        assert modal.query_one("#receipts", Switch).disabled is False
        assert modal.query_one("#receipts", Switch).value is True
        assert modal.query_one("#md", Switch).disabled is True
        # turn receipts off -> markdown re-enabled
        modal.query_one("#receipts", Switch).value = False
        await pilot.pause()
        assert modal.query_one("#md", Switch).disabled is False


async def test_modal_no_receipts_disables_receipts_switch(app_and_settings):
    from ttd.tui.screens.invoices import RenderFormatModal
    app = app_and_settings
    async with app.run_test(size=(120, 40)) as pilot:
        app.push_screen(RenderFormatModal(has_receipts=False))
        await pilot.pause()
        modal = app.screen
        assert modal.query_one("#receipts", Switch).disabled is True
        assert modal.query_one("#md", Switch).disabled is False


async def test_write_selected_formats_pdf_with_receipts(db, tmp_path):
    # build an invoice whose expense has a receipt, then render via the helper
    from ttd.services import clients as client_svc
    from ttd.services import expenses as expense_svc
    from ttd.services import invoicing as svc
    from ttd.services import projects as project_svc
    from ttd.reporting import periods
    from ttd.tui.screens.invoices import _write_selected_formats
    from pypdf import PdfReader

    await client_svc.create_client("Acme Corp", hourly_rate=Decimal("150"))
    await project_svc.create_project("API Rewrite", "acme-corp")
    exp = await expense_svc.add_expense("api-rewrite", "Claude", Decimal("100"), incurred_date=date(2026, 6, 15))
    from fpdf import FPDF
    rp = tmp_path / "r.pdf"
    r = FPDF(); r.add_page(); r.set_font("helvetica", size=12); r.cell(0, 10, "RECEIPT"); r.output(str(rp))
    await expense_svc.add_receipt(str(exp.id)[:8], rp)
    period = periods.range_period(date(2026, 6, 1), date(2026, 6, 30))
    settings = Settings(invoice=InvoiceConfig(output_dir=tmp_path / "out"))
    invoice = await svc.persist_draft(await svc.build_draft("acme-corp", period, settings), settings)
    view = await svc.get_invoice(invoice.number)

    without = await _write_selected_formats(view, settings, {"pdf": True, "md": False, "receipts": False})
    base_pdf = tmp_path / "out" / f"{invoice.number}-acme-corp.pdf"
    base_pages = len(PdfReader(str(base_pdf)).pages)
    with_r = await _write_selected_formats(view, settings, {"pdf": True, "md": False, "receipts": True})
    assert len(PdfReader(str(base_pdf)).pages) > base_pages  # receipts appended
    assert any(name.endswith(".pdf") for name in with_r)


async def test_write_selected_formats_markdown(db, tmp_path):
    from ttd.services import clients as client_svc
    from ttd.services import expenses as expense_svc
    from ttd.services import invoicing as svc
    from ttd.services import projects as project_svc
    from ttd.reporting import periods
    from ttd.tui.screens.invoices import _write_selected_formats

    await client_svc.create_client("Acme Corp", hourly_rate=Decimal("150"))
    await project_svc.create_project("API Rewrite", "acme-corp")
    await expense_svc.add_expense("api-rewrite", "Claude", Decimal("100"), incurred_date=date(2026, 6, 15))
    period = periods.range_period(date(2026, 6, 1), date(2026, 6, 30))
    settings = Settings(invoice=InvoiceConfig(output_dir=tmp_path / "out"))
    invoice = await svc.persist_draft(await svc.build_draft("acme-corp", period, settings), settings)
    view = await svc.get_invoice(invoice.number)
    wrote = await _write_selected_formats(view, settings, {"pdf": False, "md": True, "receipts": False})
    assert (tmp_path / "out" / f"{invoice.number}-acme-corp.md").exists()
    assert any(name.endswith(".md") for name in wrote)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tui/test_render_modal.py -v`
Expected: FAIL — `ImportError: cannot import name 'RenderFormatModal'` / `_write_selected_formats`.

- [ ] **Step 3: Add the `Switch` import**

In `src/ttd/tui/screens/invoices.py`, add `Switch` to the `textual.widgets` import:

```python
from textual.widgets import Button, DataTable, Input, Label, Markdown, Static, Switch
```

- [ ] **Step 4: Add `RenderFormatModal`**

Add near the other modal classes in `src/ttd/tui/screens/invoices.py`:

```python
class RenderFormatModal(ModalScreen[dict | None]):
    """Choose which files to render. Receipts embed into the PDF and are only
    available when the invoice has receipts; enabling them locks out Markdown."""

    BINDINGS: ClassVar = [("escape", "dismiss(None)", "cancel")]

    def __init__(self, has_receipts: bool) -> None:
        super().__init__()
        self.has_receipts = has_receipts

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Label("render invoice", classes="modal-title")
            with Horizontal(classes="form-toggle-row"):
                yield Switch(value=True, id="pdf")
                yield Label("PDF", classes="field-label")
            with Horizontal(classes="form-toggle-row"):
                yield Switch(value=False, id="md", disabled=self.has_receipts)
                yield Label("Markdown", classes="field-label")
            with Horizontal(classes="form-toggle-row"):
                yield Switch(
                    value=self.has_receipts, id="receipts", disabled=not self.has_receipts
                )
                yield Label("Include receipts", classes="field-label")
            yield Static("", id="render-error", classes="form-error")
            with Horizontal(classes="modal-buttons"):
                yield Button("Render", variant="primary", id="render")
                yield Button("Cancel", id="cancel")

    @on(Switch.Changed, "#receipts")
    def _receipts_changed(self, event: Switch.Changed) -> None:
        md = self.query_one("#md", Switch)
        if event.value:
            self.query_one("#pdf", Switch).value = True
            md.value = False
            md.disabled = True
        else:
            md.disabled = False

    @on(Button.Pressed, "#render")
    def _render(self) -> None:
        pdf = self.query_one("#pdf", Switch).value
        md = self.query_one("#md", Switch).value
        receipts = self.query_one("#receipts", Switch).value
        if not pdf and not md:
            self.query_one("#render-error", Static).update("[red]Choose at least one format[/red]")
            return
        self.dismiss({"pdf": pdf, "md": md, "receipts": receipts})

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(None)
```

- [ ] **Step 5: Add `_write_selected_formats` and rewire `action_render_files`**

Add a module-level helper:

```python
async def _write_selected_formats(view: svc.InvoiceView, settings, choice: dict) -> list[str]:
    """Render the chosen formats; return the file names written."""
    from ttd.services.expenses import load_invoice_receipts

    stem = settings.invoice.output_dir / f"{view.invoice.number}-{view.client.slug}"
    wrote: list[str] = []
    if choice["pdf"]:
        decoded = await load_invoice_receipts(view.expense_lines) if choice["receipts"] else None
        render_pdf(view, settings, stem.with_suffix(".pdf"), receipts=decoded)
        n = len(decoded) if decoded else 0
        wrote.append(f"{stem.name}.pdf" + (f" (+{n} receipt{'s' if n != 1 else ''})" if n else ""))
    if choice["md"]:
        write_markdown(view, settings, stem.with_suffix(".md"))
        wrote.append(f"{stem.name}.md")
    return wrote
```

Replace `action_render_files`:

```python
    async def action_render_files(self) -> None:
        number = self._selected_number()
        if number is None:
            return
        settings = get_settings()
        view = await svc.get_invoice(number)
        has_receipts = await svc.invoice_has_receipts(view)

        async def _render(choice: dict | None) -> None:
            if choice is None:
                return
            wrote = await _write_selected_formats(view, settings, choice)
            self.notify("wrote " + ", ".join(wrote), title="rendered")

        self.app.push_screen(RenderFormatModal(has_receipts), _render)
```

Change the `e` binding label:

```python
        ("e", "render_files", "render"),
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_tui/test_render_modal.py -v && uv run pytest -q && uv run ty check && uv run ruff check`
Expected: PASS, full suite green (coverage ≥84%), clean.

- [ ] **Step 7: Commit**

```bash
git add src/ttd/tui/screens/invoices.py tests/test_tui/test_render_modal.py
git commit -m "feat: TUI invoice render format modal with receipts and md gating"
```

---

## Self-Review Notes (coverage against the spec)

- Shared receipt loader (DRY, CLI + TUI) → **Task 1** (`load_invoice_receipts`).
- `RenderFormatModal` with the switch reactivity + receipts-disabled-unless-present + receipts-on-locks-md + submit validation → **Task 2**.
- Rewired `action_render_files` passing decoded receipts to `render_pdf`; binding label "render" → **Task 2**.
- Tests: helper unit (Task 1); modal reactivity pilot + format-writing unit (Task 2). The receipt-embedding-in-PDF behavior is verified via `_write_selected_formats` (page-count grows) rather than a fragile full keystroke pilot — the risky logic (reactivity, receipt loading, format dispatch) is all covered; only the trivial `push_screen` glue in `action_render_files` is exercised indirectly.
- Creation stays persist-only (untouched) — per spec, out of scope.
- **Type consistency:** `load_invoice_receipts(expense_lines) -> list[tuple[str,str,bytes]]` is used by both the CLI `_render_files` and the TUI `_write_selected_formats`; the modal returns `{"pdf","md","receipts"}` consumed by `_write_selected_formats`.
- **Verify during impl:** confirm `Settings(invoice=InvoiceConfig(output_dir=...))` constructs cleanly (InvoiceConfig with an explicit `output_dir`); if the field validator requires a `Path`, pass a `Path`. Confirm `_write_selected_formats`'s `settings` param type — it's the app `Settings`; annotate as `Settings` if imported, else leave untyped to avoid an import cycle.
