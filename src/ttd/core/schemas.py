"""Pydantic DTOs for core service boundaries."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ttd.core.models.enums import BillingMode


class CreateClient(BaseModel):
    model_config = ConfigDict(use_attribute_docstrings=True)

    name: str
    default_hourly_rate: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)


class UpdateClient(BaseModel):
    model_config = ConfigDict(use_attribute_docstrings=True)

    name: str | None = None
    default_hourly_rate: Decimal | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class CreateProject(BaseModel):
    model_config = ConfigDict(use_attribute_docstrings=True)

    client_id: UUID
    name: str
    billing_mode: BillingMode
    hourly_rate: Decimal | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    contract_total: Decimal | None = Field(default=None, gt=0)
    soft_max_hours: Decimal | None = Field(default=None, gt=0)


class UpdateProject(BaseModel):
    model_config = ConfigDict(use_attribute_docstrings=True)

    name: str | None = None
    hourly_rate: Decimal | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    contract_total: Decimal | None = Field(default=None, gt=0)
    soft_max_hours: Decimal | None = None
    clear_rate_override: bool = False


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
