---
date: 2026-05-24
topic: foundational-techstack
---

# Foundational Tech Stack

## Summary

Establish TTD’s Python monorepo foundation: uv-managed dependencies, async service-oriented core on SQLite (ferro-orm), namespace-scaffolded CLI/API/TUI surfaces, full dev tooling, GitHub Actions CI on PR and main, and a manual release pipeline that publishes to PyPI and GitHub Pages.

---

## Problem Frame

TTD is a greenfield repo with strategy defined (`STRATEGY.md`) but no application code, tooling, or CI yet. Before billing-ledger features can ship, the project needs a durable foundation: consistent local dev experience, shared business logic callable from multiple surfaces, quality gates on every change, and a repeatable release path. Without these decisions locked, planning and implementation would repeatedly re-litigate language version, package layout, async model, ORM choice, and release mechanics.

---

## Requirements

**Language & runtime**
- R1. Target Python 3.14 as the project runtime and CI matrix baseline.
- R2. Use uv for dependency management, virtual environments, and lockfile discipline.

**Package layout**
- R3. Organize as a single installable package with namespace subpackages: `ttd.core` (shared services), `ttd.cli`, `ttd.api`, `ttd.tui`.
- R4. Scaffold CLI (cyclopts), API (Litestar), and TUI (Textual) from day one; they may be empty placeholders until their respective tracks start.
- R5. All business functionality lives in `ttd.core` services; CLI, API, and TUI are thin adapters that invoke those services — no duplicated domain logic across surfaces.

**Data layer**
- R6. Use ferro-orm as the ORM for local-first SQLite storage, aligned with `STRATEGY.md` data-trust track.
- R7. Service layer is async throughout (`await` for database and domain operations); all surfaces integrate via asyncio (e.g., CLI entrypoints use `asyncio.run` or equivalent async dispatch).

**Configuration & validation**
- R8. Use pydantic for data models and validation; pydantic-settings for configuration loading.

**Dev tooling**
- R9. Lint with ruff; type-check with ty.
- R10. Local git hooks via Prek (pre-commit equivalent); CI runs the same checks non-interactively.
- R11. Documentation authored with Zensical; CI verifies docs build on PR and main.

**Testing**
- R12. Test with pytest; use Hypothesis for property-based tests on billing-sensitive logic (rounding, duration/interval invariants) as those domains are implemented.

**CI — pull request & main**
- R13. GitHub Actions runs on every PR and on pushes to main.
- R14. PR and main workflows execute at minimum: ruff, ty, pytest (with coverage reporting), docs build verification, and conventional-commit message enforcement.
- R15. PR CI does not require CHANGELOG.md edits; changelog is generated at release time via commitizen from conventional commit history.

**CI — release (manual)**
- R16. Release workflow is triggered manually (`workflow_dispatch`), not automatically on merge or tag push.
- R17. Release workflow: bump version (commitizen), compile/update changelog (commitizen), build and publish package to PyPI, build and publish Zensical docs to GitHub Pages.
- R18. Users install released versions via PyPI (`uv tool install`, `uvx`, or equivalent).

---

## Acceptance Examples

- AE1. **Covers R13, R14.** Given an open PR with failing ruff violations, when CI runs, the workflow fails and blocks merge until lint passes.
- AE2. **Covers R15.** Given a PR that adds a feature with a properly formatted conventional commit message but no CHANGELOG edit, when CI runs, the PR passes (changelog enforcement is commit-format, not file-edit).
- AE3. **Covers R16, R17.** Given a maintainer triggers the release workflow manually, when it completes successfully, the PyPI package version is bumped, CHANGELOG reflects commits since last release, and GitHub Pages serves updated docs.
- AE4. **Covers R4, R5.** Given the scaffold is in place before v1 ledger features ship, when a developer runs the CLI, API, or TUI entrypoint, each surface starts without error and delegates to (possibly empty) core services — no domain logic duplicated in surface packages.

---

## Success Criteria

- A new contributor can clone the repo, install with uv, run lint/type/test/docs locally via Prek and documented commands, and get the same results CI would produce.
- Shared services in `ttd.core` can be invoked from CLI without copy-paste when API/TUI tracks begin — no refactor of domain logic required to add a new surface.
- A manual release produces an installable PyPI artifact and published docs without ad-hoc steps.
- Planning (`ce-plan`) can proceed without re-deciding language, ORM, async model, package layout, or CI/release mechanics.

---

## Scope Boundaries

- Billing ledger domain models, export rules, rounding logic, and CSV output — deferred to product tracks in `STRATEGY.md`
- Populating Litestar routes or Textual screens with real functionality — scaffold only in this foundation; v1 ships CLI per strategy
- Cloud sync, team features, Raycast/MCP integrations
- Homebrew, apt, or other distribution channels beyond PyPI
- Automatic release on every merge to main
- uv workspace multi-package layout (single namespace package chosen instead)
- SQLAlchemy or other ORM as a fallback — ferro-orm is the chosen path (Approach A)

---

## Key Decisions

- **Approach A (proposed stack as-is):** Full async architecture with ferro-orm, Python 3.14, and all tooling from day one — chosen over stability-first (defer ferro-orm/3.14) and uv workspace split.
- **Single namespace package:** One PyPI distribution with `ttd.*` subpackages — simpler for solo-dev project than multi-member uv workspace.
- **Scaffold all surfaces, ship CLI first:** CLI, API, and TUI packages exist from foundation; product v1 focus remains terminal capture per `STRATEGY.md`.
- **Async everywhere:** Service layer is fully async to align ferro-orm and Litestar; CLI bridges with asyncio at the boundary.
- **commitizen + conventional commits:** PRs enforce commit message format; changelog and version bump happen in manual release workflow, not per-PR CHANGELOG edits.
- **Manual release only:** No auto-publish on merge; maintainer explicitly triggers release workflow.

---

## Dependencies / Assumptions

- ferro-orm (currently ~0.10.x) provides sufficient SQLite support and optional Alembic migrations via `ferro-orm[alembic]` when schema work begins.
- Python 3.14 is available in CI runners and supported by ferro-orm, Litestar, Textual, and other chosen dependencies at scaffold time.
- `ty` refers to Astral’s type checker, used alongside ruff in the uv toolchain.
- Prek provides pre-commit-style local hooks; hook config mirrors CI check commands.
- GitHub repository hosting enables Actions workflows and GitHub Pages for docs.
- Coverage threshold and exact CI matrix details (OS variants, minimum Python pin policy) are deferred to planning.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R14][Technical] Exact coverage threshold and whether CI fails below it or reports only.
- [Affects R6][Needs research] ferro-orm migration workflow specifics (auto_migrate vs Alembic-only) once ledger schema is defined.
- [Affects R10][Technical] Prek hook configuration file layout and which checks run locally vs CI-only.
- [Affects R17][Technical] PyPI trusted publishing vs API token setup for GitHub Actions release workflow.
- [Affects R11][Technical] Zensical project config location and GitHub Pages deployment branch/path.
