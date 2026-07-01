"""Logging and managing time entries."""

from dataclasses import dataclass
from datetime import date, datetime
from uuid import uuid4

from ttd.config.schema import Settings
from ttd.core.errors import ConflictError, InvoicedEntryError, NotFoundError, TtdError
from ttd.parsing.resolve import ResolvedSpan, resolve_entry
from ttd.services.projects import get_project
from ttd.storage.db import in_db_session
from ttd.storage.models import Client, Entry, EntrySource, Project, pk


class OverlapError(ConflictError):
    """New interval overlaps existing entries; retry with force to log anyway."""

    def __init__(self, message: str, overlapping: list[Entry]) -> None:
        super().__init__(message)
        self.overlapping = overlapping


@dataclass
class EntryRow:
    entry: Entry
    project: Project
    client: Client


def resolve_project_slugs(
    settings: Settings, project: str | None, client: str | None
) -> tuple[str, str | None]:
    project = project or settings.defaults.project
    client = client or settings.defaults.client
    if project is None:
        raise TtdError("No project given and no [defaults].project in config — pass --project")
    return project, client


async def _overlapping(resolved: ResolvedSpan) -> list[Entry]:
    """Interval clashes on the same day, across all projects (you only have one body)."""
    if resolved.started_at is None or resolved.ended_at is None:
        return []
    same_day = await Entry.where(lambda e: e.work_date == resolved.work_date).all()
    out = []
    for other in same_day:
        if other.started_at is None or other.ended_at is None:
            continue
        if other.started_at < resolved.ended_at and resolved.started_at < other.ended_at:
            out.append(other)
    return out


@in_db_session
async def log_entry(
    spec: str,
    project_slug: str,
    client_slug: str | None = None,
    *,
    now: datetime,
    note: str = "",
    tags: str = "",
    billable: bool = True,
    source: EntrySource = EntrySource.LOG,
    settings: Settings | None = None,
    force: bool = False,
) -> Entry:
    settings = settings or Settings()
    project = await get_project(project_slug, client_slug)
    resolved = resolve_entry(spec, now, settings.parsing)

    if not force and (clashes := await _overlapping(resolved)):
        times = ", ".join(f"{c.started_at:%-I:%M%p}–{c.ended_at:%-I:%M%p}".lower() for c in clashes)
        raise OverlapError(
            f"Overlaps {len(clashes)} existing entr{'y' if len(clashes) == 1 else 'ies'} "
            f"on {resolved.work_date:%a %b %-d} ({times})",
            clashes,
        )

    stamp = datetime.now()
    entry = Entry(
        id=uuid4(),
        project_id=pk(project),
        work_date=resolved.work_date,
        started_at=resolved.started_at,
        ended_at=resolved.ended_at,
        seconds=resolved.seconds,
        note=note,
        tags=tags,
        billable=billable,
        source=source,
        created_at=stamp,
        updated_at=stamp,
    )
    await entry.save()
    return entry


@in_db_session
async def find_entry(uid_prefix: str) -> Entry:
    """Look up an entry by full UUID or unambiguous hex prefix."""
    needle = uid_prefix.lower().replace("-", "")
    if not needle:
        raise NotFoundError("Empty entry id")
    matches = [e for e in await Entry.all() if str(e.id).replace("-", "").startswith(needle)]
    if not matches:
        raise NotFoundError(f"No entry matching '{uid_prefix}'")
    if len(matches) > 1:
        raise ConflictError(f"'{uid_prefix}' matches {len(matches)} entries — use more characters")
    return matches[0]


@in_db_session
async def list_entries(
    *,
    project_slug: str | None = None,
    client_slug: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[EntryRow]:
    entries = await Entry.all()
    projects = {p.id: p for p in await Project.all()}
    clients = {c.id: c for c in await Client.all()}

    if project_slug is not None:
        project = await get_project(project_slug, client_slug)
        entries = [e for e in entries if e.project_id == project.id]
    elif client_slug is not None:
        wanted = {p.id for p in projects.values() if clients[p.client_id].slug == client_slug}
        entries = [e for e in entries if e.project_id in wanted]
    if date_from is not None:
        entries = [e for e in entries if e.work_date >= date_from]
    if date_to is not None:
        entries = [e for e in entries if e.work_date <= date_to]

    rows = []
    earliest = datetime(1, 1, 1)  # duration-only entries sort first within a day
    for e in sorted(entries, key=lambda e: (e.work_date, e.started_at or earliest)):
        project = projects.get(e.project_id)
        if project is None:
            continue
        rows.append(EntryRow(e, project, clients[project.client_id]))
    return rows


def _ensure_unlocked(entry: Entry) -> None:
    if entry.invoice_id is not None:
        raise InvoicedEntryError(
            f"Entry {str(entry.id)[:8]} is on an invoice — void the invoice first"
        )


@in_db_session
async def edit_entry(
    uid_prefix: str,
    *,
    now: datetime,
    spec: str | None = None,
    note: str | None = None,
    tags: str | None = None,
    billable: bool | None = None,
    project_slug: str | None = None,
    client_slug: str | None = None,
    settings: Settings | None = None,
) -> Entry:
    settings = settings or Settings()
    entry = await find_entry(uid_prefix)
    _ensure_unlocked(entry)
    if spec is not None:
        resolved = resolve_entry(spec, now, settings.parsing)
        entry.work_date = resolved.work_date
        entry.started_at = resolved.started_at
        entry.ended_at = resolved.ended_at
        entry.seconds = resolved.seconds
    if note is not None:
        entry.note = note
    if tags is not None:
        entry.tags = tags
    if billable is not None:
        entry.billable = billable
    if project_slug is not None:
        project = await get_project(project_slug, client_slug)
        entry.project_id = pk(project)
    entry.updated_at = datetime.now()
    await entry.save()
    return entry


@in_db_session
async def delete_entry(uid_prefix: str) -> Entry:
    entry = await find_entry(uid_prefix)
    _ensure_unlocked(entry)
    await entry.delete()
    return entry
