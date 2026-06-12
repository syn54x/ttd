# Installation

## Requirements

- Python 3.13 or newer
- Any modern terminal (the TUI uses 24-bit color; every recent terminal qualifies)

ttd is published on PyPI as **`ttd-ledger`**; the installed command is `ttd`.

## Install with uv (recommended)

```bash
uv tool install ttd-ledger
```

[uv](https://docs.astral.sh/uv/) manages an isolated environment for the tool
and puts `ttd` on your PATH. If you don't have a Python 3.13 available,
`uv python install 3.13` first.

## Install with pipx or pip

```bash
pipx install ttd-ledger
# or, into the active environment:
pip install ttd-ledger
```

## Shell completion

```bash
ttd --install-completion
```

Detects your shell (bash, zsh, or fish), installs the completion script, and
adds a source line to your shell startup file. Restart your shell afterwards.

## Verify the install

```bash
ttd --version   # or: ttd -V
ttd --help
```

## Explore safely with demo data

Seed a database with demo clients, projects, and about three months of
entries:

```bash
ttd db seed-demo
```

To keep experiments out of your real ledger, point ttd at a throwaway file
for the session:

```bash
TTD_DB_PATH=/tmp/demo.db ttd db seed-demo
TTD_DB_PATH=/tmp/demo.db ttd
```

`ttd db seed-demo --reset --yes` wipes and reseeds. See
[Data & backups](../guides/data-and-backups.md) for where the real database
lives.

## Upgrading and uninstalling

```bash
uv tool upgrade ttd-ledger
uv tool uninstall ttd-ledger
```

Your data is never touched by an upgrade or uninstall — it lives in its own
file (see [Data & backups](../guides/data-and-backups.md)).
