"""CLI runtime helpers (DB init, parsing)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from ttd.core.db import init_db
from ttd.core.exceptions import NotFoundError, ValidationError
from ttd.core.models.client import Client
from ttd.core.models.project import Project
from ttd.core.services import clients as client_service
from ttd.core.services import projects as project_service
from ttd.core.time import parse_clock_on_work_date
from ttd.core.time import parse_work_date as parse_work_date_nl


def require_id(value: UUID | None, label: str) -> UUID:
    if value is None:
        raise ValidationError(f"{label} is missing an id")
    return value


async def ensure_db() -> None:
    """Initialize the ledger database for this CLI invocation."""
    await init_db()


def parse_date(value: str) -> date:
    return parse_work_date_nl(value)


def parse_decimal(value: str) -> Decimal:
    try:
        return Decimal(value)
    except Exception as exc:
        raise ValidationError(f"Invalid decimal '{value}'") from exc


def parse_clock_on_date(work_date: date, clock: str) -> datetime:
    """Parse HH:MM or natural language clock text on work_date (stored as UTC)."""
    return parse_clock_on_work_date(work_date, clock)


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
