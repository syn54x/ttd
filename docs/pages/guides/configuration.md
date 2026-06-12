# Configuration

ttd needs no setup — every setting has a sensible default, and config files
are created only when you first write to one. This guide covers where
settings live and the handful you'll actually want to change. The complete
catalog is in the [configuration reference](../reference/configuration.md).

## Where settings live

Four layers, highest precedence first:

1. **`TTD_*` environment variables** — per-process overrides
2. **A local `.ttd.toml`** — found by walking up from the current directory
   (stops at your home directory); per-project overrides
3. **The global config file** — `~/.config/ttd/config.toml` (respects
   `XDG_CONFIG_HOME`; `TTD_CONFIG_DIR` overrides the directory outright)
4. **Built-in defaults**

## Reading your config

```console
$ ttd config get billing.rounding
$ ttd config list                 # every option with its effective value + description
$ ttd config list --origin        # …plus which layer set each one
$ ttd config path                 # where the files are (or would be)
```

## Changing settings

```console
$ ttd config set billing.rounding up        # writes the global file
$ ttd config set defaults.project api-rewrite --local   # writes ./.ttd.toml
$ ttd config unset defaults.project --local
$ ttd config edit                           # open in $EDITOR
```

Keys are dotted `section.key` names matching the TOML structure.

## Per-project config with .ttd.toml

Drop a `.ttd.toml` in a repo and ttd picks it up from anywhere inside:

```toml
[defaults]
client = "acme-corp"
project = "api-rewrite"
```

Now `ttd start`, `ttd log "2h"`, and the TUI quick log all know where the
time goes — per codebase, no flags.

## Environment variables

Any setting: `TTD_<SECTION>__<KEY>` (double underscore):

```bash
TTD_BILLING__ROUNDING=up ttd invoice create --client acme-corp --dry-run
TTD_DISPLAY__THEME=ttd-light ttd
```

One shortcut: `TTD_DB_PATH=/tmp/demo.db` points at a different database —
the easy way to sandbox (see [Data & backups](data-and-backups.md)).

## Common recipes

```console
$ ttd config set business.default_hourly_rate 150   # price unrated projects
$ ttd config set display.time_format 24h            # 24-hour clock
$ ttd config set display.week_start sunday          # US-style weeks
$ ttd config set tax.set_aside_rate 0.30            # 30% tax set-aside
$ ttd config set invoice.tax_rate 0.08              # 8% tax on invoices
```

## Every setting

Types, defaults, and descriptions for all nine sections:
[Configuration reference](../reference/configuration.md).
