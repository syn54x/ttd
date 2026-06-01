"""`ttd db` — local database location and maintenance."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from cyclopts import App, Parameter
from rich.table import Table

from ttd.cli.console import info, muted, success
from ttd.cli.errors import cli_exit
from ttd.core import db_admin

app = App(
    name="db",
    help="Manage the local ledger database (SQLite).",
)


def _format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KiB"
    return f"{size / (1024 * 1024):.1f} MiB"


def _print_location(location: db_admin.DbLocation) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("[bold]data_dir[/bold]", str(location.data_dir))
    table.add_row("[bold]db_path[/bold]", str(location.db_path))
    table.add_row("[bold]dsn[/bold]", location.db_dsn)
    if location.exists:
        size = (
            _format_bytes(location.size_bytes)
            if location.size_bytes is not None
            else "—"
        )
        table.add_row("[bold]file[/bold]", f"[green]exists[/green] ({size})")
    else:
        table.add_row("[bold]file[/bold]", "[dim]not created yet[/dim]")
    info(table)


@app.command
async def where() -> None:
    """Show where the ledger database file lives."""
    try:
        _print_location(db_admin.describe_db())
    except BaseException as exc:
        cli_exit(exc)


@app.command
async def migrate() -> None:
    """Apply the current model schema to the database (ferro auto_migrate)."""
    try:
        location = await db_admin.apply_schema()
        success(f"Schema applied at {location.db_path}")
    except BaseException as exc:
        cli_exit(exc)


@app.command
async def backup(
    destination: Annotated[
        Path,
        Parameter(help="Path to write the backup SQLite file."),
    ],
) -> None:
    """Copy the ledger database to a backup file."""
    try:
        result = await db_admin.backup_database(destination)
        success(f"Backed up ledger to {result.destination}")
        muted(f"Size: {_format_bytes(result.size_bytes)}")
    except BaseException as exc:
        cli_exit(exc)


@app.command
async def restore(
    source: Annotated[
        Path,
        Parameter(help="Path to a backup SQLite file."),
    ],
    *,
    yes: Annotated[
        bool,
        Parameter(
            name=["-y", "--yes"],
            help="Confirm destructive restore (replaces the current ledger).",
        ),
    ] = False,
) -> None:
    """Replace the active ledger database with a backup file."""
    try:
        location = await db_admin.restore_database(source, confirmed=yes)
        success(f"Restored ledger at {location.db_path}")
    except BaseException as exc:
        cli_exit(exc)


@app.command
async def reset(
    *,
    yes: Annotated[
        bool,
        Parameter(
            name=["-y", "--yes"],
            help="Confirm destructive reset (deletes all ledger data).",
        ),
    ] = False,
) -> None:
    """Delete the database file and recreate empty tables."""
    try:
        location = await db_admin.reset_database(confirmed=yes)
        success(f"Reset database at {location.db_path}")
        muted("All clients, projects, and time entries were removed.")
    except BaseException as exc:
        cli_exit(exc)
