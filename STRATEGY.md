---
name: TTD
last_updated: 2026-05-23
---

# TTD Strategy

## Target problem

Solo developers who bill clients by the hour often reconstruct work after the fact in a strict spreadsheet (time-in/time-out rows), then manually assemble client invoices from that data. Capture is retroactive and imprecise, spreadsheets enforce clock precision even when you only remember duration, and invoicing is a separate error-prone step—while the work itself happens outside whatever tool holds the ledger.

## Our approach

We win by being a billing-native time ledger in the terminal—not a live timer or a stricter spreadsheet. Capture matches how solo devs actually reconstruct work (duration or time-in/out, with equal standing), and client → project → rate structure is built into the data model so totals and exports come from one source of truth instead of a hand-maintained sheet and a separate invoice assembly step.

## Who it's for

**Primary:** Solo developer billing clients on hourly (time & materials) across multiple clients and projects, working primarily from the terminal — they're hiring TTD to maintain a trustworthy billable ledger from retroactive, imperfect memory and produce structured period totals for invoicing without a strict spreadsheet and manual invoice assembly.

## Key metrics

- **Billing-period ledger completion** — Each billing period, did I run the full cycle from TTD only (no parallel spreadsheet)? Measured: yes/no per period.
- **Median time to log a retroactive entry** — How fast is a typical CLI log (hours or interval)? Measured: timed samples; should stay low and not creep up as features accrue.
- **Workday coverage** — What fraction of workdays in the period have at least one entry? Measured: SQLite; regresses if I stop logging and reconstruct at period end.
- **Post-export correction rate** — What share of exported entries or hours get edited within 48h of export? Measured: SQLite; regresses if I don't trust CSV totals.
- **Period close duration** — Time from period end to CSV ready for invoicing. Measured: timed once per period; should beat spreadsheet + manual invoice baseline.

## Tracks

### Billing ledger

Build and maintain the client → project → entry model with inheritable/overridable rates and flexible entry modes (interval and duration, equal standing). Replaces spreadsheet maintenance as the structured source of truth.

_Why it serves the approach:_ The billing-native data model is what makes one source of truth possible.

### Terminal-first capture

Invest in CLI ergonomics so retroactive logging is the default happy path and fast enough to use during real work; optional live timers and later extensions (e.g. Raycast, MCP) are channels into the same ledger, not separate products.

_Why it serves the approach:_ Capture has to match how solo devs actually work, from the terminal, without timer-first friction.

### Export & billing rules

Turn ledger data into billable outputs: global rounding, period totals, CSV in v1; line-item PDF/Markdown invoices and richer reports as the product matures—so billing doesn't require a second manual assembly pass.

_Why it serves the approach:_ Exports are the payoff; the ledger only wins if billing doesn't need a separate step.

### Data trust & portability

Local-first SQLite with clear backup and optional plain-file export, plus integrity around edits and exports, so solo developers can stake client invoices on the data.

_Why it serves the approach:_ Retroactive capture only works if the ledger is trustworthy enough to bill from.

## Not working on

- Team features, payroll, and utilization tracking
- Timer-first UX and productivity analytics as the product center
- Invoices, TUI, and agent/Raycast integrations in v1
- Cloud accounts and sync as a launch requirement
- Interval-only or "convert before bill" rules for duration entries
- Full accounting / payments scope

## Marketing

**One-liner:** TTD is a terminal-native billable ledger for solo developers who invoice by the hour.

**Tagline:** Bill from the terminal.

**Key message:**
- Not a stopwatch — a ledger you trust at billing time.
- Log how you remember work: hours or time-in/out, same weight.
- Client → project → rate built in; export replaces spreadsheet + manual assembly.
