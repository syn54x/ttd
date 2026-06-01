"""`ttd export` — period CSV, XLSX, and Numbers export."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated
from uuid import UUID

from cyclopts import App, Parameter

from ttd.cli.errors import cli_exit
from ttd.cli.runtime import (
    ensure_db,
    parse_date,
    require_id,
    resolve_client,
    resolve_project,
)
from ttd.core.exceptions import ValidationError
from ttd.core.schemas import ExportPeriod
from ttd.core.services.export import (
    export_period_csv,
    export_period_numbers,
    export_period_xlsx,
)
from ttd.core.services.portable_json import export_ledger_json, render_ledger_json

app = App(
    name="export",
    help="Export billing periods or the full ledger.",
)

_EXPORT_SUFFIXES = {".csv": "csv", ".xlsx": "xlsx", ".numbers": "numbers"}


def _export_format(output: Path | None) -> str:
    if output is None:
        return "csv"
    suffix = output.suffix.lower()
    fmt = _EXPORT_SUFFIXES.get(suffix)
    if fmt is None:
        raise ValidationError(
            f"Unsupported export extension '{suffix}' on {output.name}; "
            "use .csv, .xlsx, or .numbers"
        )
    return fmt


@app.default
async def export_period(
    *,
    from_date: Annotated[
        str, Parameter(name="--from", help="Period start date (YYYY-MM-DD).")
    ],
    to_date: Annotated[
        str, Parameter(name="--to", help="Period end date (YYYY-MM-DD).")
    ],
    client: Annotated[str | None, Parameter(name="--client")] = None,
    project: Annotated[str | None, Parameter(name="--project")] = None,
    project_id: Annotated[UUID | None, Parameter(name="--project-id")] = None,
    output: Annotated[
        Path | None,
        Parameter(
            name="--output",
            help=(
                "Write export file (.csv, .xlsx, or .numbers); "
                "stdout if omitted (CSV only)."
            ),
        ),
    ] = None,
) -> None:
    """Export a billing period to CSV, XLSX, or Numbers (format from --output)."""
    try:
        await ensure_db()
        export_fmt = _export_format(output)
        period = ExportPeriod(
            from_date=parse_date(from_date),
            to_date=parse_date(to_date),
        )
        owner = (
            await resolve_client(client_id=None, client_name=client)
            if client is not None
            else None
        )
        resolved = (
            await resolve_project(
                project_id=project_id,
                client=owner,
                project_name=project,
            )
            if project is not None or project_id is not None
            else None
        )
        resolved_project_id = (
            require_id(resolved.id, "project") if resolved is not None else None
        )
        client_id = owner.id if owner is not None else None
        if export_fmt == "csv":
            csv_text = await export_period_csv(
                period,
                client_id=client_id,
                project_id=resolved_project_id,
            )
            if output is not None:
                output.write_text(csv_text, encoding="utf-8")
            else:
                sys.stdout.write(csv_text)
            return

        assert output is not None
        if export_fmt == "xlsx":
            payload = await export_period_xlsx(
                period,
                client_id=client_id,
                project_id=resolved_project_id,
            )
        else:
            payload = await export_period_numbers(
                period,
                client_id=client_id,
                project_id=resolved_project_id,
            )
        output.write_bytes(payload)
    except BaseException as exc:
        cli_exit(exc)


@app.command
async def json(
    *,
    output: Annotated[
        Path | None,
        Parameter(
            name="--output",
            help="Write full-ledger JSON to this path (required).",
        ),
    ] = None,
) -> None:
    """Export the full ledger to JSON."""
    try:
        if output is None:
            raise ValidationError(
                "Full-ledger JSON export requires --output PATH "
                "(for example: ttd export json --output ledger.json)."
            )
        await ensure_db()
        document = await export_ledger_json()
        output.write_text(render_ledger_json(document), encoding="utf-8")
    except BaseException as exc:
        cli_exit(exc)
