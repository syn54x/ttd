# TUI Invoice Render Format Modal — Design

**Status:** Approved design, pre-implementation
**Date:** 2026-07-01
**Branch:** feat/billable-expenses (depends on the receipt + CLI render logic there)
**Scope:** Bring the TUI invoice render step to parity with the CLI — explicit format choice, receipt inclusion, and markdown gating.

## Problem

The TUI invoice render action (`e` on the invoices screen, `action_render_files`) is broken relative to the CLI:

1. It always renders **both** PDF and Markdown — never asks which format.
2. It calls `render_pdf(view, settings, path)` with **no `receipts=` argument**, so an invoice's receipts are never embedded in the TUI-rendered PDF.
3. There is no way to gate Markdown when the invoice has receipts (Markdown can't carry them).

The CLI already solved this (`_resolve_formats`, `--receipts`, `render_pdf(..., receipts=…)`, `invoice_has_receipts`, per-expense `get_receipt`), but none of it is wired into the TUI. TUI invoice **creation** only persists (no rendering), so the fix belongs entirely in the render step.

## Decisions (settled during brainstorming)

| Decision | Choice |
|---|---|
| Where the choice lives | The render step (`e`) only. Creation stays persist-only. |
| UI | An explicit **toggle form** (bespoke modal), not an adaptive picker. |
| Receipts control | A **Receipts** switch, **disabled unless the invoice has ≥1 receipt**. |
| Receipts ↔ Markdown | When Receipts is on, **Markdown is disabled** (can't render receipts); turning Receipts on also forces PDF on. |

## The `RenderFormatModal`

A new `ModalScreen[dict | None]` (in `src/ttd/tui/screens/invoices.py`) with three switches and Render/Cancel buttons:

- **PDF** switch — default **on**.
- **Markdown** switch — default **off**.
- **Receipts** switch — **disabled unless `has_receipts`**; default **on** when `has_receipts`, else off.

Constructor: `RenderFormatModal(has_receipts: bool)`.

Live reactivity (via `@on(Switch.Changed)`):
- **Receipts → on:** set PDF on; set Markdown off and `disabled=True`.
- **Receipts → off:** set Markdown `disabled=False` (re-enable).

Submit (Render button / enter):
- Validate at least one of PDF/Markdown is on; if neither, show an inline error and stay open.
- Dismiss with `{"pdf": bool, "md": bool, "receipts": bool}`.

Escape / Cancel dismisses with `None`.

Because the Receipts switch starts disabled when there are no receipts, and is auto-cleared/locked against Markdown when on, the invalid combination (markdown + receipts) is unreachable through the UI. Submit still validates format presence defensively.

## Rewiring `action_render_files` (`e`)

```
view = await svc.get_invoice(number)
has_receipts = await svc.invoice_has_receipts(view)
push RenderFormatModal(has_receipts) with callback:
    if result is None: return
    stem = settings.invoice.output_dir / f"{number}-{client.slug}"
    if result["pdf"]:
        receipts = await load_invoice_receipts(view) if result["receipts"] else None
        render_pdf(view, settings, stem.with_suffix(".pdf"), receipts=receipts)
    if result["md"]:
        write_markdown(view, settings, stem.with_suffix(".md"))
    notify what was written (formats + receipt count)
```

The `e` binding label changes from `"render pdf+md"` to `"render"`.

## Shared receipt loading (DRY)

The CLI `_render_files` currently inlines "for each expense line, `get_receipt(...)`, collect the decoded `(filename, content_type, bytes)` list". Extract this into a single helper — e.g. `async def load_invoice_receipts(view) -> list[tuple[str, str, bytes]]` (in `services/expenses.py` or `services/invoicing.py`) — and call it from both the CLI and the new TUI path, so PDF-with-receipts is identical in both.

## Testing

- **Pilot (with receipts):** an invoice whose expense has a receipt → open the render modal via `e`; assert the Receipts switch is enabled and on and the Markdown switch is disabled; render PDF and assert the output PDF's page count exceeds the same invoice rendered without receipts (receipts embedded).
- **Pilot (no receipts):** the Receipts switch is disabled; Markdown is selectable; rendering Markdown writes the `.md`.
- **Live rule:** toggling Receipts on disables and clears Markdown.
- **Submit validation:** with neither format selected, submit does not dismiss (stays open / shows error).
- **Unit:** `load_invoice_receipts(view)` returns the decoded receipts for the invoice's expense lines and `[]`/None-equivalent when there are none; used by both CLI and TUI.
- Keep the coverage gate (`fail_under = 84`) green; `ty` + `ruff` clean.

## Out of scope

- Rendering at creation time (creation stays persist-only; decided in brainstorming).
- Any change to the CLI's user-facing behavior (only the internal receipt-loader is extracted for reuse).
- Attaching receipts from the TUI expense form (separate, still-deferred follow-up).

## Related

- Builds on the billable-expenses feature (PR #14): `render_pdf(..., receipts=…)`, `invoice_has_receipts`, `get_receipt`, and the CLI `_resolve_formats`/`_render_files` already exist.
