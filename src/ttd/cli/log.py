"""`ttd log "TIMESPEC"` — natural-language retrospective logging."""

import sys
from datetime import datetime
from typing import Annotated

from cyclopts import Parameter
from pydantic import BaseModel, Field
from rich.prompt import Confirm

from ttd.cli._interactive import interactive_fill
from ttd.cli._output import console, success, warn
from ttd.cli._pickers import (
    describe_timespec,
    project_choices,
    split_project_choice,
    validate_timespec,
)
from ttd.cli._run import TtdApp, with_db
from ttd.config.loader import get_settings
from ttd.core.errors import TtdError
from ttd.core.money import format_hours
from ttd.services import entries as svc


class LogInput(BaseModel):
    spec: str = Field(
        json_schema_extra={
            "prompt": "Time (e.g. 'today 9am to 5pm', '2h')",
            "validate": validate_timespec,
        }
    )
    project: str = Field(
        json_schema_extra={"prompt": "Project", "widget": "select", "choices": project_choices}
    )
    note: str | None = Field(None, json_schema_extra={"prompt": "Note (optional)"})
    tags: str | None = Field(None, json_schema_extra={"prompt": "Tags (optional)"})
    billable: bool = Field(True, json_schema_extra={"prompt": "Billable?"})


def register(app: TtdApp) -> None:
    @app.command(name="log")
    @with_db
    async def log(
        spec: Annotated[
            str | None, Parameter(help='e.g. "today 8am to 5pm", "2h", "yesterday 9-11:30"')
        ] = None,
        *,
        project: Annotated[str | None, Parameter(name=["--project", "-p"])] = None,
        client: str | None = None,
        note: Annotated[str | None, Parameter(name=["--note", "-n"])] = None,
        tags: Annotated[str | None, Parameter(help="Comma-separated")] = None,
        billable: bool = True,
        force: Annotated[bool, Parameter(help="Log even if it overlaps")] = False,
        interactive: Annotated[
            bool, Parameter(name=["--interactive", "-i"], help="Fill remaining fields via a form")
        ] = False,
    ) -> None:
        """Log completed work from a natural-language time spec."""
        now = datetime.now()
        settings = get_settings()

        if interactive:
            data = await interactive_fill(
                LogInput,
                {"spec": spec, "project": project, "note": note, "tags": tags},
            )
            spec = data.spec
            project, picked_client = split_project_choice(data.project)
            client = client or picked_client
            note, tags = data.note, data.tags
            billable = billable and data.billable
            console.print(f"[muted]→ {describe_timespec(spec)}[/muted]")
        if spec is None:
            raise TtdError('TIMESPEC is required, e.g. `ttd log "today 9am to 5pm"` (or use -i)')

        project_slug, client_slug = svc.resolve_project_slugs(settings, project, client)
        try:
            entry = await svc.log_entry(
                spec,
                project_slug,
                client_slug,
                now=now,
                note=note or "",
                tags=tags or "",
                billable=billable and settings.defaults.billable,
                settings=settings,
                force=force,
            )
        except svc.OverlapError as exc:
            warn(str(exc))
            if not sys.stdin.isatty() or not Confirm.ask("Log it anyway?"):
                raise
            entry = await svc.log_entry(
                spec,
                project_slug,
                client_slug,
                now=now,
                note=note or "",
                tags=tags or "",
                billable=billable and settings.defaults.billable,
                settings=settings,
                force=True,
            )

        when = (
            f"{entry.started_at:%-I:%M%p}–{entry.ended_at:%-I:%M%p}".lower()
            if entry.started_at
            else "duration only"
        )
        success(
            f"Logged [accent]{format_hours(entry.seconds)}[/accent] "
            f"on {entry.work_date:%a %b %-d} ({when})"
        )
