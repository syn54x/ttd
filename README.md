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

## Period export

Close a billing period to CSV (default), XLSX, or Numbers. Format is inferred from `--output`; omit it to print CSV to stdout.

```bash
# CSV to stdout
ttd export --from 2026-05-01 --to 2026-05-31

# CSV, XLSX, or Numbers file
ttd export --from 5/1 --to 5/31 --output period.csv
ttd export --from 5/1 --to 5/31 --client Acme --output period.xlsx
ttd export --from 5/1 --to 5/31 --output period.numbers

# Optional export-time round-up (minutes); set on client or project
ttd client add Acme --rate 150 --rounding-minutes 15
ttd project update --client Acme --name Website --rounding-minutes 30
```

Detail rows roll up duration entries by project, day, and note; interval entries stay one row each. A summary section (same file or Summary sheet) totals billable hours and hourly dollars by project and client. See [docs/design/data-layer.md](docs/design/data-layer.md) for column schemas.

## Configuration

Persistent settings live in layered TOML files plus optional `TTD_*` env overrides. Inspect effective values and source layers with `ttd config show`; set local or global keys with `ttd config set`.

```bash
ttd config show
ttd config init
ttd config set data_dir ~/.local/share/ttd
ttd config set --global clock_format 24h
ttd config get db_filename
```

Global file: `~/.config/ttd/ttd.toml`. Local override: nearest `ttd.toml` walking up from cwd. Precedence: env → local → global → defaults. See [docs/design/data-layer.md](docs/design/data-layer.md#configuration-m4).

## Backup and portable JSON

```bash
ttd db backup ~/Backups/ttd.db
ttd db restore ~/Backups/ttd.db --yes
ttd export json --output ledger.json
ttd import json ledger.json --yes
```

See [docs/getting-started.md](docs/getting-started.md) for restore warnings and merge-by-ID import semantics.

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

### Failed publish recovery

If PyPI rejects the upload (for example **filename reuse** after a deleted version), `main` may already have the bump commit and tag while PyPI has nothing:

1. Bump to a **new** version (PyPI never reuses deleted filenames).
2. Update `CHANGELOG.md` for that version.
3. Delete stray or failed tags (`git push origin :refs/tags/v0.x.y`).
4. Push `main`, tag the recovery version, push the tag.
5. Re-run the workflow with **publish only** (skips `cz bump`):

   ```bash
   gh workflow run release.yml --ref main -f publish_only=true
   gh run watch --workflow release.yml
   ```

Also delete accidental non-semver tags (e.g. `list`) — they break `git describe` and commitizen.

### Smoke test after publish

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
