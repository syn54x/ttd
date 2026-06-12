# Contributing

ttd is developed on [GitHub](https://github.com/syn54x/ttd). Issues and pull
requests welcome.

## Development setup

Requires [uv](https://docs.astral.sh/uv/) and [just](https://github.com/casey/just):

```bash
git clone https://github.com/syn54x/ttd.git
cd ttd
just setup          # uv sync + git hooks (prek)
uv run ttd          # run from source
just tui            # TUI with live reload
just db-seed        # demo data to play against
```

## Checks

```bash
just check             # ruff + ty — the fast local gate
just test              # pytest with coverage
prek run --all-files   # full CI-lint parity: lint, format, types, docs build
```

CI runs the prek suite on every PR plus the test matrix (Ubuntu/macOS ×
Python 3.13/3.14).

## Working on the docs

The public site is built by [Zensical](https://zensical.org) from
`docs/pages/` (everything else under `docs/` is internal and not published).

```bash
just docs-serve     # live-reloading local preview
just docs-cli       # regenerate reference/cli/ from the cyclopts app
just docs-shots     # regenerate TUI screenshots (SVG) from demo data
just docs-gifs      # re-record GIF walkthroughs (requires `brew install vhs`)
```

`docs/pages/reference/cli/` is **generated — don't hand-edit it**. A commit
hook regenerates it and fails if it drifted; the configuration reference is
rendered from the schema docstrings via mkdocstrings. Screenshots and GIFs
are committed artifacts, regenerated manually when the UI changes.

## Pull requests

- [Conventional commits](https://www.conventionalcommits.org/) for commit
  messages and PR titles.
- Don't edit `CHANGELOG.md` — it's generated at release time.
