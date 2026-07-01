# Flexible Invoice Periods — Design

**Status:** Approved design, pre-implementation
**Date:** 2026-07-01
**Branch:** feat/billable-expenses (Part 2 depends on the expense draft-line code there)
**Scope:** Two related improvements to invoice periods — (1) richer period parsing, and (2) recording the invoice's *actual* period derived from the billed items rather than the requested window.

## Problem

1. **Period parsing is rigid.** `reporting/periods.py` `parse_period` accepts only `''`/`last month`/`this month`/`YYYY-MM`/`YYYY-MM-DD to YYYY-MM-DD`. Users want relative durations ("last two weeks") and natural month-name ranges ("june 16 to june 30").
2. **The recorded invoice period overstates coverage.** `persist_draft` stamps the invoice's `period_start`/`period_end` as the *requested window*. If June 1–15 was already invoiced and you invoice "this month" again, it correctly sweeps only the uninvoiced June 16–30 work but records the period as "June 1–30".

The existing `ttd log` natural-language parser is NOT reusable: it has no month-name support and requires a clock time (it's built for time-of-day intervals).

## Decisions (settled during brainstorming)

| Decision | Choice |
|---|---|
| New relative forms | `this week` / `last week` (calendar), plus rolling `last <N> days\|weeks\|months` ending **today**; `<N>` is a digit or a word (`one`…`twelve`). |
| Month-name forms | `june 16 to june 30`, abbreviations (`jun`), separators `to`/`-`/`–`/`..`; shorthands `june` (whole month) and `june 16 - 30` (second endpoint inherits the month). |
| Year inference | **Closest-year, never future.** |
| Cross-year ranges | Month wrap (`dec 28 to jan 3`) rolls the end into the following month/year. |
| Invoice period | **Derived from the billed line items** (min–max of dates), not the requested window. |
| Implementation home | All parsing stays in `reporting/periods.py` (no log-grammar reuse, no new NL-date dependency). |

## Part 1 — Period grammar (`reporting/periods.py`)

`parse_period(text, today)` gains two new families on top of the existing branches:

**Relative durations**
- `this week` / `last week` → calendar weeks (respect `display.week_start`, like `week_period`). `this week` = current calendar week; `last week` = previous full calendar week.
- Rolling `last <N> days|weeks|months` ending today:
  - days: `today − (N−1) … today` (N calendar days including today).
  - weeks: `today − (N*7 − 1) … today`.
  - months: `(today − N calendar months) … today`.
  - `<N>` accepts digits (`2`, `10`) or number words `one…twelve`.
  - Note: bare `last week` (calendar) and `last 1 week` (rolling 7 days) may differ by a day or two; Part 2 makes this invisible on the invoice.

**Month-name ranges**
- `<month> <day> <sep> <month> <day>` — full names + 3-letter abbreviations; `sep` ∈ {`to`, `-`, `–`, `..`}.
- Shorthands:
  - `<month>` alone → that whole month.
  - `<month> <day> <sep> <day>` → second endpoint inherits the first month.
- Both endpoints resolve under one inferred year unless a year is explicit (a year token, if present, is honored).

## Part 2 — Year inference (closest-year, never future)

When a month-name form omits the year, resolve it as follows:
- Build the range twice: once with **this year**, once with **last year**.
- Choose the candidate whose range is **temporally closest to today** — distance from `today` to the range interval, `0` if today falls inside it. Ties → **this year**.
- **Never infer a future (next) year** — only this year and last year are candidates.

Worked examples (all confirmed):
- Jan 1 2026, `dec 15 – 31` → **2025** (Dec 2025 ended ~1 day ago; Dec 2026 ~11 months away).
- June 30 2026, `june 16 – 30` → **2026** (today inside the range).
- June 18 2026, `june 1 – 15` → **2026** (ended 3 days ago vs a year ago).
- June 1 2026, `june 16 – 30` → **2026** (15 days out beats ~11 months).

**Cross-year ranges:** when the second month is earlier in the year than the first (`dec 28 to jan 3`), the end rolls into the following month/year: start Dec (inferred year Y), end Jan (Y+1). Apply the closest-year rule to the *start* month; the end takes the wrapped year.

## Part 3 — Derived invoice period (`services/invoicing.py`)

- `build_draft` continues to use the parsed `Period` **only as a sieve** to select uninvoiced items within `[period.start, period.end]`.
- The **empty-check** ("no uninvoiced entries or expenses for … in {window}") still uses the requested window's label.
- After building the time lines and expense lines, derive the invoice's actual period:
  - `dates = [line.work_date for time lines] + [eline.incurred_date for expense lines]`
  - `actual = range_period(min(dates), max(dates))`
  - Set `Draft.period = actual` so `persist_draft` records the tight span. (The window is no longer stored anywhere on the invoice.)
- `apply_refresh` re-derives the period from the remaining linked items (time + expenses) so the stored period stays accurate after line edits/removals; update `invoice.period_start`/`period_end` accordingly in the non-paid branch.
- Single-day results (start == end) are valid.

## Part 4 — Errors, help text, testing

- Update the `parse_period` error message to list the new forms.
- Update the CLI `invoice create` `--period` help and the TUI new-invoice period-field placeholder/label to advertise: `last two weeks`, `this week`, `june 16 to june 30`, alongside the existing examples.
- Tests:
  - `reporting/periods` (unit, table-driven): each relative form (`this week`, `last week`, `last two weeks`, `last 10 days`, `last 3 months`, digit + word counts); each month-name form (`june`, `june 16 to june 30`, `jun 16 - 30`, cross-year `dec 28 to jan 3`); the four closest-year examples; and error cases (unknown month, malformed).
  - `services/invoicing` (behavioral): sweeping a window where only part is uninvoiced records the *derived* period (e.g. only June 16–30 uninvoiced → invoice period June 16–30); an expenses-only invoice derives its period from `incurred_date`s; refresh re-derives after removing an item.
- Keep the coverage gate (`fail_under = 84`) green; `ty` + `ruff` clean.

## Out of scope / deferred

- `this quarter`/`last quarter`, `year to date`, `this year`/`last year` (expressible as explicit ranges; add later if wanted).
- Reusing/extending the `ttd log` grammar for month names (separate concern).
- Reports currently call `parse_period` too — they automatically inherit the new forms (no extra work), but no report-specific behavior changes are in scope.

## Related

- Builds on the billable-expenses feature (PR #14): Part 3 derives the period from both time and expense line dates, so it needs the expense draft-line code.
