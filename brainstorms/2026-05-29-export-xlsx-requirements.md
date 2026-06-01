---
date: 2026-05-29
topic: export-xlsx
origin: M3 export follow-up (dogfooding)
---

# Export XLSX (two-sheet workbook)

## Summary

Add optional XLSX period export alongside M3 CSV. Format is inferred from `--output` file extension (`.csv` or `.xlsx`); no `--format` flag. Workbook contains two sheets — **Log** and **Summary** — using the same column schemas as the corresponding CSV blocks (including `row_type`).

---

## Problem Frame

M3 CSV combines detail and summary blocks in one file with different column sets, separated by a blank row. That works for scripting but is awkward in Excel. A two-sheet XLSX presents the same data in a familiar review layout without changing billing logic or column semantics.

---

## Requirements

- R1. `ttd export` writes **CSV** when `--output` ends with `.csv` or when `--output` is omitted (stdout).
- R2. `ttd export` writes **XLSX** when `--output` ends with `.xlsx`.
- R3. **No `--format` flag** — extension is the only format selector.
- R4. XLSX requires `--output`; omitting `--output` always emits CSV to stdout.
- R5. Unsupported extensions raise a clear validation error.
- R6. **Log** sheet columns match the M3 CSV detail block exactly (including `row_type=DETAIL`).
- R7. **Summary** sheet columns match the M3 CSV summary block exactly (including `row_type=SUMMARY`).
- R8. Export uses the same core transform pipeline as CSV (load → detail rows → summary rows); only serialization differs.
- R9. Empty period: Log sheet has detail headers only; Summary sheet has summary headers only (no data rows), matching CSV empty behavior.
- R10. When detail rows exist but summary totals are empty, Summary sheet has headers only (no summary data rows), matching CSV.

---

## Scope Boundaries

- Google Sheets / Numbers-specific formatting — out of scope
- Multiple clients as separate sheets — out of scope
- Changing CSV combined-file shape — out of scope
- PDF/Markdown invoices — M6

---

## Key Decisions

- **Extension inference** over explicit `--format` — fewer flags; path carries intent.
- **Preserve `row_type`** on both sheets — same schema as CSV blocks; no column renaming.
- **Sheet names:** `Log`, `Summary`.

---

## Success Criteria

- Dogfooding: `ttd export ... --output period.xlsx` opens in Excel/Numbers with line items on Log and totals on Summary.
- CSV export behavior unchanged for stdout and `.csv` paths.
