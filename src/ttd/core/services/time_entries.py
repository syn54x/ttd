"""Time entry CRUD services."""

from __future__ import annotations

from uuid import UUID, uuid4

from ferro.exceptions import ModelDoesNotExist

from ttd.core.domain.hours import duration_from_interval, recompute_interval_snapshot
from ttd.core.exceptions import NotFoundError, ValidationError
from ttd.core.models.enums import EntryMode
from ttd.core.models.time_entry import TimeEntry
from ttd.core.schemas import (
    CreateDurationEntry,
    CreateIntervalEntry,
    UpdateDurationEntry,
    UpdateIntervalEntry,
)
from ttd.core.services import projects as project_service


def _reject_interval_fields_on_duration(entry: TimeEntry) -> None:
    if entry.started_at is not None or entry.ended_at is not None:
        raise ValidationError(
            "duration entries must not include started_at or ended_at"
        )


def _require_interval_fields(entry: TimeEntry) -> None:
    if entry.started_at is None or entry.ended_at is None:
        raise ValidationError("interval entries require started_at and ended_at")


async def create_duration_entry(data: CreateDurationEntry) -> TimeEntry:
    await project_service.get_project(data.project_id)
    entry = TimeEntry(
        id=uuid4(),
        project_id=data.project_id,
        work_date=data.work_date,
        entry_mode=EntryMode.DURATION,
        billable_hours=data.billable_hours,
        started_at=None,
        ended_at=None,
        billable=data.billable,
        note=data.note,
    )
    _reject_interval_fields_on_duration(entry)
    await entry.save()
    return entry


async def create_interval_entry(data: CreateIntervalEntry) -> TimeEntry:
    await project_service.get_project(data.project_id)
    hours = duration_from_interval(data.started_at, data.ended_at)
    entry = TimeEntry(
        id=uuid4(),
        project_id=data.project_id,
        work_date=data.work_date,
        entry_mode=EntryMode.INTERVAL,
        billable_hours=hours,
        started_at=data.started_at,
        ended_at=data.ended_at,
        billable=data.billable,
        note=data.note,
    )
    _require_interval_fields(entry)
    await entry.save()
    return entry


async def get_time_entry(entry_id: UUID) -> TimeEntry:
    entry = await TimeEntry.get_or_none(entry_id)
    if entry is None:
        raise NotFoundError(f"Time entry {entry_id} not found")
    return entry


async def list_time_entries_for_project(project_id: UUID) -> list[TimeEntry]:
    await project_service.get_project(project_id)
    return await TimeEntry.where(lambda e: e.project_id == project_id).all()


async def update_duration_entry(entry_id: UUID, data: UpdateDurationEntry) -> TimeEntry:
    entry = await get_time_entry(entry_id)
    if entry.entry_mode != EntryMode.DURATION:
        raise ValidationError("entry is not duration mode")
    if data.work_date is not None:
        entry.work_date = data.work_date
    if data.billable_hours is not None:
        entry.billable_hours = data.billable_hours
    if data.billable is not None:
        entry.billable = data.billable
    if data.note is not None:
        entry.note = data.note
    _reject_interval_fields_on_duration(entry)
    await entry.save()
    return entry


async def update_interval_entry(entry_id: UUID, data: UpdateIntervalEntry) -> TimeEntry:
    entry = await get_time_entry(entry_id)
    if entry.entry_mode != EntryMode.INTERVAL:
        raise ValidationError("entry is not interval mode")
    if data.work_date is not None:
        entry.work_date = data.work_date
    if data.started_at is not None:
        entry.started_at = data.started_at
    if data.ended_at is not None:
        entry.ended_at = data.ended_at
    if data.billable is not None:
        entry.billable = data.billable
    if data.note is not None:
        entry.note = data.note
    _require_interval_fields(entry)
    assert entry.started_at is not None and entry.ended_at is not None
    entry.billable_hours = recompute_interval_snapshot(
        entry.started_at, entry.ended_at
    )
    await entry.save()
    return entry


async def delete_time_entry(entry_id: UUID) -> None:
    entry = await get_time_entry(entry_id)
    try:
        await entry.delete()
    except ModelDoesNotExist:
        raise NotFoundError(f"Time entry {entry_id} not found") from None
