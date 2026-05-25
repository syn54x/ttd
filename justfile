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
