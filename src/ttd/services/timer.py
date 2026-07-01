"""The running timer. At most one timer at a time; stopping creates an Entry."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from ttd.core.errors import ConflictError, TtdError
from ttd.services.projects import get_project
from ttd.storage.db import in_db_session
from ttd.storage.models import (
    TIMER_SINGLETON_ID,
    Client,
    Entry,
    EntrySource,
    Project,
    TimerState,
    pk,
)


@dataclass
class TimerStatus:
    timer: TimerState | None
    project: Project | None
    client: Client | None
    elapsed_seconds: int
    today_seconds: int


@in_db_session
async def start_timer(
    project_slug: str,
    client_slug: str | None = None,
    *,
    now: datetime,
    at: datetime | None = None,
    note: str = "",
) -> TimerState:
    if (existing := await TimerState.get_or_none(TIMER_SINGLETON_ID)) is not None:
        project = await Project.get_or_none(existing.project_id)
        slug = project.slug if project else "?"
        raise ConflictError(
            f"A timer is already running on '{slug}' (since {existing.started_at:%-I:%M%p}) — "
            "`ttd stop` or `ttd cancel` first"
        )
    started = (at or now).replace(microsecond=0)
    if started > now:
        raise TtdError(f"Can't start a timer in the future ({started:%-I:%M%p})")
    project = await get_project(project_slug, client_slug)
    timer = TimerState(id=TIMER_SINGLETON_ID, project_id=pk(project), started_at=started, note=note)
    await timer.save()
    return timer


@in_db_session
async def stop_timer(
    *,
    now: datetime,
    at: datetime | None = None,
    note: str | None = None,
) -> Entry:
    timer = await TimerState.get_or_none(TIMER_SINGLETON_ID)
    if timer is None:
        raise ConflictError("No timer is running — `ttd start PROJECT` first")
    ended = (at or now).replace(microsecond=0)
    if ended < timer.started_at:
        raise TtdError(
            f"Stop time {ended:%-I:%M%p} is before the timer started ({timer.started_at:%-I:%M%p})"
        )
    if ended == timer.started_at:
        ended += timedelta(seconds=1)  # stopped within the same second; floor at 1s
    stamp = datetime.now()
    entry = Entry(
        id=uuid4(),
        project_id=timer.project_id,
        work_date=timer.started_at.date(),
        started_at=timer.started_at,
        ended_at=ended,
        seconds=int((ended - timer.started_at).total_seconds()),
        note=note if note is not None else timer.note,
        source=EntrySource.TIMER,
        created_at=stamp,
        updated_at=stamp,
    )
    await entry.save()
    await timer.delete()
    return entry


@in_db_session
async def cancel_timer() -> TimerState:
    timer = await TimerState.get_or_none(TIMER_SINGLETON_ID)
    if timer is None:
        raise ConflictError("No timer is running")
    await timer.delete()
    return timer


@in_db_session
async def timer_status(*, now: datetime) -> TimerStatus:
    timer = await TimerState.get_or_none(TIMER_SINGLETON_ID)
    today = now.date()
    today_entries = await Entry.where(lambda e: e.work_date == today).all()
    today_seconds = sum(e.seconds for e in today_entries)
    project = client = None
    elapsed = 0
    if timer is not None:
        project = await Project.get_or_none(timer.project_id)
        if project is not None:
            client = await Client.get_or_none(project.client_id)
        elapsed = max(0, int((now - timer.started_at).total_seconds()))
        today_seconds += elapsed if timer.started_at.date() == today else 0
    return TimerStatus(timer, project, client, elapsed, today_seconds)
