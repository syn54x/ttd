# TTD

Terminal-first time tracking, reporting, and invoicing for solo developers.

See the [roadmap](roadmap.md) for milestone sequencing and [STRATEGY.md](https://github.com/syn54x/ttd/blob/main/STRATEGY.md) for product direction.

## Prerequisites

- [uv](https://docs.astral.sh/uv/)
- Python 3.13+ (`uv python install 3.13`)

## Setup

```bash
git clone https://github.com/syn54x/ttd.git
cd ttd
uv sync
prek install
```

## Run checks

```bash
prek run --all-files   # lint, format, types, docs build
uv run pytest          # test suite (CI runs this on Ubuntu/macOS, 3.13/3.14)
```

## Install (released)

```bash
uv tool install ttd-ledger
ttd --help
```

## Run TTD (development)

```bash
uv run ttd
```

## Pull requests

- Use [conventional commits](https://www.conventionalcommits.org/) for commit messages and PR titles.
- You do **not** need to edit `CHANGELOG.md` on PRs — it is updated at release time.
