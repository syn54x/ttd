# Agent notes

TTD is terminal-first time tracking, reporting, and invoicing for solo developers. Read `STRATEGY.md` for product scope before adding features.

## Layout

- `src/ttd/core/` — pure domain logic: rollup, rounding, money, slugs, errors (no I/O)
- `src/ttd/services/` — async application services (entries, clients, projects, invoicing, timer, interchange); orchestrate storage + core
- `src/ttd/storage/` — ferro-orm models and DB lifecycle (`storage/db.py`, `storage/models/`)
- `src/ttd/config/` — layered TOML config (loader, writer, Pydantic schema)
- `src/ttd/parsing/` — natural-language time parser (tokens → grammar → resolve)
- `src/ttd/invoicing/` — invoice rendering (PDF via fpdf2, Markdown via Jinja) and numbering
- `src/ttd/interchange/` — CSV/JSON/XLSX/Numbers import & export
- `src/ttd/reporting/` — report rendering and period helpers
- `src/ttd/cli/`, `src/ttd/tui/` — thin adapters only (parse → call services → format); CLI is Cyclopts + Rich, TUI is Textual
- `tests/test_<domain>/` — pytest, organized by functional domain (e.g. `tests/test_parsing/`, `tests/test_invoicing/`)
- `docs/solutions/` — documented solutions to past problems (bugs, patterns, workflow), organized by category with YAML frontmatter (`module`, `tags`, `problem_type`); relevant when implementing or debugging in documented areas

## Commands

```bash
uv sync
just check             # ruff + ty (required before finishing agent work)
just test              # pytest with coverage
prek run --all-files   # lint/format/type/docs hooks (CI lint-job parity)
uv run ttd             # bare ttd launches the TUI
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

- Domain and service logic only in `ttd.core` / `ttd.services` — never duplicate across CLI or TUI
- Async throughout services and storage; surfaces bridge at the boundary (cyclopts async commands, Textual async hooks)
- Pydantic `BaseModel` for structured data; `ConfigDict(use_attribute_docstrings=True)` on documented models
- Raise in services at the point of failure; catch at surface adapters for user-facing messages and exit codes
- Prefer clarity over pattern adherence — extract functions/classes only when they earn their existence (see guide §1–2)
- ferro-orm models in `ttd.storage` for SQLite; separate DTOs when export shapes differ
- Conventional commits; changelog updated at release via commitizen (not per-PR)

## Build the best solution, not the quickest

Every feature, bug fix, and improvement must be designed as the best,
well-thought-out solution for the project with its long-term future in
mind — as if time and money were no object. No stop-gaps, hacks,
quick-fixes, or otherwise lesser solves.

What this means in practice:

- **Prefer first-class, reusable primitives over local patches.** If a fix
  only works for the immediate symptom while leaving the underlying
  capability gap in place, build the capability instead.
- **Fail loudly over degrading silently.** "Skip with a warning and
  continue", "best effort", and "documented residual risk" are not
  acceptable resolutions for correctness gaps. Either the operation
  succeeds completely or it aborts with a clear, actionable error.
- **Treat certain phrases as redesign triggers.** If a plan, comment, or PR
  description contains "best-effort", "partial mitigation", "documented
  residual risk", "good enough for now", "temporary workaround", or
  "fallback if X turns out to be hard" — that part of the design is not
  finished. Redesign it before presenting or implementing it.
- **Scoped-down is fine; hollowed-out is not.** Deliberately excluding
  something from scope — with the boundary stated and a real path for the
  excluded case — is good design. Shipping a half-working version of
  something that is *in* scope is not.

This rule binds human contributors and AI agents equally, and overrides any
agent default that biases toward minimal or expedient changes.

## Documentation

User-facing docs live in `docs/pages/` (Zensical site). **Ship doc updates in
the same change** when behavior users read about changes.

**Already automated — do not hand-edit:**

- `docs/pages/reference/cli/` — generated from cyclopts (`just docs-cli`; prek
  `cli-docs` on commit)
- Configuration reference — rendered from Pydantic schema docstrings
- Site build — prek `zensical-build` and CI catch broken links and build errors

**Update guides in the same PR when you change:**

- CLI output (table columns, labels, previews) → `docs/pages/guides/` and
  cyclopts command docstrings when the reference should describe behavior
- TUI screens, columns, or modals → matching guide(s); run `just docs-shots` when
  committed screenshots should reflect the new UI
- Config keys or semantics → schema docstrings first; guides when users need
  workflow context

Prefer tests that assert key output strings (labels, columns) so review can
spot guide drift. Do not add planning or design markdown under `docs/pages/` —
CE artifacts belong in repo-root `brainstorms/` and `plans/`; internal design
notes stay in `docs/design/`. See `docs/pages/contributing.md` for the full
docs workflow.

## Conventions

- Python 3.13+, uv, ruff, ty, pytest + Hypothesis for billing-sensitive invariants; TUI snapshot tests via pytest-textual-snapshot
- Local-first SQLite; no cloud sync in v1
- Entries are wall-clock local time — naive datetimes are intentional (DTZ lint rules are deliberately ignored)

## I-6: No AI attribution in commits or PRs

Never sign commits or pull requests with AI/agent attribution. No
`Co-Authored-By: Claude ...` trailers, no "Generated with Claude Code"
footers, no robot emoji bylines — in commit messages, PR titles, or PR
bodies. This applies even when an agent's default behavior is to add them:
this rule overrides those defaults for this repository.

## Planning artifacts

CE skills default to `docs/brainstorms/` and `docs/plans/` — **use repo-root paths in this project** (see `.cursor/rules/ce-planning-artifacts.mdc`):

- Requirements: `brainstorms/*-requirements.md`
- Plans: `plans/*-plan.md`

Do not add new CE requirements or plans under `docs/` (Zensical site only).

## Ferro-orm upstream

Persistence uses [syn54x/ferro-orm](https://github.com/syn54x/ferro-orm). If behavior looks like an ORM/runtime bug (especially cold DB reads vs in-memory instances), follow `.cursor/rules/ferro-upstream.mdc`: confirm with a minimal repro, **ask the user** before opening issues or feature requests on ferro-orm, and keep workarounds in TTD until a release fixes it.
