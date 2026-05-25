"""Enum hydration after DB round-trip (ferro-orm >= 0.10.5)."""

from decimal import Decimal

from ferro import reset_engine

from ttd.core.db import close_db, init_db
from ttd.core.models.enums import BillingMode, EntryMode, enum_value
from ttd.core.models.project import Project
from ttd.core.schemas import CreateDurationEntry, CreateProject
from ttd.core.services import projects as project_service
from ttd.core.services import time_entries as entry_service


async def test_project_reload_enum_compare_and_enum_value(db, sample_client) -> None:
    created = await project_service.create_project(
        CreateProject(
            client_id=sample_client.id,
            name="Roundtrip",
            billing_mode=BillingMode.HOURLY,
        )
    )
    loaded = await Project.get_or_none(created.id)
    assert loaded is not None
    assert isinstance(loaded.billing_mode, BillingMode)
    assert loaded.billing_mode == BillingMode.HOURLY
    assert enum_value(loaded.billing_mode) == "hourly"


async def test_project_cold_load_hydrates_billing_mode_enum(db, sample_client) -> None:
    created = await project_service.create_project(
        CreateProject(
            client_id=sample_client.id,
            name="Cold",
            billing_mode=BillingMode.HOURLY,
        )
    )
    assert created.id is not None
    project_id = created.id
    await close_db()
    reset_engine()
    Project._reregister_ferro()
    await init_db(db)
    loaded = await Project.where(lambda p: p.id == project_id).first()
    assert loaded is not None
    assert type(loaded.billing_mode) is not str
    assert isinstance(loaded.billing_mode, BillingMode)


async def test_entry_reload_enum_value(db, hourly_project) -> None:
    created = await entry_service.create_duration_entry(
        CreateDurationEntry(
            project_id=hourly_project.id,
            work_date="2026-05-01",
            billable_hours=Decimal("1"),
        )
    )
    loaded = await entry_service.get_time_entry(created.id)
    assert loaded.entry_mode == EntryMode.DURATION
    assert enum_value(loaded.entry_mode) == "duration"
