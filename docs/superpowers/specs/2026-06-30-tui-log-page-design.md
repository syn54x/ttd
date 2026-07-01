# TUI Log Page (re-scope timesheet) — Design

**Status:** Approved design, pre-implementation
**Date:** 2026-06-30
**Branch:** feat/billable-expenses (TUI side of the billable-expenses feature)
**Scope:** Re-scope the TUI `timesheet` screen into a unified `log` page that views, adds, edits, and deletes BOTH time entries and expenses.

## Problem

Expenses can be created in the TUI (via the `l` chooser) and seen on invoices, but there is
no TUI surface to **browse/manage expenses** as a list. Meanwhile the `timesheet` screen — the
only TUI place to view a span of time entries and edit/delete them — is underused (the user
goes straight to reports). Rather than add a 7th nav item, re-scope `timesheet` into a `log`
page that manages both record types, mirroring the `l` chooser (log time / log expense).

## Decisions (settled during brainstorming)

| Decision | Choice |
|---|---|
| Replace vs add | Re-scope `timesheet` → `log` (nav slot 2). No 7th nav item. Time-entry edit/delete is preserved (the concern that drove this). |
| Layout | **Two stacked sections** — a time table, then an expenses table — each with its own columns (different record shapes; matches the invoice detail/preview layout). |
| Add/edit/delete | **Focus-based.** `e` edits / `x` deletes the highlighted row in the *focused* section. Adding reuses the global `l` chooser (time/expense) — no separate add key. |
| Period window | **Month only**, cycled with `[` / `]`. Drop the day/week/month (`d`/`w`/`m`) toggle. |
| Empty expenses | Show the section header + a muted "no expenses this month" line (page shape stays stable). |

## Page identity & nav

- `NAV` entry `("timesheet", "2 timesheet")` → `("log", "2 log")` in `src/ttd/tui/screens/_base.py`.
- Rework `TimesheetScreen` into `LogScreen`: rename the class, rename `screens/timesheet.py` →
  `screens/log.py`, set `nav_id = "log"`, and update the `SCREENS` registry in `src/ttd/tui/app.py`
  (the screen is keyed by `nav_id`, so the `goto('timesheet')` binding/registry key becomes
  `'log'`). Update any imports/references.
- Keep it one screen with two sections.

## Layout & data

Under a shared month header (e.g. "June 2026"), two `DataTable`s:

- **Time** — columns: `date · project · hours · note`. This is the current timesheet day table,
  unchanged in content; rows are entries in the active month by `work_date`.
- **Expenses** — columns: `date · project · description · amount`. Rows are expenses in the
  active month by `incurred_date`. Empty → header + muted "no expenses this month".

A footer shows the month's billable time total and the month's expense total.

Both sections are scoped to the same active month; `[` / `]` shift the month and refresh both.

## Interaction

- `[` / `]` cycle months; `d`/`w`/`m` span bindings are removed.
- Focus moves between the two sections (Tab; and up/down rolls past a table edge into the other).
  The focused section's header is visually highlighted.
- **`e`** edits the highlighted row in the focused section:
  - time → existing entry edit flow.
  - expense → a `FormModal` (project/description/amount/date) prefilled with the row's values,
    submitting through `expense_svc.edit_expense`.
- **`x`** deletes the highlighted row in the focused section (entry → `entry_svc.delete_entry`,
  expense → `expense_svc.delete_expense`). Both services already refuse invoiced rows; surface
  that error via `notify`.
- **`l`** (global chooser) adds time or expense; on return the page refreshes.

## Implementation & testing

- **Services/data:** reuse `entry_svc` (list/edit/delete) and `expense_svc.list_expenses`/
  `edit_expense`/`delete_expense`. Add a `_data` helper for "expenses in a month window"
  mirroring the entries-by-window helper, returning the rows the expenses table renders.
- **Edit modal:** reuse the generic `FormModal` with the same fields as the `l` expense form;
  prefill from the selected expense; validate amount/date with the existing `_validate_amount`/
  `_validate_date` helpers.
- **Focus model:** track the active section; route `e`/`x` by it; highlight the active header.
- **Tests (pilot + data):**
  - `_data` month-window expense helper returns the right rows (unit).
  - Pilot: log screen renders both sections for a month containing an entry + an expense;
    `[`/`]` changes the month and re-renders; `x` on a focused expense row deletes it;
    deleting/editing an invoiced expense surfaces an error.
  - Keep the coverage gate (`fail_under = 84`) green.

## Out of scope / deferred

- Receipt attachment from the TUI (still CLI-only — separate follow-up).
- Any change to dashboard/reports.
- Recurring expenses, markup (already out of scope for the feature).

## Related

- Builds on the billable-expenses feature (PR #14): the `l` time/expense chooser, the
  `FormModal` expense form, and `expense_svc` CRUD all already exist.
