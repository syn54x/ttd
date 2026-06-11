"""Choice providers and validators for interactive forms."""

from datetime import datetime

from ttd.core.errors import ParseError, TtdError
from ttd.core.money import format_hours, parse_money
from ttd.parsing.resolve import resolve_entry
from ttd.services.clients import list_clients
from ttd.services.projects import list_projects
from ttd.storage.models import Client


async def client_choices() -> list[str]:
    return [c.slug for c in await list_clients()]


async def project_choices() -> list[str]:
    """All projects as 'client-slug/project-slug'."""
    projects = await list_projects()
    clients = {c.id: c.slug for c in await Client.all()}
    return [f"{clients.get(p.client_id, '?')}/{p.slug}" for p in projects]


def split_project_choice(choice: str) -> tuple[str, str | None]:
    """'client/project' → (project, client); bare slug passes through."""
    if "/" in choice:
        client, project = choice.split("/", 1)
        return project, client
    return choice, None


def validate_timespec(text: str) -> bool | str:
    if not text.strip():
        return "Enter a time, e.g. 'today 9am to 5pm' or '2h'"
    try:
        resolved = resolve_entry(text, datetime.now())
    except ParseError as exc:
        return str(exc)
    when = (
        f"{resolved.started_at:%a %b %-d, %-I:%M%p}–{resolved.ended_at:%-I:%M%p}".lower()
        if resolved.started_at and resolved.ended_at
        else f"{resolved.work_date:%a %b %-d}"
    )
    del when  # questionary validators return True; the echo happens after the form
    return True


def describe_timespec(text: str) -> str:
    resolved = resolve_entry(text, datetime.now())
    if resolved.started_at and resolved.ended_at:
        return (
            f"{resolved.work_date:%a %b %-d} "
            f"{resolved.started_at:%-I:%M%p}–{resolved.ended_at:%-I:%M%p} "
            f"({format_hours(resolved.seconds)})"
        ).lower()
    return f"{resolved.work_date:%a %b %-d} — {format_hours(resolved.seconds)} (no clock times)"


def validate_money(text: str) -> bool | str:
    if not text.strip():
        return True  # optional
    try:
        parse_money(text)
    except TtdError as exc:
        return str(exc)
    return True
