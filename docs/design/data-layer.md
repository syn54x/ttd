# Data layer

**Date:** 2026-05-25
**Status:** Superseded — predates the rewrite; models now live in `src/ttd/storage/models/`, DB lifecycle in `src/ttd/storage/db.py`. Kept for the conventions; module paths are stale.
**Applies to:** `src/ttd/core/models/`, `src/ttd/core/db.py` (old layout)

Extends [general.md](general.md). Defines persistence conventions for the billing ledger.

---

## Stack

- **SQLite** via ferro-orm (`connect(dsn, auto_migrate=True)`)
- **Models** in `src/ttd/core/models/` — one module per entity
- **Money and hours** as `Decimal` (never `float` on persisted billing fields)
- **Primary keys** — `UUID`, assigned in services on create (`uuid4()`)

---

## Schema evolution (M1)

### Active development: `auto_migrate`

- `init_db()` imports `ttd.storage.models` before `connect` so all `Model` subclasses register metadata.
- `auto_migrate=True` creates missing **tables only** — it does **not** add columns
  to existing tables when a model gains fields between releases.
- **Column adds:** `_COLUMN_ADDS` in `src/ttd/storage/db.py` is an idempotent
  shim that `ALTER TABLE ADD COLUMN`s nullable fields at startup (first used for
  the invoice tax set-aside columns). After any DDL it must `reset_engine()` and
  reconnect: querying through the live pool after an ALTER panics the sqlx
  worker and **silently returns zero rows** on ferro-orm 0.10.5 — see
  [ferro-orm#67](https://github.com/syn54x/ferro-orm/issues/67) and the repro in
  `docs/upstream/ferro-alter-table-stale-pool-repro-standalone.py`. The shim can
  be retired if [ferro-orm#68](https://github.com/syn54x/ferro-orm/issues/68)
  (auto_migrate column adds) ships.
- **Tests:** each test uses an isolated `Settings(data_dir=tmp_path)` database; `reset_db_state` closes the engine between tests.
- **Local dev:** if the on-disk `ttd.db` drifts after model changes, delete `~/.local/share/ttd/ttd.db` (or your configured `data_dir`) and reconnect.

### Pre–user-testing: Alembic cutover (deferred)

When the schema stabilizes (e.g. before M2 dogfooding / external testers):

1. Freeze model definitions; avoid drive-by column renames.
2. Generate `alembic/` and the initial revision from ferro models (`ferro-orm[alembic]`).
3. Check in revision files; document `alembic upgrade head` for long-lived databases.
4. Decide whether tests keep `auto_migrate` on tmp DBs or run `upgrade head` — either is fine if CI is consistent.

Until then, **do not** add `alembic/` to the repo for routine M1 work.

---

## Configuration (M4)

Layered TOML + env vars feed a single `Settings` object via `get_settings()`. All DB paths and future display prefs use this path.

### Files and discovery

| Layer | Path | Notes |
|-------|------|--------|
| **Global** | `{XDG_CONFIG_HOME}/ttd/ttd.toml` (default `~/.config/ttd/ttd.toml`) | Created on first `ttd config set --global …` |
| **Local** | Nearest `ttd.toml` walking up from cwd to filesystem root | First match wins; no merge of ancestor files |
| **Env** | `TTD_*` variables (and optional cwd `.env`) | Highest precedence |

### Precedence (highest first)

1. `TTD_*` environment variables (including values loaded from `.env`)
2. Local `ttd.toml`
3. Global `ttd.toml`
4. Built-in defaults

### v1 keys

| Key | Default | Purpose |
|-----|---------|---------|
| `data_dir` | `~/.local/share/ttd` | SQLite directory (created on first use when default) |
| `db_filename` | `ttd.db` | Database file name within `data_dir` |
| `clock_format` | `24h` | `12h` or `24h`; stored only in M4 |

Paths in TOML are expanded and resolved on read. Unknown keys in existing files (e.g. legacy `timezone`) are ignored.

### CLI

```bash
ttd config show              # key, effective value, source layer + file paths
ttd config init              # interactive first-run setup (writes global file)
ttd config init --local      # write ./ttd.toml instead
ttd config get data_dir      # scriptable single-line output
ttd config set data_dir /path/to/data
ttd config set --global clock_format 24h
```

`config set` writes the **local** file in cwd when no ancestor `ttd.toml` exists; use `--global` for the XDG config file. After changing `data_dir`, run `ttd db where` (and `ttd db migrate` if needed) in a fresh invocation.

### Tests

Config tests monkeypatch `XDG_CONFIG_HOME` and cwd; service tests continue to inject `Settings(data_dir=tmp_path)` directly — unchanged.

---

## Entity model

| Entity | Table | Notes |
|--------|-------|--------|
| `Client` | `client` | Default hourly rate + ISO 4217 currency; optional `rounding_increment_minutes` |
| `Project` | `project` | `billing_mode`: hourly or fixed_price; unique `(client_id, name)`; optional rounding override |
| `TimeEntry` | `time_entry` | Hours-canonical; duration vs interval modes |

M1 uses scalar UUID FK columns (`client_id`, `project_id`) rather than ferro
`ForeignKey` relation fields so `.where(Model.fk == uuid)` filters work reliably.

### Billing modes

- **Hourly:** optional `hourly_rate` + `currency` override; else inherit client.
- **Fixed-price:** required `contract_total` + `currency`; no hourly rate columns used.

### Entry modes

- **Duration:** `billable_hours` + `work_date` only; `started_at` / `ended_at` must be null.
- **Interval:** timezone-aware UTC `started_at` / `ended_at`; `billable_hours` snapshotted at write and recomputed when bounds change. Overnight spans allowed (end may be after `work_date`).

---

## Deletes (M1)

- **TimeEntry:** hard delete.
- **Project:** delete only when no entries remain.
- **Client:** delete only when no projects remain.

No soft-archive in M1.

---

## Enums

`BillingMode` and `EntryMode` are Python `StrEnum` types persisted as **`text`**
columns (`FerroField(db_type="text")`), not native DB enums. Values are the enum’s
string values (e.g. `hourly`, `duration`). This keeps `auto_migrate` and future
Alembic revisions straightforward when adding enum members.

**Hydration:** ferro-orm **≥ 0.10.5** (fix in [PR #66](https://github.com/syn54x/ferro-orm/pull/66),
closes [#65](https://github.com/syn54x/ferro-orm/issues/65)) registers enum fields at
class definition and coerces text columns back to `StrEnum` on cold fetch. TTD pins
`ferro-orm>=0.10.5`.

`enum_value()` in `ttd.core.models.enums` remains useful for display and for any
value that might still be a plain `str` (e.g. tests); prefer `.value` on hydrated
models when the type is known to be `StrEnum`.

Historical repro scripts: `docs/upstream/` (fail on ferro ≤ 0.10.3). Agents: see
`.cursor/rules/ferro-upstream.mdc`.

---

## Export rounding (M3)

- **`rounding_increment_minutes`** on `Client` and `Project` — positive integer minutes, or `null` for no rounding.
- Project unset inherits the client value at export time (same pattern as hourly rates).
- Rounding applies **at export only** via `round_hours_up` in `ttd.core.domain.rounding`; stored `billable_hours` are never modified.
- Direction is **round up** to the next increment boundary.

Configure via CLI: `ttd client add|update --rounding-minutes N`, `ttd project add|update --rounding-minutes N`, and `--clear-rounding` on update.

---

## Period CSV export (M3)

- Service entrypoint: `export_period_csv` in `ttd.core.services.export`.
- CLI: `ttd export --from YYYY-MM-DD --to YYYY-MM-DD` with optional `--client`, `--project`, `--project-id`, `--output`.
- **CSV** (default): stdout when `--output` is omitted, or when `--output` ends with `.csv`. Combined detail + summary blocks as in M3.
- **XLSX**: when `--output` ends with `.xlsx` — workbook with **Log** and **Summary** sheets; same column schemas as the CSV blocks (including `row_type`). Row 1 on each sheet is bold with a frozen pane and an unstyled Excel table (`headerRowCount=1`). Requires `--output` (no stdout). Best for Excel / Google Sheets.
- **Numbers**: when `--output` ends with `.numbers` — native Apple Numbers workbook with the same **Log** / **Summary** sheets and columns; each table sets `num_header_rows=1` so Numbers opens with proper header rows. Requires `--output` (no stdout).
- **Detail rows** (`row_type=DETAIL`): duration entries rolled up by project + work date + note; interval entries one row each with `time_from` / `time_to`.
- **Summary rows** (`row_type=SUMMARY`): project and client subtotals for billable hours; dollar amounts for hourly projects only.
- Hourly projects populate `currency`, `rate`, and `amount`; fixed-price projects export hours only.
- Non-billable rows are included with `billable=no` and empty `amount`; dollar summaries exclude them.

---

## Backup and restore (M5)

- Core: `backup_database` / `restore_database` in `ttd.core.db_admin`.
- CLI: `ttd db backup PATH`, `ttd db restore PATH --yes`.
- After `close_db()`, backup uses stdlib `sqlite3.Connection.backup()` into a single file (WAL consolidated into the destination).
- Restore validates the source file, deletes the active `db_path` and any `-wal` / `-shm` sidecars, copies the backup into place, and reconnects via `init_db()`.

---

## Portable ledger JSON (M5)

- Service: `ttd.core.services.portable_json` — `export_ledger_json`, `import_ledger_json`, `parse_ledger_json`.
- CLI: `ttd export json --output PATH` (required), `ttd import json PATH --yes`.
- Document shape: `schema_version` (currently `1`), `exported_at`, `clients`, `projects`, `time_entries` with stable UUIDs and billing fields.
- Import policy: **skip-by-ID** — records whose `id` already exists are not overwritten. Requires `--yes` when at least one new row would be inserted.
- On failure mid-import, inserted rows from that run are rolled back.

---

## Related

- Requirements: `brainstorms/2026-05-24-billing-ledger-requirements.md`
- Plan: `plans/2026-05-25-002-feat-billing-ledger-plan.md`
