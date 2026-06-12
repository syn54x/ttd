# Import & export

Your ledger is yours: round-trip it through CSV, JSON, XLSX, or Apple
Numbers — for spreadsheets, archives, or migrating from another tracker.

## Exporting your ledger

```console
$ ttd export ledger.csv          # format inferred from the extension
$ ttd export ledger.json
$ ttd export ledger.xlsx
$ ttd export ledger.numbers
$ ttd export backup -f json      # or say it explicitly
```

All formats write the same [canonical columns](../reference/interchange-format.md).
The JSON export adds a `_metadata` block (export time, settings summary).

### Filtering exports

```console
$ ttd export acme-may.csv --client acme-corp --from 2026-05-01 --to 2026-05-31
$ ttd export unbilled.csv --uninvoiced     # only work not yet on an invoice
$ ttd export billed.csv --invoiced
$ ttd export api.csv -p api-rewrite
```

## Importing entries

```console
$ ttd import ledger.csv
```

Rows missing a client or project can be defaulted (`--client`, `-p`), and
unknown clients/projects can be created on the fly:

```console
$ ttd import old-tracker.csv --client acme-corp --create-missing
```

Without `--create-missing`, rows referencing unknown clients/projects are
reported as errors instead of silently invented.

### Preview with --dry-run

```console
$ ttd import ledger.csv --dry-run
```

Shows exactly what would be created, updated, or skipped — and why — without
touching the database.

### Conflicts and idempotence

Each incoming row is matched against existing entries by **uid** first
(ttd's own exports carry one), then by **content** (same client, project,
date, times, duration, note). What happens on a match is yours to choose:

```console
$ ttd import ledger.csv --on-conflict skip        # default: leave existing alone
$ ttd import ledger.csv --on-conflict update      # overwrite with the file's version
$ ttd import ledger.csv --on-conflict duplicate   # keep both
```

Re-importing your own export with `skip` is a no-op — imports are safe to
repeat. **Invoiced entries are never modified or re-linked** by an import,
whatever the conflict mode.

## Migrating from another tracker

1. Export from the old tool as CSV.
2. Rename its columns to the [canonical set](../reference/interchange-format.md) —
   only `client`, `project`, `date`, and a duration (`seconds` or `hours`)
   are required.
3. Preview: `ttd import old.csv --create-missing --dry-run`
4. Import: `ttd import old.csv --create-missing`

## The interchange format

`uid · client · project · date · start · end · hours · seconds · note · tags
· billable · invoice_number` — types, semantics, and per-format details in
the [interchange format reference](../reference/interchange-format.md).
