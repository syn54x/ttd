"""Project CRUD and rate read helpers."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

from ferro.exceptions import ModelDoesNotExist

from ttd.core.domain.aggregates import (
    SoftMaxStatus,
    soft_max_status,
    sum_billable_hours,
)
from ttd.core.domain.rates import (
    ImpliedRate,
    effective_hourly_rate,
    implied_hourly_rate,
)
from ttd.core.exceptions import NotFoundError, ValidationError
from ttd.core.models.enums import BillingMode
from ttd.core.models.project import Project
from ttd.core.models.time_entry import TimeEntry
from ttd.core.schemas import CreateProject, UpdateProject
from ttd.core.services import clients as client_service


def _validate_rounding_minutes(value: int | None) -> None:
    if value is not None and value <= 0:
        raise ValidationError("rounding_increment_minutes must be a positive integer")


def _validate_hourly_override(
    hourly_rate: Decimal | None, currency: str | None
) -> None:
    has_rate = hourly_rate is not None
    has_currency = currency is not None
    if has_rate != has_currency:
        raise ValidationError(
            "hourly_rate and currency must both be set or both cleared "
            "on hourly projects"
        )


def _apply_create_fields(project: Project, data: CreateProject) -> None:
    if data.billing_mode == BillingMode.HOURLY:
        if data.contract_total is not None:
            raise ValidationError("contract_total is not allowed on hourly projects")
        _validate_hourly_override(data.hourly_rate, data.currency)
        project.hourly_rate = data.hourly_rate
        project.currency = data.currency.upper() if data.currency else None
        project.contract_total = None
    else:
        if data.contract_total is None:
            raise ValidationError("contract_total is required for fixed-price projects")
        if data.currency is None:
            raise ValidationError("currency is required for fixed-price projects")
        if data.hourly_rate is not None:
            raise ValidationError("hourly_rate is not allowed on fixed-price projects")
        project.contract_total = data.contract_total
        project.currency = data.currency.upper()
        project.hourly_rate = None
    project.soft_max_hours = data.soft_max_hours
    _validate_rounding_minutes(data.rounding_increment_minutes)
    project.rounding_increment_minutes = data.rounding_increment_minutes


async def create_project(data: CreateProject) -> Project:
    await client_service.get_client(data.client_id)
    project = Project(
        id=uuid4(),
        client_id=data.client_id,
        name=data.name.strip(),
        billing_mode=data.billing_mode,
    )
    _apply_create_fields(project, data)
    await project.save()
    return project


async def get_project(project_id: UUID) -> Project:
    project = await Project.get_or_none(project_id)
    if project is None:
        raise NotFoundError(f"Project {project_id} not found")
    return project


async def list_projects_for_client(client_id: UUID) -> list[Project]:
    await client_service.get_client(client_id)
    return await Project.where(lambda p: p.client_id == client_id).all()


async def update_project(project_id: UUID, data: UpdateProject) -> Project:
    project = await get_project(project_id)
    if data.name is not None:
        project.name = data.name.strip()
    if data.soft_max_hours is not None:
        project.soft_max_hours = data.soft_max_hours

    if project.billing_mode == BillingMode.HOURLY:
        if data.contract_total is not None:
            raise ValidationError("contract_total is not allowed on hourly projects")
        if data.clear_rate_override:
            project.hourly_rate = None
            project.currency = None
        else:
            rate = (
                data.hourly_rate
                if data.hourly_rate is not None
                else project.hourly_rate
            )
            currency = (
                data.currency.upper() if data.currency is not None else project.currency
            )
            if data.hourly_rate is not None or data.currency is not None:
                _validate_hourly_override(rate, currency)
                project.hourly_rate = rate
                project.currency = currency
    else:
        if (
            data.hourly_rate is not None
            or data.currency is not None
            or data.clear_rate_override
        ):
            raise ValidationError(
                "hourly overrides are not allowed on fixed-price projects"
            )
        if data.contract_total is not None:
            project.contract_total = data.contract_total
        if data.currency is not None:
            project.currency = data.currency.upper()

    if data.clear_rounding_increment:
        project.rounding_increment_minutes = None
    elif data.rounding_increment_minutes is not None:
        _validate_rounding_minutes(data.rounding_increment_minutes)
        project.rounding_increment_minutes = data.rounding_increment_minutes

    await project.save()
    return project


async def delete_project(project_id: UUID) -> None:
    project = await get_project(project_id)
    entries = await TimeEntry.where(lambda e: e.project_id == project.id).all()
    if entries:
        raise ValidationError("Cannot delete project with existing time entries")
    try:
        await project.delete()
    except ModelDoesNotExist:
        raise NotFoundError(f"Project {project_id} not found") from None


async def resolve_effective_rate(project_id: UUID) -> tuple[Decimal, str]:
    project = await get_project(project_id)
    client = await client_service.get_client(project.client_id)
    return effective_hourly_rate(client, project)


async def resolve_implied_rate(project_id: UUID) -> ImpliedRate | None:
    project = await get_project(project_id)
    if project.billing_mode != BillingMode.FIXED_PRICE:
        raise ValidationError(
            "implied hourly rate applies only to fixed-price projects"
        )
    if project.contract_total is None or project.currency is None:
        raise ValidationError(
            "fixed-price project is missing contract_total or currency"
        )
    entries = await TimeEntry.where(lambda e: e.project_id == project.id).all()
    hours = sum_billable_hours(entries)
    return implied_hourly_rate(project.contract_total, project.currency, hours)


async def project_billable_hours(project_id: UUID) -> Decimal:
    project = await get_project(project_id)
    entries = await TimeEntry.where(lambda e: e.project_id == project.id).all()
    return sum_billable_hours(entries)


async def project_soft_max_status(project_id: UUID) -> SoftMaxStatus:
    project = await get_project(project_id)
    total = await project_billable_hours(project_id)
    return soft_max_status(total, project.soft_max_hours)
