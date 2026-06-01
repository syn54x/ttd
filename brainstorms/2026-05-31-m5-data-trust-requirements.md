---
date: 2026-05-31
topic: m5-data-trust
origin: docs/roadmap.md (M5 — Data trust & hardening); STRATEGY.md (Data trust & portability track)
---

# M5 — Data trust & hardening

## Summary

Make the ledger safe to stake client invoices on: **`ttd db backup` / `ttd db restore`** copy the SQLite database to a user-chosen path; **`ttd export json` / `ttd import json`** provide a full-ledger portable dump with merge-by-ID import (skip records whose IDs already exist); **Hypothesis property tests** cover rounding math; and **pytest coverage `fail_under`** applies to the entire `ttd` package. Post-export edit visibility is explicitly out of scope for M5.

---

## Problem Frame

M1–M4 delivered a working CLI ledger, period export (CSV/XLSX/Numbers), and layered TOML config. The product can close a billing period from TTD alone, but trust gaps remain: there is no supported backup/restore path beyond manual file copy, no portable ledger format outside SQLite, rounding logic lacks property-test coverage, and CI reports coverage without enforcing a floor. A mistaken edit, disk failure, or silent export/rounding regression would undermine the strategy metrics — especially billing-period ledger completion and post-export correction rate — before TUI and invoice formats add more surfaces.

---

## Actors

- A1. **Solo developer:** Backs up the ledger before risky operations, restores after failure, and moves data between machines without hand-rolling SQLite copies or ad-hoc SQL.
- A2. **Maintainer:** Relies on coverage and property tests as quality gates before M6–M8 surfaces multiply adapter code.

---

## Key Flows

- F1. **Backup ledger**
  - **Trigger:** User runs `ttd db backup` with a destination path (or is prompted for one).
  - **Steps:** Resolve active `db_path` from settings → copy SQLite file (and related WAL sidecar files when present) to destination → confirm path and size.
  - **Outcome:** User has a restorable snapshot at a known location.
  - **Covered by:** R1, R2, R3

- F2. **Restore ledger**
  - **Trigger:** User runs `ttd db restore` from a backup path, with explicit confirmation.
  - **Steps:** Validate source file exists → warn that restore replaces current ledger → require confirmation flag → replace active database file → schema need not be re-applied if file is valid.
  - **Outcome:** TTD reads the restored ledger on next command.
  - **Covered by:** R1, R2, R4

- F3. **Portable JSON export**
  - **Trigger:** User runs `ttd export json` with optional output path.
  - **Steps:** Read full ledger (clients, projects, time entries, and fields needed to reconstruct relationships) → write structured JSON → confirm output location.
  - **Outcome:** Human-readable, diff-friendly archive independent of SQLite.
  - **Covered by:** R5, R6

- F4. **Merge JSON import**
  - **Trigger:** User runs `ttd import json` from a JSON file, with explicit confirmation when the operation adds records.
  - **Steps:** Parse and validate JSON shape → for each entity, insert only when `id` is not already present in the database → skip duplicates silently or with a summary count → report imported vs skipped counts.
  - **Outcome:** Records from another machine or backup JSON are added without overwriting existing rows.
  - **Covered by:** R7, R8

---

## Requirements

**Backup and restore**

- R1. **`ttd db backup`** accepts a user-chosen destination path and copies the active ledger database file from the location reported by `ttd db where`.
- R2. Backup includes SQLite sidecar files required for a consistent restore when the engine uses WAL mode (e.g. `-wal`, `-shm` when present).
- R3. Backup succeeds only when the source database exists; otherwise fail with a clear error (no empty backup file).
- R4. **`ttd db restore`** accepts a source backup path, requires explicit confirmation before replacing the active database, and replaces the current ledger file at the configured `db_path`.
- R5. Restore validates that the source is a readable SQLite file before overwriting the active ledger.
- R6. User-facing documentation describes backup/restore behavior, what files are copied, and that restore is destructive to the current ledger.

**Portable JSON export**

- R7. **`ttd export json`** writes a full-ledger JSON document containing all clients, projects, and time entries with stable IDs and fields needed to reconstruct the billing graph (including rates, rounding increments, entry modes, and billable flags).
- R8. JSON export is read-only on ledger data — no mutation of stored entries during export.
- R9. Default output path follows the same conventions as period export (stdout or `-o` / `--output` path); exact default deferred to planning.

**Merge JSON import**

- R10. **`ttd import json`** reads a JSON document produced by R7 (same schema version) and merges into the active ledger.
- R11. Merge policy: **skip** any record whose `id` already exists in the database — no overwrite of existing clients, projects, or entries in M5.
- R12. Import reports counts: records inserted vs skipped (by entity type when practical).
- R13. Import validates JSON structure and rejects files that would leave the ledger in an invalid state (e.g. entry referencing missing project after import completes).
- R14. Import requires explicit confirmation when it will insert one or more new records.

**Test hardening — Hypothesis**

- R15. Property tests cover export rounding behavior: `round_hours_up` respects increment boundaries, monotonicity (rounding never decreases billable hours), and inheritance of client vs project rounding increment.
- R16. Existing Hypothesis tests for interval/duration hour calculations remain passing; M5 adds rounding coverage, not a rewrite of hours tests.

