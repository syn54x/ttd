---
date: 2026-05-25
topic: export-period-close
origin: docs/roadmap.md (M3)
---

# M3 — Export & Period Close (CSV)

## Summary

Deliver period CSV export in `ttd.core` with a thin CLI command: flexible date-range filtering (client, project, or all), export-time rounding configured per client with project override (entry-level round-up to a configured increment; default no rounding), transformed rows that roll up duration entries per project-day-note while keeping interval entries as individual time-in/out rows, hourly projects with dollar amounts and fixed-price projects hours-only, and trailing period summary totals. Named billing schedules (monthly, bi-weekly, semi-monthly) are deferred; M3 uses explicit `--from` / `--to` ranges only.

---

## Problem Frame

M1 and M2 established a trustworthy ledger and terminal capture path. Dogfooding shows the remaining gap at period close: entries live in TTD, but **billable totals are still rebuilt in a spreadsheet** before invoicing. The product strategy promises one source of truth through export — without that, TTD replaces capture but not the error-prone assembly step. M3 closes that loop for tabular output: a CSV shape the solo developer trusts enough to invoice from, with rounding and rate rules applied consistently at export time while stored entry hours remain exact for later corrections.

---

## Actors

- A1. **Solo developer (ledger owner):** Closes a billing period, reviews CSV output, and uses it for invoicing without re-summing in a spreadsheet.
- A2. **Downstream implementer (M4+ surfaces):** Calls core export services from CLI, TUI, or API without reimplementing rounding, rollup, or rate logic.

---

## Key Flows

- F1. **Close a period for one client**
  - **Trigger:** Developer finishes a billing window and needs invoice-ready output for one customer.
  - **Actors:** A1
  - **Steps:** Choose date range → filter export to one client → core loads entries, applies client/project rounding at export, builds transformed rows and summary → CLI writes CSV to file or stdout.
  - **Outcome:** CSV contains self-contained rows for that client with correct hours and (for hourly projects) dollar amounts; spreadsheet sum step is unnecessary.
  - **Covered by:** R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R12, R13

- F2. **Export all clients for a date range**
  - **Trigger:** Developer wants a combined export across the ledger for the same period.
  - **Actors:** A1
  - **Steps:** Choose date range → export with no client filter (all clients in range) → receive CSV with client-identifying columns on every row plus summary totals grouped appropriately.
  - **Outcome:** One file covers the full period scope without manual merging.
  - **Covered by:** R1, R2, R11, R12, R13

- F3. **Review non-billable time alongside billable**
  - **Trigger:** Developer exported a period that includes internal or write-off entries flagged non-billable.
  - **Actors:** A1
  - **Steps:** Export period → non-billable rows appear with a billable flag → dollar columns omit non-billable amounts while hours remain visible.
  - **Outcome:** Export is auditable; dollar totals match what can be invoiced.
  - **Covered by:** R9, R10, AE4

---

## Requirements

**Billing period & filters**

- R1. M3 defines a billing period as an **explicit inclusive date range** (`from_date`, `to_date`). No named schedule types (monthly, bi-weekly, 1st/15th) ship in M3.
- R2. Export includes only entries whose **work date** falls within the period bounds.
- R3. Export supports **flexible scope filters** aligned with `ttd entries list`: optional client filter, optional project filter, or all entries in range when neither filter is set.

**Rounding configuration**

- R4. **Clients** may configure a **rounding increment** (duration in minutes). When unset, the client has **no rounding** (export uses exact stored billable hours per entry).
- R5. **Projects** may override the client rounding increment. When unset on the project, the client value applies.
- R6. At export time, each **billable entry** has its canonical billable hours rounded **up** to the effective increment for that entry's project (project override else client). **Stored entry hours are not modified** by export — rounding is export-time only.
- R7. Rounding direction in M3 is **round up** only; nearest/down and per-direction configuration are out of scope.

**Export row shape**

- R8. **Duration-mode entries** in the export period are **rolled up** into CSV rows keyed by **project + work_date + note text**. Multiple duration entries sharing the same project, work date, and note text produce **one row** with summed hours (after per-entry rounding in R6).
- R9. **Different note text** on the same project and work date always produces **separate rows**, including when one note is blank and another is not.
- R10. **Interval-mode entries** are exported as **one row per entry**, never rolled up with other entries, even on the same project-day. Rows include time-in and time-out when stored.
- R11. Every export row includes identifying context (**client**, **project**, **work date**) so filtered and unfiltered exports are self-contained.
- R12. The CSV ends with a **summary section** (same file) providing period subtotals by client and by project (billable hours; dollar subtotals for hourly projects only).

**Amounts & billing mode**

- R13. For **hourly** projects, export rows and summary totals include **billable hours** and **dollar amounts** computed from the **effective hourly rate** (project override else client default) applied to **rounded** entry hours (before duration rollup where applicable).
- R14. For **fixed-price** projects, export rows and summary totals include **billable hours only** — no rate × hours dollar columns (contract total remains available separately in the ledger, not duplicated as line-item billing in M3 CSV).
- R15. **Non-billable** entries are **included** in the CSV with a **billable flag** column. They contribute to hour columns where applicable but are **excluded from dollar amount columns and dollar summary totals**.

