# TTD

Terminal-native billable ledger for solo developers who invoice by the hour.

## Install

PyPI distribution: **`ttd-ledger`**. CLI command: **`ttd`**.

```bash
uv tool install ttd-ledger
ttd --help
```

One-off: `uvx ttd-ledger`.

## Quick start (development)

```bash
just setup
prek run --all-files
uv run ttd
```

## Development

| Command | Purpose |
|---------|---------|
| `just check` | Ruff lint/format check + ty (fast gate before PR or agent handoff) |
| `just setup` | Install dependencies (`uv sync`) and git hooks (`uv run prek install`) |
| `uv sync` | Install dependencies only |
| `prek install` | Install git hooks only |
| `prek run --all-files` | Run all checks (same as CI) |
| `uv run ttd` | CLI (Rich tables; health check by default) |
| `just db-seed` | Seed local DB with demo clients, projects, and entries |
| `just release-smoke` | Build wheel/sdist and verify `ttd` from the artifact |
| `just release` | Full checks + smoke, then trigger GitHub Release workflow |
| `uv run ttd-api` | Litestar API (scaffold) |
| `uv run ttd-tui` | Textual TUI (scaffold) |

## Release (maintainers)

### One-time setup

1. **PyPI project** — Register [ttd-ledger](https://pypi.org/manage/projects/) (name must match `project.name` in `pyproject.toml`).
2. **Trusted publishing** — On that project: *Publishing* → *Add a new pending publisher* → **GitHub**:

   | Field | Value |
   |-------|-------|
   | Owner | `syn54x` |
   | Repository | `ttd` |
   | Workflow name | `release.yml` |
   | Environment | `pypi` |

3. **GitHub environment** — Repo *Settings* → *Environments* → create **`pypi`** (no secrets required for OIDC).
4. **GitHub Pages** — *Settings* → *Pages* → **Source: GitHub Actions**.

### Pre-release check

```bash
just release-smoke
```

Builds the wheel/sdist and runs `ttd --help` from the artifact (same layout CI publishes).

### Publish

1. Complete [one-time setup](#one-time-setup) above.
2. Merge to `main` with conventional commits since the last tag.
3. From a clean, pushed `main`:

   ```bash
   just release
   ```

   Runs CI checks, `release-smoke`, then triggers the **Release** workflow (`cz bump`, PyPI publish, GitHub Release, docs deploy).

   Watch progress: `gh run watch --workflow release.yml`

4. Smoke test after publish:

   ```bash
   uvx ttd-ledger --help
   uv tool install ttd-ledger
   ttd
   ```

## Roadmap

Milestone sequencing and v1 scope: [docs/roadmap.md](docs/roadmap.md). Product direction: [STRATEGY.md](STRATEGY.md).

## Architecture

- `ttd.core` — async domain services and SQLite (ferro-orm)
- `ttd.cli` — cyclopts CLI adapter
- `ttd.api` — Litestar API adapter (scaffold)
- `ttd.tui` — Textual TUI adapter (scaffold)

Domain logic lives only in `ttd.core`. Surfaces are thin adapters.
