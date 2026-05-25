# Getting started

See the [repository README](https://github.com/syn54x/ttd/blob/main/README.md) for clone, install, and check commands.

## Checks

```bash
prek run --all-files
```

This runs ruff, ty, pytest (with coverage), and a Zensical docs build — the same hooks CI executes on every pull request and push to `main`.

## Demo data

```bash
just db-seed
```

Loads demo clients, projects, and time entries into the local SQLite database (`~/.local/share/ttd/ttd.db` by default). Safe to re-run: it skips if demo data is already present. Use `just db-seed -- --force` to replace demo rows only.
