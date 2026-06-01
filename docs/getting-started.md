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
prek run --all-files
```

`just check` runs ruff and ty only (fast local gate). `prek run --all-files` also runs pytest (with coverage), Zensical docs build, and other hooks — the same full suite CI executes on every pull request and push to `main`.

## Demo data

```bash
just db-seed
```

Loads demo clients, projects, and time entries into the local SQLite database (`~/.local/share/ttd/ttd.db` by default). Safe to re-run: it skips if demo data is already present. Use `just db-seed -- --force` to replace demo rows only.

## Backup and restore

Before risky edits or migrations, snapshot the ledger:

```bash
ttd db backup ~/Backups/ttd-$(date +%F).db
```

Restore replaces the **entire** active database at the path from `ttd db where`:

```bash
ttd db restore ~/Backups/ttd-2026-05-31.db --yes
```

Backup uses SQLite’s online backup API after closing the local connection. Restore is destructive — confirm with `--yes`.

## Portable JSON export

Export the full ledger (clients, projects, entries) for inspection or merge into another machine:

```bash
ttd export json --output ledger.json
ttd import json ledger.json --yes
```

Import **merges by ID**: existing records are skipped, not updated. For a full replace, use `ttd db restore` instead.
