# TTD

Terminal-native billable ledger for solo developers who invoice by the hour.

See the [roadmap](roadmap.md) for milestone sequencing and [STRATEGY.md](https://github.com/syn54x/ttd/blob/main/STRATEGY.md) for product direction.

## Prerequisites

- [uv](https://docs.astral.sh/uv/)
- Python 3.14 (`uv python install 3.14`)

## Setup

```bash
git clone https://github.com/syn54x/ttd.git
cd ttd
uv sync
prek install
```

## Run checks

CI runs the same command as local full-repo verification:

```bash
prek run --all-files
```

## Run TTD

```bash
uv run ttd
```

## Pull requests

- Use [conventional commits](https://www.conventionalcommits.org/) for commit messages and PR titles.
- You do **not** need to edit `CHANGELOG.md` on PRs — it is updated at release time.
