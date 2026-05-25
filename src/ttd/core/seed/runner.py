"""Apply demo seed data through core services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time
from uuid import UUID

from ttd.core.db import init_db
from ttd.core.exceptions import ValidationError
from ttd.core.schemas import (
    CreateClient,
    CreateDurationEntry,
    CreateIntervalEntry,
    CreateProject,
)
from ttd.core.seed.demo_data import (
    DEMO_CLIENT_NAMES,
    DEMO_LEDGER,
    MARKER_CLIENT_NAME,
    DemoClient,
    DemoIntervalEntry,
    DemoProject,
)
from ttd.core.services import clients as client_service
from ttd.core.services import projects as project_service
from ttd.core.services import time_entries as entry_service


@dataclass(frozen=True, slots=True)
class SeedSummary:
    clients: int
    projects: int
    entries: int
    skipped: bool = False


def _require_id(value: UUID | None, label: str) -> UUID:
    if value is None:
        raise ValidationError(f"{label} is missing an id")
    return value


async def is_demo_seeded() -> bool:
    for client in await client_service.list_clients():
        if client.name == MARKER_CLIENT_NAME:
            return True
    return False


async def clear_demo_data() -> None:
    for client in await client_service.list_clients():
        if client.name not in DEMO_CLIENT_NAMES:
            continue
        client_id = _require_id(client.id, "client")
        for project in await project_service.list_projects_for_client(client_id):
            project_id = _require_id(project.id, "project")
            for entry in await entry_service.list_time_entries_for_project(project_id):
                entry_id = _require_id(entry.id, "time entry")
                await entry_service.delete_time_entry(entry_id)
            await project_service.delete_project(project_id)
        await client_service.delete_client(client_id)


def _parse_clock(clock: str) -> time:
    hour, minute = clock.split(":")
    return time(int(hour), int(minute))


def _interval_datetimes(
    entry: DemoIntervalEntry,
) -> tuple[datetime, datetime]:
    started = datetime.combine(entry.work_date, _parse_clock(entry.started), tzinfo=UTC)
    ended = datetime.combine(entry.work_date, _parse_clock(entry.ended), tzinfo=UTC)
    return started, ended


async def _seed_project(client_id: UUID, spec: DemoProject) -> int:
    project = await project_service.create_project(
        CreateProject(
            client_id=client_id,
            name=spec.name,
            billing_mode=spec.billing_mode,
            hourly_rate=spec.hourly_rate,
            currency=spec.currency,
            contract_total=spec.contract_total,
            soft_max_hours=spec.soft_max_hours,
        )
    )
    project_id = _require_id(project.id, "project")
    entry_count = 0
    for duration in spec.duration_entries:
        await entry_service.create_duration_entry(
            CreateDurationEntry(
                project_id=project_id,
                work_date=duration.work_date,
                billable_hours=duration.hours,
                billable=duration.billable,
                note=duration.note,
            )
        )
        entry_count += 1
    for interval in spec.interval_entries:
        started, ended = _interval_datetimes(interval)
        await entry_service.create_interval_entry(
            CreateIntervalEntry(
                project_id=project_id,
                work_date=interval.work_date,
                started_at=started,
                ended_at=ended,
                billable=interval.billable,
                note=interval.note,
            )
        )
        entry_count += 1
    return entry_count


async def _seed_client(spec: DemoClient) -> tuple[int, int]:
    client = await client_service.create_client(
        CreateClient(
            name=spec.name,
            default_hourly_rate=spec.default_hourly_rate,
            currency=spec.currency,
        )
    )
    client_id = _require_id(client.id, "client")
    project_count = 0
    entry_count = 0
    for project_spec in spec.projects:
        project_count += 1
        entry_count += await _seed_project(client_id, project_spec)
    return project_count, entry_count


async def seed_database(*, force: bool = False) -> SeedSummary:
    await init_db()
    if await is_demo_seeded():
        if not force:
            return SeedSummary(clients=0, projects=0, entries=0, skipped=True)
        await clear_demo_data()

    clients = 0
    projects = 0
    entries = 0
    for client_spec in DEMO_LEDGER:
        clients += 1
        project_count, entry_count = await _seed_client(client_spec)
        projects += project_count
        entries += entry_count
    return SeedSummary(clients=clients, projects=projects, entries=entries)
