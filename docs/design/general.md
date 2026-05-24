# General Software Design Guide

**Date:** 2026-05-24
**Status:** Approved
**Applies to:** TTD (`src/ttd/`, `tests/`)

---

## Overview

This document defines the general coding philosophy and design preferences for TTD. Domain-specific guides (for example `docs/design/data-layer.md` when added) extend this baseline; they do not replace it.

The preferred style is a **pragmatic mix of OOP and functional design**. Neither extreme is the goal: not everything in a class, and not everything as a flat bag of functions. Classes organize related behavior and state; standalone functions are fine for genuinely independent operations. The test is always clarity and navigability, not pattern adherence.

**TTD architecture overlay:** All billing and ledger domain logic lives in `ttd.core`. `ttd.cli`, `ttd.api`, and `ttd.tui` are thin async adapters — they parse input, call core services, and format output. See `AGENTS.md` and `STRATEGY.md`.

---

## Core Decisions

| Decision | Choice | Rationale |
|---|---|---|
| OOP vs functional | Mix both pragmatically | Classes when behavior/state/resources cluster together; standalone functions when an operation is truly independent |
| When to write a class | Shared behavior, shared state, resource encapsulation, or interface contract | Four valid drivers — any one is sufficient |
| When to write a function | Called from multiple places, complex enough to name, or materially clarifies the call site | Single-use inline logic does not need to be extracted |
| DRY | Important, but not at the expense of over-abstraction | Duplication is sometimes the clearer choice; premature abstraction is a cost, not a virtue |
| Structured data | Pydantic models by default | Validation, serialization, and type safety in one; `pydantic.dataclasses` for simple internal structs that never cross a boundary |
| Persistence models | ferro-orm `Model` + Pydantic in `ttd.core` | ORM models for SQLite; separate DTOs when export/API shapes differ from storage |
| Inheritance | Pragmatic | Use when genuinely the clearest model; composition otherwise; no deep hierarchies |
| Error handling | Raise at the point of failure; catch at the recovery point | Don't swallow errors; don't add catch blocks that don't meaningfully handle the failure |
| Async | Async throughout `ttd.core` | ferro-orm and Litestar are async-native; surfaces bridge at the boundary |

---

## 1. Class Design

Reach for a class when one or more of the following applies:

1. **Grouping related state** — several pieces of data naturally belong together and methods operate on that shared state.
2. **Grouping related behavior** — a family of related operations that would otherwise be loose functions scattered across a module (e.g., a `PeriodExporter` with several steps).
3. **Encapsulating a resource** — anything with setup/teardown, connection state, or lifecycle (DB sessions, export writers).
4. **Defining a contract** — an abstract base class or protocol that multiple implementations will satisfy.

When functions share a subject, make it a class.

```python
# Avoid — loose functions with a shared implicit subject
def parse_duration_input(raw: str) -> timedelta: ...
def parse_interval_input(raw: str) -> tuple[datetime, datetime]: ...
def validate_entry_input(raw: str, mode: EntryMode) -> None: ...
def normalize_entry_note(raw: str) -> str: ...


# Prefer — the subject is explicit; the module is navigable
class EntryInputParser:
    """Parses retroactive time entry input (duration or interval)."""

    def parse(self, raw: str, mode: EntryMode) -> EntryDraft:
        """Entry point. Returns a validated draft ready for persistence."""
        self._validate(raw, mode)
        if mode is EntryMode.DURATION:
            return self._parse_duration(raw)
        return self._parse_interval(raw)

    def _validate(self, raw: str, mode: EntryMode) -> None: ...
    def _parse_duration(self, raw: str) -> EntryDraft: ...
    def _parse_interval(self, raw: str) -> EntryDraft: ...
```

Not everything needs a class. A standalone utility with no natural siblings belongs at module level.

```python
# Fine as a standalone function — no siblings, no shared state
def round_hours(hours: Decimal, rule: RoundingRule) -> Decimal:
    ...
```

---

## 2. Function Design

Extract logic into a named function when at least one of the following is true:

- It is called from **more than one place**
- It is **complex enough to warrant a name**
- Extracting it makes the **call site materially clearer**

If none of these apply, keep the logic inline.

```python
# Avoid — unnecessary extraction
def _entry_cache_key(client_id: UUID, project_id: UUID) -> str:
    return f"{client_id}:{project_id}"

async def log_entry(client_id: UUID, project_id: UUID, draft: EntryDraft) -> Entry:
    key = _entry_cache_key(client_id, project_id)
    ...


# Prefer — inline when obvious and used once
async def log_entry(client_id: UUID, project_id: UUID, draft: EntryDraft) -> Entry:
    ...
```

