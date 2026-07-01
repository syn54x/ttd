"""`ttd import PATH` — bring entries in from csv/json/xlsx/numbers."""

from pathlib import Path
from typing import Annotated, cast

from cyclopts import Parameter

from ttd.cli._output import console, success, table, warn
from ttd.cli._run import TtdApp, with_db
from ttd.core.errors import TtdError
from ttd.core.money import format_hours
from ttd.interchange import base as formats
from ttd.interchange import importer
from ttd.interchange.json_io import read_metadata


def register(app: TtdApp) -> None:
    @app.command(name="import")
    @with_db
    async def import_(
        path: Annotated[Path, Parameter(help="File to import")],
        *,
        fmt: Annotated[str | None, Parameter(name=["--format", "-f"])] = None,
        client: Annotated[str | None, Parameter(help="Client for rows missing one")] = None,
        project: Annotated[
            str | None, Parameter(name=["--project", "-p"], help="Project for rows missing one")
        ] = None,
        on_conflict: Annotated[str, Parameter(help="skip|update|duplicate")] = "skip",
        create_missing: Annotated[bool, Parameter(help="Create unknown clients/projects")] = False,
        dry_run: bool = False,
    ) -> None:
        """Import entries; matches by uid then content, never touches invoiced entries."""
        if on_conflict not in ("skip", "update", "duplicate"):
            raise TtdError(
                f"--on-conflict must be skip, update, or duplicate (got '{on_conflict}')"
            )
        conflict_mode = cast("importer.OnConflict", on_conflict)
        if not path.is_file():
            raise TtdError(f"No such file: {path}")
        fmt_obj = formats.detect_format(path, fmt)
        raws = fmt_obj.reader(path)
        metadata = read_metadata(path) if fmt_obj.name == "json" else {}

        plan = await importer.build_plan(
            raws,
            on_conflict=conflict_mode,
            default_client=client,
            default_project=project,
        )
        written = 0
        if not dry_run and plan.importable:
            written = await importer.apply_plan(
                plan, create_missing=create_missing, metadata=metadata
            )

        # Restore expenses from JSON metadata (skip on dry_run or non-JSON files).
        if not dry_run and metadata.get("expenses"):
            from ttd.interchange.importer import restore_expenses

            n = await restore_expenses(
                metadata, on_conflict=conflict_mode, create_missing=create_missing
            )
            if n:
                success(f"Restored {n} expense{'s' if n != 1 else ''}")

        t = table("Action", "Rows")
        t.add_row("new", str(len(plan.new)))
        t.add_row("update", str(len(plan.update)))
        t.add_row("skip", str(len(plan.skip)))
        t.add_row("errors", str(len(plan.errors)))
        console.print(t)
        for row, message in plan.errors[:10]:
            warn(f"row {row}: {message}")
        if len(plan.errors) > 10:
            warn(f"...and {len(plan.errors) - 10} more errors")
        for record, reason in plan.skip[:5]:
            console.print(
                f"[muted]skip {record.date} {record.client}/{record.project} "
                f"{format_hours(record.seconds)}: {reason}[/muted]"
            )
        if len(plan.skip) > 5:
            console.print(f"[muted]...and {len(plan.skip) - 5} more skipped[/muted]")

        if dry_run:
            if plan.missing_clients or plan.missing_projects:
                missing = ", ".join(
                    sorted(plan.missing_clients | {f"{c}/{p}" for c, p in plan.missing_projects})
                )
                warn(f"Would need --create-missing for: {missing}")
            console.print("[muted]Dry run — nothing written.[/muted]")
        else:
            success(f"Imported {written} entr{'y' if written == 1 else 'ies'} from {path}")
