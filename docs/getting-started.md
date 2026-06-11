# Getting started

See the [repository README](https://github.com/syn54x/ttd/blob/main/README.md) for clone, install, and check commands.

## Setup

```bash
just setup
```

Runs `uv sync` and `uv run prek install` (same as the README quick start).

## Checks

```bash
just check
just test
prek run --all-files
```

`just check` runs ruff and ty (fast local gate), `just test` runs pytest with coverage. `prek run --all-files` runs lint, format, type, and docs-build hooks — the same lint job CI executes on every pull request and push to `main`; tests run in a separate CI matrix (Ubuntu/macOS × Python 3.13/3.14).

## Demo data

```bash
just db-seed
```

Runs `ttd db seed-demo`, loading demo clients, projects, and time entries into the local SQLite database (`ttd db path` shows where). Use `just db-seed --reset` to wipe and reseed.

## Backup

Before risky edits or migrations, snapshot the ledger:

```bash
ttd db backup
```

Copies the database to a timestamped backup file. `ttd db doctor` checks database health, and `ttd db migrate` applies pending schema migrations.

## Export / import

Export entries (with client/project metadata in JSON) for inspection or transfer; CSV, JSON, XLSX, and Apple Numbers are supported in both directions:

```bash
ttd export ledger.json
ttd import ledger.json --dry-run
ttd import ledger.json --on-conflict update --create-missing
```

Imports match by entry id, then by content; invoiced entries are never touched.
