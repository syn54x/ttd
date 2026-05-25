# Data layer

**Date:** 2026-05-25
**Status:** Active
**Applies to:** `src/ttd/core/models/`, `src/ttd/core/db.py`

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

- `init_db()` imports `ttd.core.models` before `connect` so all `Model` subclasses register metadata.
- `auto_migrate=True` creates or updates tables to match models.
- **Tests:** each test uses an isolated `Settings(data_dir=tmp_path)` database; `reset_db_state` closes the engine between tests.
- **Local dev:** if the on-disk `ttd.db` drifts after model changes, delete `~/.local/share/ttd/ttd.db` (or your `TTD_DATA_DIR`) and reconnect.

### Pre–user-testing: Alembic cutover (deferred)

When the schema stabilizes (e.g. before M2 dogfooding / external testers):

1. Freeze model definitions; avoid drive-by column renames.
2. Generate `alembic/` and the initial revision from ferro models (`ferro-orm[alembic]`).
3. Check in revision files; document `alembic upgrade head` for long-lived databases.
4. Decide whether tests keep `auto_migrate` on tmp DBs or run `upgrade head` — either is fine if CI is consistent.

Until then, **do not** add `alembic/` to the repo for routine M1 work.

---

## Entity model

| Entity | Table | Notes |
|--------|-------|--------|
| `Client` | `client` | Default hourly rate + ISO 4217 currency |
| `Project` | `project` | `billing_mode`: hourly or fixed_price; unique `(client_id, name)` |
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

## Related

- Requirements: `brainstorms/2026-05-24-billing-ledger-requirements.md`
- Plan: `plans/2026-05-25-002-feat-billing-ledger-plan.md`
