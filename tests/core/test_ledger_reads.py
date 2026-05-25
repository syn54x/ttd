from datetime import date
from decimal import Decimal

from ttd.core.domain.aggregates import SoftMaxStatus
from ttd.core.schemas import CreateDurationEntry
from ttd.core.services import projects as project_service
from ttd.core.services import time_entries as entry_service


async def test_implied_rate_fixed_price(fixed_price_project) -> None:
    for _ in range(4):
        await entry_service.create_duration_entry(
            CreateDurationEntry(
                project_id=fixed_price_project.id,
                work_date=date(2026, 5, 1),
                billable_hours=Decimal("10"),
            )
        )
    implied = await project_service.resolve_implied_rate(fixed_price_project.id)
    assert implied is not None
    assert implied.amount == Decimal("250")
    assert implied.currency == "USD"


async def test_implied_rate_zero_hours(fixed_price_project) -> None:
    assert await project_service.resolve_implied_rate(fixed_price_project.id) is None


async def test_fixed_price_billable_hours_only(fixed_price_project) -> None:
    await entry_service.create_duration_entry(
        CreateDurationEntry(
            project_id=fixed_price_project.id,
            work_date=date(2026, 5, 1),
            billable_hours=Decimal("5"),
        )
    )
    hours = await project_service.project_billable_hours(fixed_price_project.id)
    assert hours == Decimal("5")


async def test_soft_max_unset(hourly_project) -> None:
    status = await project_service.project_soft_max_status(hourly_project.id)
    assert status == SoftMaxStatus.UNSET
