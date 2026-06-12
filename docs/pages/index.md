# TTD

Terminal-first time tracking, reporting, and invoicing for solo developers.

![The ttd dashboard](assets/screenshots/dashboard.svg)

## What is ttd

ttd turns logged hours into client-ready invoices without leaving your
terminal. Track time with a live timer or plain English ("today 9am to
noon"), see where the week went, invoice a client's unbilled work in one
command, and set a slice of every paid invoice aside for estimated taxes.

Everything lives in a single local SQLite file — no accounts, no sync, no
browser.

## The three ways in

Everything works three ways; pick per task:

1. **Direct commands** — `ttd log "yesterday 2h" -p api-rewrite`. Fast, scriptable.
2. **Interactive forms** — add `-i` to any creating command (`ttd client add -i`)
   and a form asks for whatever you didn't pass as flags.
3. **The TUI** — bare `ttd` opens a full-screen dashboard with a timer,
   timesheet, reports, invoices, and tax tracking. See [The TUI](guides/the-tui.md).

![Quickstart walkthrough](assets/gifs/quickstart.gif)

## Install in one line

```bash
uv tool install ttd-ledger
```

More options (pipx, pip, shell completion) in [Installation](getting-started/installation.md).

## Try it with demo data

```bash
ttd db seed-demo
ttd
```

Seeds demo clients, projects, and ~3 months of entries so every screen has
something to show. Point `TTD_DB_PATH` at a throwaway file to keep it out of
your real ledger.

## Where to go next

- [Quickstart](getting-started/quickstart.md) — zero to your first invoice in ten minutes
- [Tracking time](guides/tracking-time.md) — timers, natural-language logging, editing
- [Invoicing](guides/invoicing.md) — from unbilled hours to a rendered PDF
- [The TUI](guides/the-tui.md) — the full-screen interface
- [CLI reference](reference/cli/index.md) — every command and flag
