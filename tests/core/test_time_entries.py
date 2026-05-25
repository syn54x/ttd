from datetime import UTC, date, datetime
from decimal import Decimal

from ttd.core.schemas import (
    CreateDurationEntry,
    CreateIntervalEntry,
    UpdateIntervalEntry,
)
from ttd.core.services import projects as project_service
from ttd.core.services import time_entries as entry_service

UTC = UTC


async def test_duration_entry(db, hourly_project) -> None:
    entry = await entry_service.create_duration_entry(
        CreateDurationEntry(
            project_id=hourly_project.id,
            work_date=date(2026, 5, 1),
            billable_hours=Decimal("3"),
            note="feature work",
        )
    )
    assert entry.entry_mode.value == "duration"
    assert entry.billable_hours == Decimal("3")
    assert entry.started_at is None
    assert entry.ended_at is None


async def test_interval_entry_snapshot(db, hourly_project) -> None:
    entry = await entry_service.create_interval_entry(
        CreateIntervalEntry(
            project_id=hourly_project.id,
            work_date=date(2026, 5, 1),
            started_at=datetime(2026, 5, 1, 9, 0, tzinfo=UTC),
            ended_at=datetime(2026, 5, 1, 12, 30, tzinfo=UTC),
        )
    )
    assert entry.billable_hours == Decimal("3.5")


async def test_interval_update_recomputes_hours(db, hourly_project) -> None:
    entry = await entry_service.create_interval_entry(
        CreateIntervalEntry(
            project_id=hourly_project.id,
            work_date=date(2026, 5, 1),
            started_at=datetime(2026, 5, 1, 9, 0, tzinfo=UTC),
            ended_at=datetime(2026, 5, 1, 12, 30, tzinfo=UTC),
        )
    )
    updated = await entry_service.update_interval_entry(
        entry.id,
        UpdateIntervalEntry(
            ended_at=datetime(2026, 5, 1, 13, 0, tzinfo=UTC),
        ),
    )
    assert updated.billable_hours == Decimal("4")


async def test_billable_hours_sum_excludes_non_billable(db, hourly_project) -> None:
    await entry_service.create_duration_entry(
        CreateDurationEntry(
            project_id=hourly_project.id,
            work_date=date(2026, 5, 1),
            billable_hours=Decimal("3"),
            billable=True,
        )
    )
    await entry_service.create_duration_entry(
        CreateDurationEntry(
            project_id=hourly_project.id,
            work_date=date(2026, 5, 1),
            billable_hours=Decimal("2"),
            billable=False,
        )
    )
    total = await project_service.project_billable_hours(hourly_project.id)
    assert total == Decimal("3")


async def test_entry_allowed_when_over_soft_max(db, sample_client) -> None:
    from ttd.core.models.enums import BillingMode
    from ttd.core.schemas import CreateProject

    project = await project_service.create_project(
        CreateProject(
            client_id=sample_client.id,
            name="Capped",
            billing_mode=BillingMode.HOURLY,
            soft_max_hours=Decimal("1"),
        )
    )
    await entry_service.create_duration_entry(
        CreateDurationEntry(
            project_id=project.id,
            work_date=date(2026, 5, 1),
            billable_hours=Decimal("2"),
        )
    )
    status = await project_service.project_soft_max_status(project.id)
    assert status.value == "over"
    await entry_service.create_duration_entry(
        CreateDurationEntry(
            project_id=project.id,
            work_date=date(2026, 5, 2),
            billable_hours=Decimal("1"),
        )
    )