**Core services & CLI**

- R16. All export logic — period selection, rounding, rollup rules, rate resolution, row generation, summary totals, and CSV formatting — lives in **`ttd.core` only**.
- R17. CLI provides a thin **`ttd export`** (or equivalent) command: required period bounds, optional client/project filters, optional **output file path**; when path is omitted, CSV is written to **stdout**.
- R18. Service-layer and CLI tests cover export happy paths, rounding inheritance, duration rollup vs interval row shape, hourly vs fixed-price columns, and non-billable dollar exclusion.

---

## Acceptance Examples

- AE1. **Covers R1, R2, R3.** Given entries on 2026-05-01 and 2026-05-31 and an export for 2026-05-01 through 2026-05-31, when export runs, then only entries with work dates in May are included.
- AE2. **Covers R4, R6, R7.** Given a client with no rounding increment and a 2.37h duration entry, when exported, then the row shows 2.37h (not rounded).
- AE3. **Covers R5, R6, R7.** Given a client with 15-minute increment and a project with no override, and a 2.10h billable entry, when exported, then the entry contributes 2.25h (rounded up to next 15-minute increment) before any duration rollup.
- AE4. **Covers R9, R15.** Given two duration entries on the same project and work date with notes "API" and "" (blank), when exported, then two separate rows appear; if one entry is non-billable, then its row shows the billable flag false and dollar columns are zero or omitted for that row while hours still appear.
- AE5. **Covers R8, R10.** Given two duration entries on the same project, work date, and note "Standup", when exported, then one row shows the sum of rounded hours; given two interval entries the same project-day, when exported, then two rows appear each with time-in and time-out.
- AE6. **Covers R13, R14.** Given an hourly project at $150/h with 10h billable in the period and a fixed-price project with 5h billable in the same export, when summary totals are produced, then the hourly project summary includes dollars and the fixed-price summary includes hours only.
- AE7. **Covers R6, R12.** Given an entry edited after a prior export, when the ledger is queried, then stored billable hours reflect the edit; when export is re-run, then CSV reflects the new rounded export-time values without mutating stored hours from the prior export.

---

## Success Criteria

- After dogfooding M3, the developer can close a billing period **without spreadsheet summing** for the exported scope — CSV totals are trusted for invoicing.
- **Period close duration** (strategy metric) improves versus spreadsheet + manual assembly baseline for the same period.
- Planning (`ce-plan`) does not need to invent CSV row shape, rounding inheritance, rollup keys, or hourly vs fixed-price column rules.
- Export tests give confidence that duration rollup and interval row rules do not diverge silently before M4 trust features or M6 invoice formats.

---

## Scope Boundaries

- Named billing period schedules (calendar month presets, bi-weekly, 1st-and-15th) — follow-up after M3; M3 is custom date range only
- PDF/Markdown invoices and client-ready document layout — M6
- TUI and Litestar export routes — M5, M7
- Backup/restore, portable export formats, post-export edit audit — M4
- Rounding direction options other than round-up; minimum billable blocks per entry
- Multi-currency FX conversion between clients
- Timer-first capture, tags, cloud sync, team features
- Changing stored entry hours during export (export is read-only on ledger data)

---

## Key Decisions

- **Transformed export rows vs raw entry dump:** M3 produces invoice-oriented rows (duration rollup + interval detail), not a one-row-per-entry dump — replaces spreadsheet assembly, not just CSV serialization.
- **Rounding at export only:** Preserves exact ledger data for post-export corrections (strategy post-export correction rate); rounding config is durable on client/project for repeatability.
- **Client/project rounding inheritance:** Mirrors rate inheritance — familiar mental model, one place to set defaults per customer.
- **M3 period = date range only:** Defers schedule complexity while keeping flexibility via `--from` / `--to`; named schedules are a follow-up once export shape is proven.
- **Note text as rollup key:** Different notes always split rows — avoids losing audit trail when collapsing duration work on the same day.
- **Summary in same CSV:** Period subtotals ship with detail rows so one file is sufficient for invoicing review without a second export artifact.

---

## Dependencies / Assumptions

- M1 ledger models and services (clients, projects, entries, effective rate, billable flag, billing modes) are shipped and stable.
- M2 CLI capture and `entries list` filtering patterns exist and inform export filter UX.
- New client/project fields for rounding increment are acceptable in M3 (schema via existing `auto_migrate` policy until Alembic cutover).
- CSV column names and ordering are defined during planning; requirements fix behavior, not spreadsheet layout branding.
- Currency on dollar columns follows effective rate currency for hourly projects (no FX).

---

## Outstanding Questions

### Deferred to Planning

- [Affects R12][Technical] Exact CSV column set, column order, and summary section format (footer rows vs second logical block).
- [Affects R8][Technical] Whether blank-note duration entries with identical project-day merge with each other when note is empty on all (confirmed: same empty note merges; different blank vs text splits per AE4).
- [Affects R4][Technical] Representation of "no rounding" on client/project (null increment vs explicit zero — must not collide with a valid 0-minute increment if ever allowed).
- [Affects R17][Technical] Final CLI command name and flag names (`export` vs `close`, path of default data-dir exports if any).
