"""DB-backed entity pickers for interactive CLI."""

from __future__ import annotations

from uuid import UUID

from ttd.cli.output import _short_id
from ttd.cli.prompts import ask_confirm, ask_select
from ttd.cli.runtime import require_id
from ttd.core.exceptions import ValidationError
from ttd.core.models.client import Client
from ttd.core.models.project import Project
from ttd.core.models.time_entry import TimeEntry
from ttd.core.services import clients as client_service
from ttd.core.services import projects as project_service
from ttd.core.services import time_entries as entry_service


def _client_label(client: Client) -> str:
    return f"{client.name} ({_short_id(client.id)})"


def _project_label(project: Project) -> str:
    return f"{project.name} ({_short_id(project.id)})"


def _entry_label(entry: TimeEntry, *, project_name: str) -> str:
    hours = entry.billable_hours
    return (
        f"{project_name} · {entry.work_date.isoformat()} · {hours}h "
        f"({_short_id(entry.id)})"
    )


async def pick_client(*, message: str = "Client") -> Client:
    clients = await client_service.list_clients()
    if not clients:
        raise ValidationError("No clients yet. Run: ttd client add")
    return await ask_select(
        message,
        [(_client_label(client), client) for client in clients],
    )


async def pick_project_for_client(
    client_id: UUID, *, message: str = "Project"
) -> Project:
    projects = await project_service.list_projects_for_client(client_id)
    if not projects:
        raise ValidationError("No projects for this client. Run: ttd project add")
    return await ask_select(
        message,
        [(_project_label(project), project) for project in projects],
    )


async def pick_project_any(*, message: str = "Project") -> Project:
    clients = await client_service.list_clients()
    if not clients:
        raise ValidationError("No clients yet. Run: ttd client add")
    choices: list[tuple[str, Project]] = []
    for client in clients:
        projects = await project_service.list_projects_for_client(
            require_id(client.id, "client")
        )
        for project in projects:
            choices.append((f"{client.name} / {_project_label(project)}", project))
    if not choices:
        raise ValidationError("No projects yet. Run: ttd project add")
    return await ask_select(message, choices)


async def pick_entry_for_project(
    project_id: UUID, *, project_name: str, message: str = "Time entry"
) -> TimeEntry:
    entries = await entry_service.list_time_entries_for_project(project_id)
    if not entries:
        raise ValidationError("No time entries for this project.")
    return await ask_select(
        message,
        [(_entry_label(entry, project_name=project_name), entry) for entry in entries],
    )


async def confirm_delete(label: str) -> bool:
    return await ask_confirm(f"Delete {label}? This cannot be undone.", default=False)