DRY applies when the same logic appears in multiple places — not preemptively for single-use code.

```python
# Good extraction — shared by export and CLI summary
def format_billable_hours(hours: Decimal) -> str:
    """Formats billable hours for display, e.g. 1.5 → '1.50h'."""
    return f"{hours.quantize(Decimal('0.01'))}h"
```

---

## 3. Data Models

Use **Pydantic `BaseModel`** as the default for structured data that crosses service boundaries (CLI input, export payloads, API responses).

Prefer **attribute docstrings** over `Field(description=...)`. Set `use_attribute_docstrings=True` on every model that uses them.

```python
from pydantic import BaseModel, ConfigDict, Field

class TimeEntryDraft(BaseModel):
    model_config = ConfigDict(use_attribute_docstrings=True)

    client_id: UUID
    """Client this entry bills to."""
    project_id: UUID
    """Project under the client."""
    hours: Decimal | None = None
    """Duration when the user logged by hours remembered."""
    started_at: datetime | None = None
    """Interval start when the user logged time-in/out."""
    ended_at: datetime | None = None
    """Interval end when the user logged time-in/out."""
    note: str = ""
    """Optional description shown on export."""
```

Reserve `Field(...)` for constraints (`gt`, `ge`, etc.); document with an attribute docstring on the next line when possible.

**Dataclasses** (`pydantic.dataclasses.dataclass`) are acceptable for simple internal structs that never serialize and never cross a module boundary — for example a bundle of objects passed into a single service method.

If a struct starts crossing boundaries or needs validation, migrate it to `BaseModel`.

**ferro-orm models** live in `ttd.core` and represent persisted ledger entities. Keep export/API DTOs separate when their shape diverges from storage.

---

## 4. Inheritance & Composition

Use inheritance when you have shared implementation and concrete variants. Use composition otherwise.

```python
# Inheritance appropriate — shared export pipeline, format-specific writers
class BasePeriodExporter:
    """Loads ledger rows for a period and delegates formatting."""

    async def export(self, period: BillingPeriod, writer: ExportWriter) -> Path:
        rows = await self._load_rows(period)
        return await writer.write(rows)

    async def _load_rows(self, period: BillingPeriod) -> list[BillableRow]:
        raise NotImplementedError


class CsvPeriodExporter(BasePeriodExporter):
    async def _load_rows(self, period: BillingPeriod) -> list[BillableRow]:
        ...
```

```python
# Composition appropriate — unrelated capabilities
class LedgerService:
    def __init__(self, repository: EntryRepository, rounding: RoundingService) -> None:
        self._repository = repository
        self._rounding = rounding
```

Avoid deep hierarchies. A third level of inheritance usually means the abstraction should be reconsidered.

---

## 5. Error Handling

Raise at the point of failure. Propagate to the layer that can recover or present a useful message.

```python
# Avoid — silent failure; caller proceeds with bad state
async def get_project(project_id: UUID) -> Project | None:
    try:
        return await Project.get(project_id)
    except Exception:
        return None


# Prefer — explicit failure
async def get_project(project_id: UUID) -> Project:
    project = await Project.get(project_id)
    if project is None:
        raise LookupError(f"Project {project_id} not found")
    return project
```

Catch at the **recovery point** — typically the surface adapter (CLI command, API route, TUI action):

```python
# CLI: translate domain errors into exit codes and user-facing messages
@app.command
async def log(...) -> None:
    try:
        await entry_service.create(...)
    except LookupError as e:
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(1) from e
```

Use specific exception types. Bare `Exception` is acceptable at outer boundaries for logging/cleanup, but re-raise or exit with context.

---

## 6. Module Organization

A module should have one clear subject. Split when the subject genuinely forks — not because the file grew long.

- **Classes are the primary unit of organization** within a module.
- **Module-level code** (constants, `__all__`) is fine.
- **Don't split prematurely.** One well-organized module beats several micro-modules with cross-imports.

```
src/ttd/core/
  services/
    entries.py      # EntryService, related helpers — one subject
    export.py       # PeriodExporter, CSV formatting
  models/           # ferro-orm + pydantic types when shared across services
  config.py         # Settings only
  db.py             # connect lifecycle only
```

Surfaces stay thin:

```
src/ttd/cli/main.py     # cyclopts commands → core services
src/ttd/api/app.py      # Litestar routes → core services
src/ttd/tui/app.py      # Textual widgets → core services
```

---

## Related documents

- `AGENTS.md` — agent entrypoint and repo commands
- `STRATEGY.md` — product scope and v1 boundaries
- `docs/design/data-layer.md` — add when documenting ferro-orm schema and migration conventions
