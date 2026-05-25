# TTD

Terminal-native billable ledger for solo developers who invoice by the hour.

## Quick start

```bash
uv sync
prek install
prek run --all-files
uv run ttd
```

## Development

| Command | Purpose |
|---------|---------|
| `uv sync` | Install dependencies |
| `prek install` | Install git hooks |
| `prek run --all-files` | Run all checks (same as CI) |
| `uv run ttd` | CLI health check |
| `uv run ttd-api` | Litestar API (scaffold) |
| `uv run ttd-tui` | Textual TUI (scaffold) |

## Release (maintainers)

1. Configure [PyPI trusted publishing](https://docs.pypi.org/trusted-publishers/) for this repository's `release.yml` workflow.
2. Enable GitHub Pages with **Source: GitHub Actions**.
3. Trigger the **Release** workflow manually on `main`. Commitizen auto-bumps semver from conventional commits since the last tag, updates `CHANGELOG.md`, publishes to PyPI, and deploys docs.

## Roadmap

Milestone sequencing and v1 scope: [docs/roadmap.md](docs/roadmap.md). Product direction: [STRATEGY.md](STRATEGY.md).

## Architecture

- `ttd.core` — async domain services and SQLite (ferro-orm)
- `ttd.cli` — cyclopts CLI adapter
- `ttd.api` — Litestar API adapter (scaffold)
- `ttd.tui` — Textual TUI adapter (scaffold)

Domain logic lives only in `ttd.core`. Surfaces are thin adapters.
