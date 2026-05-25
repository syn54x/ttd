# Local task shortcuts. Requires: https://github.com/casey/just

set dotenv-load := true

default:
    @just --list

db-seed *ARGS:
    uv run python -m ttd.core.seed {{ARGS}}
