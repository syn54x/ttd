---
title: Roadmap
last_updated: 2026-05-25
---

# Roadmap

This document sequences **when** TTD ships capability. [STRATEGY.md](https://github.com/syn54x/ttd/blob/main/STRATEGY.md) defines **why** and **what tracks** matter; individual features get requirements in `brainstorms/` and implementation plans in `plans/` (repo root — excluded from the docs site build) before code lands.

**Product goal:** Replace the spreadsheet + manual invoice assembly loop for a solo developer billing hourly. **M1–M4** deliver the CLI ledger and CSV period close; **M5–M7** add TUI, client-ready invoice formats, and API; **M8** is the first public release. Success is measured by the metrics in `STRATEGY.md`.

---

## Status overview

| Milestone | Theme | Status |
|-----------|-------|--------|
| M0 | Foundation | **Done** |
| M1 | Billing ledger (core) | **Done** |
| M2 | Terminal capture (CLI) | **Done** |
| M3 | Export & period close (CSV) | Next |
| M4 | Data trust & hardening | Planned |
| M5 | TUI | Planned |
| M6 | PDF / Markdown invoices | Planned |
| M7 | API | Planned |
| M8 | Public release | Planned |

```mermaid
flowchart LR
    M0[M0 Foundation] --> M1[M1 Ledger]
    M1 --> M2[M2 CLI]
    M2 --> M3[M3 CSV export]
    M3 --> M4[M4 Trust]
    M4 --> M5[M5 TUI]
    M5 --> M6[M6 Invoices]
    M6 --> M7[M7 API]
    M7 --> M8[M8 Release]
```

M3 is next — export and period close build on the M1 ledger and M2 CLI dogfooding. **M5–M7** are thin surfaces and export formats over the same core — no duplicate domain logic.

---

## M0 — Foundation

**Track:** Enabler for all tracks

**Outcome:** Contributors can clone, run checks, and release without re-deciding stack choices.

**Delivered:**

- uv / Python 3.14 project with `ttd.core`, `ttd.cli`, `ttd.api`, `ttd.tui`
- Async core + ferro-orm SQLite connect stub
- Prek hooks, CI, manual release workflow (commitizen → PyPI → GitHub Pages)
- Design standards (`docs/design/general.md`, `AGENTS.md`)

**Plan:** `plans/2026-05-24-001-feat-foundational-techstack-plan.md`

---

## M1 — Billing ledger (core)

**Track:** Billing ledger

**Outcome:** Client → project → entry model exists in SQLite with inheritable/overridable rates. Core services own all domain rules; product surface commands not required yet.

**Ship when:**

- ferro-orm models and Alembic revision workflow are defined (`docs/design/data-layer.md` documents conventions)
- CRUD services for clients, projects, and time entries
- Entry modes: **duration** and **interval** stored with equal standing (no conversion required before billing)
- Rate inheritance: client default, project override
- Service-layer tests; first Hypothesis tests for duration/interval invariants

**Not in M1:** CLI/TUI/API product commands, export/rounding

**Pre-work:** Requirements brainstorm → implementation plan (same pattern as M0)

**Suggested plan units:**

1. Schema & migrations policy (Alembic vs dev `auto_migrate`)
2. Models: `Client`, `Project`, `TimeEntry`, rate fields
3. Services: create/list/update with validation
4. Tests: happy paths, rate override, entry mode validation

---

## M2 — Terminal capture (CLI)

**Track:** Terminal-first capture

**Outcome:** Run the real billing workflow from the terminal — add clients/projects, log retroactive work, list and correct entries — without a spreadsheet.

**Ship when:**

- `ttd client` — add, list (edit/delete as needed for corrections)
- `ttd project` — add, list, scoped to client
- `ttd log` — retroactive entry by duration **or** time-in/out
- `ttd entries` — list (filter by period/project), edit
- CLI stays thin: parse → `await` core → format
- Dogfooding: at least one real client/project logged locally

**Design constraint:** Optimize for **median time to log a retroactive entry**. Timer-first UX remains deferred (see After M8).

**Depends on:** M1

---

## M3 — Export & period close (CSV)

**Track:** Export & billing rules

**Outcome:** A billing period closes to CSV totals you trust enough to invoice from — no second assembly step for tabular export.

**Ship when:**

- Billing period definition (calendar month to start; extensibility deferred unless requirements demand it)
- Global rounding rule applied at export time
- Period totals by client and project
- CSV export suitable for invoicing (shape defined in requirements)
- Duration and interval entries bill the same way

**Not in M3:** PDF/Markdown invoices (M6), TUI/API product routes (M5–M7)

**Depends on:** M1; validated through M2 dogfooding

---

## M4 — Data trust & hardening

**Track:** Data trust & portability

**Outcome:** The ledger is safe to stake client invoices on; quality gates match billing sensitivity.

**Ship when:**

- Documented backup/restore of the SQLite database
- Plain-file or portable export path (requirements define format)
- Edit visibility for post-export corrections (supports post-export correction rate metric)
- pytest coverage `fail_under` enabled for billing-critical modules
- Hypothesis property tests for rounding and hour calculations

**Depends on:** M1–M3 (trust features wrap real ledger + export behavior)

---

## M5 — TUI

**Track:** Terminal-first capture (visual surface)

**Outcome:** Core ledger workflows are usable from Textual without opening a second tool for day-to-day review and capture.

**Ship when:**

- Textual app replaces placeholder with real screens (not a parallel product)
- Parity with primary CLI flows: clients, projects, log entry, list/edit entries, view period summary
- `ttd.tui` stays thin: widgets → `await` core → render
- Async core calls from Textual lifecycle hooks (no domain logic in `ttd.tui`)

**Not in M5:** Timer-first UX, rich analytics dashboards

**Depends on:** M1–M4 (stable core + CSV export to display)

---

## M6 — PDF / Markdown invoices

**Track:** Export & billing rules

**Outcome:** Period close produces client-ready line-item invoices — not only CSV totals — so billing does not require manual document assembly.

**Ship when:**

- Invoice generation from the same period totals and entry rows as M3 (single source of truth)
- **Markdown** and **PDF** output formats (requirements define layout, line items, and branding hooks)
- Global rounding and rate rules from M3 apply identically
- Formatting and layout logic lives in `ttd.core` (export services); CLI/TUI/API only trigger export and deliver files

**Depends on:** M3 (export engine); M4 recommended for export trust

---

## M7 — API

**Track:** Enabler for integrations (thin surface over core)

**Outcome:** Programmatic access to the ledger and exports for scripts, editors, and future channels (e.g. Raycast, MCP) without duplicating domain rules.

**Ship when:**

- Litestar routes for core operations: clients, projects, entries, period export (CSV + invoice formats from M6)
- Shared DB lifespan via `ttd.core.db`; auth deferred unless requirements demand it for local-only v1
- OpenAPI-visible DTOs; persistence and billing rules remain in core only
- API tests prove adapter → core delegation (same pattern as CLI tests)

**Not in M7:** Public multi-tenant hosting, cloud sync

**Depends on:** M1–M6 (API exposes what core already does)

---

## M8 — Public release

**Outcome:** TTD is installable, documented, and shippable as a complete solo-dev billing product (CLI + TUI + API + CSV + invoices).

**Ship when:**

- First semver release to PyPI (`uv tool install ttd-ledger`; CLI command `ttd`)
- User-facing docs: CLI workflow, TUI overview, API usage, period close through CSV and invoice export
- GitHub branch protection + PyPI trusted publishing verified
- Maintainer runbook exercised once end-to-end

**Depends on:** M2–M7 (M1 is implicit); dogfood at least one full billing period through M6 before tagging

---

## After M8 (not scheduled)

Deferred past the first public release. Tracks exist; sequencing TBD after dogfooding:

| Track | Examples |
|-------|----------|
| Terminal-first capture | Live timers, Raycast, MCP as channels into the same ledger |
| Export & billing rules | Rich reports, custom invoice templates, multi-currency |
| Billing ledger | Tags, non-hourly rate types |
| Data trust | Cloud sync, encryption at rest, multi-machine workflows |
| Platform | Team features, payroll, full accounting / payments |

---

## How work flows through the roadmap

For each milestone (starting with **M1**):

1. **Brainstorm** — `brainstorms/YYYY-MM-DD-<topic>-requirements.md`
2. **Plan** — `plans/YYYY-MM-DD-<n>-feat-<topic>-plan.md`
3. **Implement** — core first, then the surface for that milestone (CLI M2, TUI M5, export formats M6, API M7)
4. **Compound** — capture pitfalls in `docs/solutions/` when something non-obvious is learned

---

## Operational checklist (ongoing)

Land before or with **M8**:

- [ ] GitHub branch protection (require CI on PRs)
- [x] PyPI package name confirmed (`ttd-ledger`; CLI `ttd`)
- [ ] PyPI project registered and trusted publisher configured (see README release runbook)
- [ ] `just release-smoke` passes on `main`
- [ ] First manual release workflow dry-run on `main`
