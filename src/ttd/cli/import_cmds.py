"""`ttd import` — merge portable ledger JSON into the local database."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from cyclopts import App, Parameter

from ttd.cli.console import muted, success
from ttd.cli.errors import cli_exit
from ttd.cli.runtime import ensure_db
from ttd.core.services.portable_json import import_ledger_json, parse_ledger_json

app = App(name="import", help="Import portable ledger data.")


@app.command
async def json(
    source: Annotated[
        Path,
        Parameter(help="Path to a ledger JSON file from `ttd export json`."),
    ],
    *,
    yes: Annotated[
        bool,
        Parameter(
            name=["-y", "--yes"],
            help="Confirm merge import when new records will be inserted.",
        ),
    ] = False,
) -> None:
    """Merge ledger records from JSON, skipping ids that already exist."""
    try:
        await ensure_db()
        document = parse_ledger_json(source.read_text(encoding="utf-8"))
        summary = await import_ledger_json(document, confirmed=yes)
        success(f"Imported ledger data from {source}")
        muted(
            "Clients: "
            f"{summary.clients_inserted} inserted, "
            f"{summary.clients_skipped} skipped; "
            "Projects: "
            f"{summary.projects_inserted} inserted, "
            f"{summary.projects_skipped} skipped; "
            "Entries: "
            f"{summary.entries_inserted} inserted, "
            f"{summary.entries_skipped} skipped."
        )
    except BaseException as exc:
        cli_exit(exc)