**Test hardening — coverage gate**

- R17. Enable pytest **`fail_under`** for coverage of the entire **`ttd`** package (core, CLI, API, TUI).
- R18. Threshold and any omit/exclude rules are chosen during planning so `uv run pytest` fails CI when coverage drops below the agreed floor; current baseline is approximately 68% total package coverage.

---

## Acceptance Examples

- AE1. **Covers R1, R2, R3.** Given a populated ledger at `db_path`, when user runs `ttd db backup /tmp/ttd-backup.db`, then `/tmp/ttd-backup.db` exists, opens as SQLite, and contains the same client/project/entry row counts as the source.
- AE2. **Covers R4, R5.** Given a valid backup file and an empty or different ledger at `db_path`, when user runs `ttd db restore /tmp/ttd-backup.db` without confirmation, then the command refuses; with confirmation, subsequent `ttd client list` reflects the backup's data.
- AE3. **Covers R7, R8.** Given two clients and five entries, when user runs `ttd export json -o ledger.json`, then `ledger.json` parses as JSON and includes all entities with IDs and relationship fields intact.
- AE4. **Covers R10, R11, R12.** Given ledger A exported to `ledger.json` and an empty ledger B, when user imports `ledger.json` into B, then all records appear in B. Given ledger B already contains client `id=C1`, when user imports a JSON file that also contains `id=C1`, then C1 is skipped (not updated) and the import summary reports one skipped client.
- AE5. **Covers R15.** Given any non-negative decimal hours and a positive rounding increment in minutes, when `round_hours_up` runs, then result hours are ≥ input hours and are an integer multiple of the increment expressed in hours.
- AE6. **Covers R17, R18.** Given the agreed `fail_under` threshold is configured, when a billing-critical module loses test coverage below the threshold, then `uv run pytest` exits non-zero.

---

## Success Criteria

- A solo developer can back up and restore the ledger using documented CLI commands without manually locating files via `ttd db where` alone.
- Ledger data can leave SQLite as JSON and be merged into another TTD database without overwriting existing rows by ID.
- Rounding and hour-calculation regressions are caught by automated tests before M6 TUI work begins.
- `just check` / CI pytest runs enforce the coverage floor on the whole package.
- Planning (`ce-plan`) does not need to invent backup semantics, JSON entity shape, merge policy, or coverage scope.

---

## Scope Boundaries

- Post-export edit visibility, export snapshots, entry `created_at` / `updated_at` audit fields, and change logs — explicitly deferred; user chose to skip for M5
- Destructive JSON import (replace entire ledger) — out of scope; restore remains the SQLite backup path
- CSV or other portable formats — JSON only in M5
- JSON import that **updates** existing records by ID — out of scope without timestamps; merge is skip-only
- Cloud sync, encryption at rest, multi-machine conflict resolution — strategy "not working on"
- TUI/API routes for backup or JSON import — CLI first; thin surfaces in later milestones if needed
- PDF/Markdown invoices, TUI product screens, Litestar API routes — M6–M8
- Consuming `timezone` / `clock_format` in log/list — follow-up from M4 (separate brainstorm)

---

## Key Decisions

- **Skip post-export edit audit:** Trust features focus on durability and test gates, not change tracking after period close.
- **CLI backup/restore with user-chosen paths:** Matches `ttd db` namespace; no opinionated backup directory layout in v1.
- **Full-ledger JSON dump:** Single artifact for portability and inspection; not a row-per-period export variant.
- **Merge import skip-by-ID:** Safe default that avoids silent overwrites; re-importing corrected rows requires manual edit or a future update-import milestone.
- **Whole-package `fail_under`:** Quality gate spans adapters too, not only `ttd.core` — raises work to cover CLI paths but matches user's billing-sensitivity bar before more surfaces land.

---

## Dependencies / Assumptions

- M1–M4 ledger, export, and config are stable; JSON export uses the same domain entities as SQLite models.
- `ttd db where` and settings-derived `db_path` remain the source of truth for which file backup/restore targets.
- ferro-orm `auto_migrate` policy continues; restored or imported databases must match current model schema (or restore fails clearly).
- Hypothesis and pytest-cov are already dev dependencies.
- Current total package coverage is approximately 68%; reaching a meaningful `fail_under` may require new CLI/integration tests in the same milestone.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R2][Technical] Exact WAL checkpoint/copy sequence so backup is crash-consistent without requiring the user to stop all TTD processes.
- [Affects R9][Technical] Default output path for `export json` (stdout vs required `-o`) and JSON schema version field naming.
- [Affects R13][Technical] Import ordering when entries reference projects and projects reference clients; transactional rollback behavior on partial failure.
- [Affects R18][Technical] Target `fail_under` percentage, whether to ratchet from current baseline, and coverage omit rules for `if __name__ == "__main__"` / placeholder TUI/API entrypoints.
- [Affects R6][Product] Where backup/restore docs live (README section vs `docs/getting-started.md` vs design doc cross-link).
