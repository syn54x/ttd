# Agent notes

TTD is a terminal-native billable ledger. Read `STRATEGY.md` for product scope before adding features.

## Layout

- `src/ttd/core/` — async domain services and persistence; **all business logic here**
- `src/ttd/cli/`, `api/`, `tui/` — thin adapters only (parse → call core → format); CLI output uses **Rich** (`ttd.cli.console`, `ttd.cli.output`)
- `tests/` — pytest; mirror `core` structure for service tests
- `docs/solutions/` — documented solutions to past problems (bugs, patterns, workflow), organized by category with YAML frontmatter (`module`, `tags`, `problem_type`); relevant when implementing or debugging in documented areas

## Commands

```bash
uv sync
just check             # ruff + ty (required before finishing agent work)
prek run --all-files   # full check suite (CI parity)
uv run pytest
uv run ttd
```

**Done means green:** run `just check` and fix failures before handoff. See `.cursor/rules/quality-gate.mdc`.

## Dependency management (uv)

- Use **uv**, not `pip install` / ad-hoc virtualenvs.
- **One-off inline scripts**: prefer `uv run --with <pkg> python -c "..."` (add `--no-project` if you want an isolated ephemeral env).
- **Project deps**: update `pyproject.toml` via `uv add <pkg>` (or `uv remove <pkg>`), then `uv sync`.
- If you need to test something against the project environment, prefer `uv run ...` over invoking `python` directly.

## Design standards

Full guide: [`docs/design/general.md`](docs/design/general.md)

**Non-negotiables:**

- Domain logic only in `ttd.core` — never duplicate across CLI, API, or TUI
- Async throughout core; surfaces bridge at the boundary (`asyncio` / cyclopts / Litestar lifespan)
- Pydantic `BaseModel` for structured data; `ConfigDict(use_attribute_docstrings=True)` on documented models
- Raise in core at the point of failure; catch at surface adapters for user-facing messages and exit codes
- Prefer clarity over pattern adherence — extract functions/classes only when they earn their existence (see guide §1–2)
- ferro-orm models in core for SQLite; separate DTOs when export/API shapes differ
- Conventional commits; changelog updated at release via commitizen (not per-PR)

## Conventions

- Python 3.14, uv, ruff, ty, pytest + Hypothesis for billing-sensitive invariants
- Local-first SQLite; no cloud sync in v1
- M1–M4: CLI-first ledger + CSV; M5–M7 add TUI, PDF/Markdown invoices, API — see `docs/roadmap.md`

## Planning artifacts

CE skills default to `docs/brainstorms/` and `docs/plans/` — **use repo-root paths in this project** (see `.cursor/rules/ce-planning-artifacts.mdc`):

- Requirements: `brainstorms/*-requirements.md`
- Plans: `plans/*-plan.md`

Do not add new CE requirements or plans under `docs/` (Zensical site only).

## Ferro-orm upstream

Persistence uses [syn54x/ferro-orm](https://github.com/syn54x/ferro-orm). If behavior looks like an ORM/runtime bug (especially cold DB reads vs in-memory instances), follow `.cursor/rules/ferro-upstream.mdc`: confirm with a minimal repro, **ask the user** before opening issues or feature requests on ferro-orm, and keep workarounds in TTD until a release fixes it.
