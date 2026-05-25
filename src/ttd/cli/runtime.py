"""CLI runtime helpers (DB init, parsing)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal
from uuid import UUID

from ttd.core.db import init_db
from ttd.core.exceptions import NotFoundError, ValidationError
from ttd.core.models.client import Client
from ttd.core.models.project import Project
from ttd.core.services import clients as client_service
from ttd.core.services import projects as project_service


def require_id(value: UUID | None, label: str) -> UUID:
    if value is None:
        raise ValidationError(f"{label} is missing an id")
    return value

async def ensure_db() -> None:
    """Initialize the ledger database for this CLI invocation."""
    await init_db()


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(f"Invalid date '{value}'; use YYYY-MM-DD") from exc


def parse_decimal(value: str) -> Decimal:
    try:
        return Decimal(value)
    except Exception as exc:
        raise ValidationError(f"Invalid decimal '{value}'") from exc


def parse_clock_on_date(work_date: date, clock: str) -> datetime:
    """Parse HH:MM or HH:MM:SS on work_date as UTC."""
    parts = clock.split(":")
    if len(parts) not in (2, 3):
        raise ValidationError(f"Invalid time '{clock}'; use HH:MM or HH:MM:SS")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
        second = int(parts[2]) if len(parts) == 3 else 0
        parsed_time = time(hour, minute, second)
    except ValueError as exc:
        raise ValidationError(f"Invalid time '{clock}'") from exc
    return datetime.combine(work_date, parsed_time, tzinfo=UTC)


async def resolve_client(*, client_id: UUID | None, client_name: str | None) -> Client:
    if client_id is not None:
        return await client_service.get_client(client_id)
    if client_name is not None:
        all_clients = await client_service.list_clients()
        matches = [c for c in all_clients if c.name == client_name]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise NotFoundError(f"No client named '{client_name}'")
        raise ValidationError(f"Multiple clients named '{client_name}'")
    raise ValidationError("Provide --client-id or --client")


async def resolve_project(
    *,
    project_id: UUID | None,
    client: Client | None = None,
    project_name: str | None = None,
) -> Project:
    if project_id is not None:
        return await project_service.get_project(project_id)
    if client is not None and project_name is not None:
        matches = [
            p
            for p in await project_service.list_projects_for_client(
                require_id(client.id, "client")
            )
            if p.name == project_name
        ]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise NotFoundError(
                f"No project '{project_name}' for client '{client.name}'"
            )
        raise ValidationError(
            f"Multiple projects named '{project_name}' for client '{client.name}'"
        )
    raise ValidationError("Provide --project-id or --client with --project")
