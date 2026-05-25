from decimal import Decimal

import pytest

from ttd.core.exceptions import ValidationError
from ttd.core.models.enums import BillingMode
from ttd.core.schemas import CreateProject
from ttd.core.services import projects as project_service


async def test_hourly_project_inherits_rate(db, sample_client) -> None:
    project = await project_service.create_project(
        CreateProject(
            client_id=sample_client.id,
            name="Inherited",
            billing_mode=BillingMode.HOURLY,
        )
    )
    rate, currency = await project_service.resolve_effective_rate(project.id)
    assert rate == Decimal("150")
    assert currency == "USD"


async def test_hourly_project_rate_override(db, sample_client) -> None:
    project = await project_service.create_project(
        CreateProject(
            client_id=sample_client.id,
            name="Override",
            billing_mode=BillingMode.HOURLY,
            hourly_rate=Decimal("175"),
            currency="CAD",
        )
    )
    rate, currency = await project_service.resolve_effective_rate(project.id)
    assert rate == Decimal("175")
    assert currency == "CAD"


async def test_fixed_price_project_requires_contract(db, sample_client) -> None:
    with pytest.raises(ValidationError, match="contract_total"):
        await project_service.create_project(
            CreateProject(
                client_id=sample_client.id,
                name="Bad",
                billing_mode=BillingMode.FIXED_PRICE,
                currency="USD",
            )
        )


async def test_fixed_price_project_create(db, sample_client) -> None:
    project = await project_service.create_project(
        CreateProject(
            client_id=sample_client.id,
            name="Fixed",
            billing_mode=BillingMode.FIXED_PRICE,
            contract_total=Decimal("5000"),
            currency="USD",
        )
    )
    assert project.contract_total == Decimal("5000")
    assert project.hourly_rate is None


async def test_partial_hourly_override_rejected(db, sample_client) -> None:
    with pytest.raises(ValidationError, match="both be set"):
        await project_service.create_project(
            CreateProject(
                client_id=sample_client.id,
                name="Partial",
                billing_mode=BillingMode.HOURLY,
                hourly_rate=Decimal("200"),
            )
        )


async def test_delete_project_with_entries_fails(db, hourly_project) -> None:
    from ttd.core.schemas import CreateDurationEntry
    from ttd.core.services import time_entries as entry_service

    await entry_service.create_duration_entry(
        CreateDurationEntry(
            project_id=hourly_project.id,
            work_date="2026-05-01",
            billable_hours=Decimal("1"),
        )
    )
    with pytest.raises(ValidationError, match="entries"):
        await project_service.delete_project(hourly_project.id)
