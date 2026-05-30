"""`ttd config` — inspect and edit layered TOML configuration."""

from __future__ import annotations

from typing import Annotated

from cyclopts import App, Parameter
from rich.table import Table

from ttd.cli.console import info, muted, stdout, success
from ttd.cli.errors import cli_exit, cli_exit_cancelled
from ttd.cli.interactive import require_interactive_tty
from ttd.core import db_admin
from ttd.core.config import (
    CONFIG_KEYS,
    get_config_value,
    get_settings,
    init_config,
    resolve_sources,
    set_config_value,
)
from ttd.core.config_files import find_local_config, global_config_path

app = App(
    name="config",
    help="Inspect and edit TTD configuration (TOML + env).",
)


@app.command
async def show() -> None:
    """Show effective config values and their source layer."""
    try:
        settings = get_settings()
        sources = resolve_sources(settings)
        table = Table(show_header=True, box=None, padding=(0, 2))
        table.add_column("[bold]key[/bold]")
        table.add_column("[bold]effective[/bold]")
        table.add_column("[bold]source[/bold]")
        for key in CONFIG_KEYS:
            value = getattr(settings, key)
            effective = str(value)
            table.add_row(key, effective, sources[key])
        info(table)
        muted(f"global: {global_config_path()}")
        local_path = find_local_config()
        if local_path is not None:
            muted(f"local: {local_path}")
        else:
            muted("local: none")
    except BaseException as exc:
        cli_exit(exc)


@app.command
async def get(key: str) -> None:
    """Print one effective config value (plain stdout, scriptable)."""
    try:
        stdout.print(get_config_value(key))
    except BaseException as exc:
        cli_exit(exc)


@app.command
async def init(
    *,
    local: Annotated[
        bool,
        Parameter(
            name="--local",
            help="Write a local ttd.toml in cwd instead of the global file.",
        ),
    ] = False,
) -> None:
    """Interactive first-run setup for TTD configuration."""
    try:
        require_interactive_tty()
        from ttd.cli import collect

        values = await collect.collect_config_init(global_=not local)
        path = init_config(
            data_dir=values.data_dir,
            db_filename=values.db_filename,
            clock_format=values.clock_format,
            global_=not local,
            create_data_dir=values.create_data_dir,
        )
        scope = "global" if not local else "local"
        success(f"Wrote {scope} config at {path}")
        if values.run_migrate:
            location = await db_admin.apply_schema()
            success(f"Schema applied at {location.db_path}")
        else:
            muted("Run `ttd db migrate` when you are ready to create the database.")
    except KeyboardInterrupt:
        cli_exit_cancelled()
    except BaseException as exc:
        cli_exit(exc)


@app.command
async def set(
    key: str,
    value: str,
    *,
    global_: Annotated[
        bool,
        Parameter(
            name="--global",
            help="Write the global config file instead of local ttd.toml.",
        ),
    ] = False,
) -> None:
    """Set a config key in local or global TOML."""
    try:
        path = set_config_value(key, value, global_=global_)
        scope = "global" if global_ else "local"
        success(f"Set {key} in {scope} config at {path}")
        muted("Run the next command in a new shell if you changed data_dir.")
    except BaseException as exc:
        cli_exit(exc)
