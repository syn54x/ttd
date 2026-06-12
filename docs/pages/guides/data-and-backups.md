# Data & backups

Everything ttd knows lives in one local SQLite file. No cloud, no accounts —
and backing up means copying one file.

## Where your data lives

```console
$ ttd db path
```

By default that's the platform user-data directory (`~/Library/Application
Support/ttd/ttd.db` on macOS, `~/.local/share/ttd/ttd.db` on Linux). Move it
by setting `storage.db_path` in [config](configuration.md), or per-process
with `TTD_DB_PATH=/somewhere/ttd.db`.

## Backups

```console
$ ttd db backup                  # timestamped copy next to the database
$ ttd db backup ~/Backups/       # or wherever you say
```

Creates `ttd-YYYYMMDD-HHMMSS.db`. Restoring is copying the file back. Take
one before bulk imports or anything you're unsure about.

## Health checks and migrations

```console
$ ttd db doctor     # sanity-check + row counts (clients, projects, entries, invoices)
$ ttd db migrate    # create/upgrade the schema
```

Migrations also run automatically on first use, so `migrate` is rarely
needed by hand.

## Demo data and sandboxes

```console
$ TTD_DB_PATH=/tmp/demo.db ttd db seed-demo --yes
$ TTD_DB_PATH=/tmp/demo.db ttd
```

`seed-demo` loads demo clients, projects, and ~3 months of entries —
pointing `TTD_DB_PATH` at a throwaway file keeps experiments out of your
ledger. `--reset` wipes before seeding (it asks unless you pass `--yes`).

## Exports as archives

A periodic `ttd export ledger.json` gives you a portable, human-readable
snapshot alongside binary backups — see [Import & export](import-export.md).
