"""Root-level timer commands: start, stop, status, cancel."""

from datetime import datetime
from typing import Annotated

from cyclopts import Parameter
from pydantic import BaseModel, Field

from ttd.cli._interactive import interactive_fill
from ttd.cli._output import console, success
from ttd.cli._pickers import project_choices, split_project_choice
from ttd.cli._run import TtdApp, with_db
from ttd.config.loader import get_settings
from ttd.core.errors import TtdError
from ttd.core.money import format_hours
from ttd.parsing.resolve import resolve_point
from ttd.services import timer as svc

AtOpt = Annotated[str | None, Parameter(help="Clock time like '9am' or 'today 8:30'")]
NoteOpt = Annotated[str | None, Parameter(name=["--note", "-n"])]


def _at(raw: str | None, now: datetime) -> datetime | None:
    return resolve_point(raw, now, get_settings().parsing) if raw else None


class StartInput(BaseModel):
    project: str = Field(
        json_schema_extra={"prompt": "Project", "widget": "select", "choices": project_choices}
    )
    at: str | None = Field(None, json_schema_extra={"prompt": "Started at (blank for now)"})
    note: str | None = Field(None, json_schema_extra={"prompt": "Note (optional)"})


def register(app: TtdApp) -> None:
    @app.command(name="start")
    @with_db
    async def start(
        project: Annotated[str | None, Parameter(help="Project slug")] = None,
        *,
        client: str | None = None,
        at: AtOpt = None,
        note: NoteOpt = None,
        interactive: Annotated[
            bool, Parameter(name=["--interactive", "-i"], help="Fill remaining fields via a form")
        ] = False,
    ) -> None:
        """Start a timer (project defaults to [defaults].project from config)."""
        now = datetime.now()
        settings = get_settings()

        if interactive:
            data = await interactive_fill(StartInput, {"project": project, "at": at, "note": note})
            project, picked_client = split_project_choice(data.project)
            client = client or picked_client
            at, note = data.at, data.note

        slug = project or settings.defaults.project
        if slug is None:
            raise TtdError(
                "No project given and no [defaults].project in config — `ttd start PROJECT`"
            )
        timer = await svc.start_timer(
            slug,
            client or settings.defaults.client,
            now=now,
            at=_at(at, now),
            note=note or "",
        )
        success(f"Timer started at [accent]{timer.started_at:%-I:%M%p}[/accent]".lower())

    @app.command(name="stop")
    @with_db
    async def stop(
        *,
        at: AtOpt = None,
        note: NoteOpt = None,
    ) -> None:
        """Stop the running timer and log the entry."""
        now = datetime.now()
        entry = await svc.stop_timer(now=now, at=_at(at, now), note=note)
        success(
            f"Logged [accent]{format_hours(entry.seconds)}[/accent] "
            f"({entry.started_at:%-I:%M%p}–{entry.ended_at:%-I:%M%p})".lower()
        )

    @app.command(name="status")
    @with_db
    async def status() -> None:
        """Show the running timer and today's total."""
        now = datetime.now()
        st = await svc.timer_status(now=now)
        if st.timer is None:
            console.print("[muted]No timer running.[/muted]")
        else:
            where = f"{st.client.slug}/{st.project.slug}" if st.project and st.client else "?"
            console.print(
                f"[accent]▶[/accent] {where} — [bold]{format_hours(st.elapsed_seconds)}[/bold] "
                f"(since {st.timer.started_at:%-I:%M%p})".lower()
                + (f"  [muted]{st.timer.note}[/muted]" if st.timer.note else "")
            )
        console.print(f"Today: [bold]{format_hours(st.today_seconds)}[/bold]")

    @app.command(name="cancel")
    @with_db
    async def cancel() -> None:
        """Discard the running timer without logging."""
        timer = await svc.cancel_timer()
        success(f"Discarded timer started at {timer.started_at:%-I:%M%p}".lower())
