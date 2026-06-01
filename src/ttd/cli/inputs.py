"""Typed CLI command inputs and value narrowing at the adapter boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from ttd.core.exceptions import ValidationError


def require_uuid(value: UUID | None, label: str = "id") -> UUID:
    if value is None:
        raise ValidationError(f"{label} is required")
    return value


def optional_str(value: str | None) -> str | None:
    return value


def parse_optional_uuid(value: str | UUID | None) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def billable_flag(
    *,
    non_billable: bool | None = None,
    billable: bool | None = None,
) -> bool | None:
    if non_billable is True and billable is not None:
        raise ValidationError("Use only one of --billable or --no-billable")
    if non_billable is True:
        return False
    if billable is not None:
        return bool(billable)
    return None


def missing_keys(provided: Mapping[str, Any], required: tuple[str, ...]) -> list[str]:
    return [key for key in required if provided.get(key) is None]


@dataclass(slots=True)
class ClientAddInput:
    name: str | None = None
    rate: str | None = None
    currency: str | None = None

    def as_provided(self) -> dict[str, Any]:
        return {"name": self.name, "rate": self.rate, "currency": self.currency}


@dataclass(slots=True)
class ClientUpdateInput:
    client_id: UUID | None = None
    name: str | None = None
    rate: str | None = None
    currency: str | None = None

    def as_provided(self) -> dict[str, Any]:
        return {
            "client_id": self.client_id,
            "name": self.name,
            "rate": self.rate,
            "currency": self.currency,
        }

    def require_client_id(self) -> UUID:
        return require_uuid(self.client_id, "client")


@dataclass(slots=True)
class ClientDeleteInput:
    client_id: UUID | None = None
    cancelled: bool = False

    def as_provided(self) -> dict[str, Any]:
        return {"client_id": self.client_id}


@dataclass(slots=True)
class ProjectAddInput:
    name: str | None = None
    client: str | None = None  # client name
    billing_mode: str | None = None
    rate: str | None = None
    currency: str | None = None
    contract_total: str | None = None
    soft_max_hours: str | None = None

    def as_provided(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "client": self.client,
            "billing_mode": self.billing_mode,
            "rate": self.rate,
            "currency": self.currency,
            "contract_total": self.contract_total,
            "soft_max_hours": self.soft_max_hours,
        }


@dataclass(slots=True)
class ProjectUpdateInput:
    project_id: UUID | None = None
    name: str | None = None
    rate: str | None = None
    currency: str | None = None
    contract_total: str | None = None
    soft_max_hours: str | None = None
    clear_rate_override: bool = False

    def as_provided(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "rate": self.rate,
            "currency": self.currency,
            "contract_total": self.contract_total,
            "soft_max_hours": self.soft_max_hours,
            "clear_rate_override": self.clear_rate_override,
        }

    def require_project_id(self) -> UUID:
        return require_uuid(self.project_id, "project")


@dataclass(slots=True)
class ProjectDeleteInput:
    project_id: UUID | None = None
    cancelled: bool = False

    def as_provided(self) -> dict[str, Any]:
        return {"project_id": self.project_id}


@dataclass(slots=True)
class LogEntryInput:
    client: str | None = None
    project: str | None = None
    project_id: UUID | None = None
    work_date: str | None = None
    when: str | None = None
    hours: str | None = None
    time_from: str | None = None
    time_to: str | None = None
    note: str | None = None
    non_billable: bool | None = None

    def as_provided(self) -> dict[str, Any]:
        return {
            "client": self.client,
            "project": self.project,
            "project_id": self.project_id,
            "work_date": self.work_date,
            "when": self.when,
            "hours": self.hours,
            "time_from": self.time_from,
            "time_to": self.time_to,
            "note": self.note,
            "non_billable": self.non_billable,
        }

    def required_for_run(self) -> tuple[str, ...]:
        if self.project_id is not None:
            base: tuple[str, ...] = ("project_id",)
        else:
            base = ("client", "project")
        if self.hours is not None:
            return base
        if self.when is not None:
            return base
        if self.time_from is not None and self.time_to is not None:
            return base
        return (*base, "hours")


@dataclass(slots=True)
class EntryEditInput:
    entry_id: UUID | None = None
    work_date: str | None = None
    hours: str | None = None
    time_from: str | None = None
    time_to: str | None = None
    note: str | None = None
    non_billable: bool | None = None
    billable: bool | None = None

    def as_provided(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "work_date": self.work_date,
            "hours": self.hours,
            "time_from": self.time_from,
            "time_to": self.time_to,
            "note": self.note,
            "non_billable": self.non_billable,
            "billable": self.billable,
        }

    def require_entry_id(self) -> UUID:
        return require_uuid(self.entry_id, "entry")


@dataclass(slots=True)
class EntryDeleteInput:
    entry_id: UUID | None = None
    cancelled: bool = False

    def as_provided(self) -> dict[str, Any]:
        return {"entry_id": self.entry_id}


@dataclass(slots=True)
class ConfigInitInput:
    data_dir: str
    db_filename: str
    clock_format: Literal["12h", "24h"]
    create_data_dir: bool = True
    run_migrate: bool = False
