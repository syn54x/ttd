# Time expressions

The natural-language grammar used by `ttd log`, the `--at` flag on
`ttd start`/`ttd stop`, `ttd entry edit --time`, and the TUI quick log. An
expression combines an optional **date part** and a **time body**, in any
order: `yesterday 9am to noon`, `2h30m last friday`.

## Where expressions are used

| Place | Accepts |
| --- | --- |
| `ttd log "…"`, `entry edit --time`, TUI quick log | intervals and durations |
| `ttd start --at`, `ttd stop --at` | a single point in time |

## Dates

If you give no date, the entry lands on **today**.

| Form | Examples | Meaning |
| --- | --- | --- |
| keyword | `today`, `yesterday` | the obvious |
| weekday | `monday`, `wed`, `thurs` | the most recent occurrence (today counts) |
| `last` weekday | `last monday` | the occurrence before that |
| ISO date | `2026-06-03` | exact date |
| slash date | `6/3`, `6/3/26`, `6/3/2026` | month/day; 2-digit years are 2000+ |
| part of day | `morning`, `this afternoon`, `evening`, `night` | today, and biases am/pm for the times |
| `on` + any of the above | `on 2026-06-01` | reads naturally in sentences |

Future dates are rejected — ttd logs what happened, not what's planned.

## Times

| Form | Examples | Notes |
| --- | --- | --- |
| hour | `9`, `17` | `0` and `13`–`23` are unambiguous 24-hour |
| hour:minute | `9:30`, `17:45` | |
| with meridiem | `9am`, `5 pm`, `9:30p.m.` | |
| leading zero | `08:30` | always exact 24-hour, no am/pm inference |
| words | `noon`, `midnight` | |

A bare `9` could be 09:00 or 21:00. ttd resolves ambiguity with the
**workday window** (`parsing.workday_start`–`parsing.workday_end`, default
7–19): the reading that keeps the interval inside the window wins. When no
single reading does — `6 to 8` fits both ways — the expression is rejected
and the candidate readings are shown; add am/pm. For `--at` points, the
candidate closest to *now* wins.

## Durations

| Form | Examples |
| --- | --- |
| hours / minutes | `2h`, `30m`, `2h30m`, `2h 30m` |
| words | `2 hours`, `30 minutes`, `2 hours 30 minutes` |
| decimals | `1.5h` |

A single entry can't exceed **14 hours**.

## Expression forms

| Form | Example | Result |
| --- | --- | --- |
| time to time | `9am to noon`, `9-11:30`, `from 9 to 11` | interval (start, end) |
| time for duration | `1pm for 3 hours`, `at 9 for 2h` | interval |
| duration | `2h30m` | duration only, no clock times |
| duration at time | `3h at 9am` | interval anchored at the time |
| point time (`--at` only) | `--at 8:30`, `--at "yesterday 5pm"` | a single moment |

## Limits and errors

- **Cross-midnight intervals aren't supported** — an entry belongs to one
  day. (`10pm to midnight` works; `10pm to 2am` doesn't — log two entries.)
- **Ambiguous times are rejected** with the readings ttd considered.
- **Overlaps** with an existing entry on the same project and day are
  rejected unless you pass `--force` ([details](../guides/tracking-time.md#validation-overlaps-ambiguity-limits)).

## Cookbook

All verified against the parser (assume "now" is Thursday 2026-06-11, 3pm):

| You type | You get |
| --- | --- |
| `today 9am to noon` | Jun 11, 09:00–12:00 (3h) |
| `9-11:30` | Jun 11, 09:00–11:30 (2h30m) |
| `9 to 5` | Jun 11, 09:00–17:00 (8h) |
| `yesterday 2h30m` | Jun 10, 2h30m, no clock times |
| `monday 1pm for 3 hours` | Mon Jun 8, 13:00–16:00 |
| `last friday 10am to 1pm` | Fri Jun 5, 10:00–13:00 |
| `2026-06-03 9-11:30` | Jun 3, 09:00–11:30 |
| `6/3 2h` | Jun 3, 2h |
| `on 2026-06-01 8h` | Jun 1, 8h |
| `this morning 3h` | Jun 11, 3h |
| `3h at 9am` | Jun 11, 09:00–12:00 |
| `from 9 to 11` | Jun 11, 09:00–11:00 |
| `10pm to midnight` | Jun 11, 22:00–24:00 |
| `1.5h` | Jun 11, 1h30m |
| `2 hours 30 minutes` | Jun 11, 2h30m |
| `08:30 to 10:00` | Jun 11, 08:30–10:00 (exact 24h) |
