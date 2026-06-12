# Local task shortcuts. Requires: https://github.com/casey/just

set dotenv-load := true

default:
    @just --list

# Lint and type-check (ruff + ty). Run before considering agent work done.
check:
    uv run ruff check .
    uv run ruff format --check .
    uv run ty check src

# Install Python deps (uv) and git hooks (prek via uv).
setup:
    uv sync
    uv run prek install

test *args:
    uv run pytest {{args}}

# Auto-fix lint findings and reformat.
fix:
    uv run ruff check --fix src tests
    uv run ruff format src tests

# Run the TUI with live reload for development.
tui:
    uv run textual run --dev ttd.tui.app:TtdApp

db-seed *ARGS:
    uv run ttd db seed-demo {{ARGS}}

# Regenerate the CLI reference pages from the cyclopts app.
docs-cli:
    uv run python scripts/gen_cli_docs.py

# Regenerate the TUI screenshots (SVG) from seeded demo data.
docs-shots:
    uv run python scripts/gen_screenshots.py

# Re-record the GIF walkthroughs. Requires vhs (brew install vhs).
docs-gifs:
    #!/usr/bin/env bash
    set -euo pipefail
    rm -rf /tmp/ttd-vhs.db /tmp/ttd-vhs-config
    TTD_DB_PATH=/tmp/ttd-vhs.db TTD_CONFIG_DIR=/tmp/ttd-vhs-config uv run python scripts/seed_docs_demo.py
    for tape in docs/tapes/*.tape; do vhs "$tape"; done

# Serve the docs site locally with live reload.
docs-serve:
    uv run zensical serve

# Build wheel/sdist and verify the ttd CLI from the artifact (pre-release smoke).
release-smoke:
    rm -rf dist/
    uv build
    uv run --with dist/*.whl --no-project -- ttd --help
    uv run --with dist/*.whl --no-project -- python -c "import ttd; print(ttd.__version__)"

# CI checks, artifact smoke, then trigger the GitHub Release workflow on main.
release:
    #!/usr/bin/env bash
    set -euo pipefail
    branch="$(git rev-parse --abbrev-ref HEAD)"
    if [[ "${branch}" != "main" ]]; then
      echo "error: checkout main before releasing (on ${branch})" >&2
      exit 1
    fi
    if [[ -n "$(git status --porcelain)" ]]; then
      echo "error: uncommitted changes; commit or stash before releasing" >&2
      exit 1
    fi
    git fetch origin main
    upstream="$(git rev-parse @{u} 2>/dev/null || true)"
    if [[ -n "${upstream}" ]]; then
      local_sha="$(git rev-parse HEAD)"
      remote_sha="$(git rev-parse origin/main)"
      if [[ "${local_sha}" != "${remote_sha}" ]]; then
        echo "error: main is not synced with origin/main; push or pull first" >&2
        exit 1
      fi
    fi
    uv run prek run --all-files
    just release-smoke
    gh workflow run release.yml --ref main
    echo "Triggered Release workflow on main."
    echo "Watch: gh run watch --workflow release.yml"
