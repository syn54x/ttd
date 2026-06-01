"""Pydantic DTOs for core service boundaries."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ttd.core.models.enums import BillingMode


class CreateClient(BaseModel):
    model_config = ConfigDict(use_attribute_docstrings=True)

    name: str
    default_hourly_rate: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    rounding_increment_minutes: int | None = Field(default=None, gt=0)


class UpdateClient(BaseModel):
    model_config = ConfigDict(use_attribute_docstrings=True)

    name: str | None = None
    default_hourly_rate: Decimal | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    rounding_increment_minutes: int | None = Field(default=None, gt=0)
    clear_rounding_increment: bool = False


class CreateProject(BaseModel):
    model_config = ConfigDict(use_attribute_docstrings=True)

    client_id: UUID
    name: str
    billing_mode: BillingMode
    hourly_rate: Decimal | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    contract_total: Decimal | None = Field(default=None, gt=0)
    soft_max_hours: Decimal | None = Field(default=None, gt=0)
    rounding_increment_minutes: int | None = Field(default=None, gt=0)


class UpdateProject(BaseModel):
    model_config = ConfigDict(use_attribute_docstrings=True)

    name: str | None = None
    hourly_rate: Decimal | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    contract_total: Decimal | None = Field(default=None, gt=0)
    soft_max_hours: Decimal | None = None
    clear_rate_override: bool = False
    rounding_increment_minutes: int | None = Field(default=None, gt=0)
    clear_rounding_increment: bool = False


class ExportPeriod(BaseModel):
    model_config = ConfigDict(use_attribute_docstrings=True)

    from_date: date
    """Inclusive period start (work date)."""

    to_date: date
    """Inclusive period end (work date)."""

    @model_validator(mode="after")
    def check_date_order(self) -> ExportPeriod:
        if self.from_date > self.to_date:
            msg = "from_date must be on or before to_date"
            raise ValueError(msg)
        return self


class CreateDurationEntry(BaseModel):
    model_config = ConfigDict(use_attribute_docstrings=True)

    project_id: UUID
    work_date: date
    billable_hours: Decimal = Field(gt=0)
    billable: bool = True
    note: str | None = None


class CreateIntervalEntry(BaseModel):
    model_config = ConfigDict(use_attribute_docstrings=True)

    project_id: UUID
    work_date: date
    started_at: datetime
    ended_at: datetime
    billable: bool = True
    note: str | None = None


class UpdateDurationEntry(BaseModel):
    model_config = ConfigDict(use_attribute_docstrings=True)

    work_date: date | None = None
    billable_hours: Decimal | None = Field(default=None, gt=0)
    billable: bool | None = None
    note: str | None = None


class UpdateIntervalEntry(BaseModel):
    model_config = ConfigDict(use_attribute_docstrings=True)

    work_date: date | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    billable: bool | None = None
    note: str | None = None
