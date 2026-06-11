# ttd

Terminal-first time tracking, reporting, and invoicing for solo developers.

Track time where you already live — the terminal. Log work in natural language,
run timers, roll everything up into reports, and send client-ready PDF invoices,
all without leaving your shell.

```
$ ttd log "today 8am to 5pm" -p api-rewrite --note "auth endpoints"
✓ Logged 9:00 on Tue Jun 9 (8:00am–5:00pm)

$ ttd invoice create --client acme-corp --month 2026-06 --pdf
✓ Created invoice 2026-001
✓ Wrote ~/Documents/invoices/2026-001-acme-corp.pdf
```

## Install

```sh
uv tool install ttd-ledger     # or: pipx install ttd-ledger
ttd --install-completion       # shell completion
```

## The three ways in

1. **CLI** — every feature is a command. Scriptable, pipeable.
2. **`-i` forms** — add `-i` to any mutating command for an interactive form;
   any flags you already passed pre-fill it.
3. **TUI** — run bare `ttd` for the full-screen app: live timer, activity
   heatmap, day-by-day timesheet with as-you-type time parsing, reports, and
   invoice management. Keys: `1–5` screens, `s` start/stop, `l` quick-log.

Try it with demo data: `ttd db seed-demo && ttd` (add `--reset` to wipe and reseed)

## Logging time

Natural language, retrospective or live:

```sh
ttd log "today 8am to 5pm"            # interval
ttd log "yesterday 9-11:30"           # am/pm inferred from your workday window
ttd log "monday 1pm for 3 hours"      # most recent monday
ttd log "2h this morning"             # duration-only entry
ttd log "6/3 10am-1pm"                # explicit date

ttd start api-rewrite                 # live timer
ttd stop --at 5pm
ttd status
```

Multiple entries per project per day are normal; reports and invoices roll
them up into hours per day. Ambiguous times ("6 to 8") are rejected with the
candidate readings instead of silently guessing.

## Clients, projects, rates

```sh
ttd client add "Acme Corp" --rate 150 --email billing@acme.test
ttd project add "API Rewrite" --client acme-corp        # inherits $150/h
ttd project add "Mobile App" --client acme-corp --rate 175
```

Rates resolve project → client → `[business].default_hourly_rate`.

## Reports

```sh
ttd report day                  # today, entry by entry
ttd report week --by project    # sparklines + billable value
ttd report month 2026-05 --client acme-corp
ttd report range --from 2026-01-01 --to 2026-03-31 --by client
```

## Invoicing

```sh
ttd invoice create --client acme-corp --month 2026-05 --pdf --md
ttd invoice list
ttd invoice mark 2026-001 sent     # then: paid, or void
```

Billable, uninvoiced entries roll up to one line per project per day, rounded
per your `[billing]` policy. Invoiced entries lock; voiding an invoice releases
them (numbers are never reused).

## Export / import

CSV, JSON, XLSX, and Apple Numbers — both directions:

```sh
ttd export hours.xlsx                  # format inferred from extension
ttd export backup.json                 # JSON carries client/project metadata
ttd import hours.csv --dry-run         # preview: new/update/skip/errors
ttd import hours.csv --on-conflict update --create-missing
```

Imports match by entry id, then by content; invoiced entries are never touched.

## Configuration

Layered TOML, nearest-wins (like ruff): CLI flags → `TTD_*` env →
`.ttd.toml` (walks up from cwd) → `~/.config/ttd/config.toml` → defaults.

```toml
# ~/.config/ttd/config.toml
[user]
name = "Taylor"
email = "taylor@example.com"

[business]
currency = "USD"
default_hourly_rate = 150

[billing]
rounding = "nearest"      # nearest | up | none
increment_minutes = 15    # applied per project-day

[invoice]
number_format = "{year}-{seq:03d}"
payment_terms_days = 30
output_dir = "~/Documents/invoices"

[parsing]
workday_start = 7         # am/pm inference window
workday_end = 19
```

Pin a repo to a project so bare `ttd start` / `ttd log "2h"` just work:

```sh
cd ~/code/acme-api
ttd config set defaults.client acme-corp --local
ttd config set defaults.project api-rewrite --local
```

`ttd config list --origin` shows where every value came from.

## Development

```sh
uv sync
just test     # pytest
just lint     # ruff + ty
just tui      # textual dev mode
```

Stack: Python 3.13, [Ferro-ORM](https://github.com/syn54x/ferro-orm) over
SQLite, Cyclopts, Rich, Textual, questionary, fpdf2, openpyxl, numbers-parser.
