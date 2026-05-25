# Local task shortcuts. Requires: https://github.com/casey/just

set dotenv-load := true

default:
    @just --list

# Install Python deps (uv) and git hooks (prek via uv).
setup:
    uv sync
    uv run prek install

db-seed *ARGS:
    uv run python -m ttd.core.seed {{ARGS}}

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
