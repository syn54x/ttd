"""`ttd export PATH` — write entries to csv/json/xlsx/numbers."""

from datetime import date
from pathlib import Path
from typing import Annotated

from cyclopts import Parameter

from ttd.cli._output import success
from ttd.cli._run import TtdApp, with_db
from ttd.core.errors import TtdError
from ttd.interchange import base as formats
from ttd.services.interchange_svc import export_records


def _parse_date(raw: str | None, what: str) -> date | None:
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise TtdError(f"{what} must be YYYY-MM-DD (got '{raw}')") from exc


def register(app: TtdApp) -> None:
    @app.command(name="export")
    @with_db
    async def export(
        path: Annotated[Path, Parameter(help="Output file; format inferred from extension")],
        *,
        fmt: Annotated[str | None, Parameter(name=["--format", "-f"])] = None,
        project: Annotated[str | None, Parameter(name=["--project", "-p"])] = None,
        client: str | None = None,
        date_from: Annotated[str | None, Parameter(name="--from")] = None,
        date_to: Annotated[str | None, Parameter(name="--to")] = None,
        invoiced: Annotated[
            bool | None,
            Parameter(name="--invoiced", negative="--uninvoiced", help="Only (un)billed entries"),
        ] = None,
    ) -> None:
        """Export entries (csv, json, xlsx, or Apple Numbers)."""
        fmt_obj = formats.detect_format(path, fmt)
        records, meta = await export_records(
            project_slug=project,
            client_slug=client,
            date_from=_parse_date(date_from, "--from"),
            date_to=_parse_date(date_to, "--to"),
            invoiced=invoiced,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        fmt_obj.writer(records, path, meta)
        success(f"Exported {len(records)} entr{'y' if len(records) == 1 else 'ies'} to {path}")
