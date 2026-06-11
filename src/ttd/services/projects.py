"""Project CRUD. Rates inherit client → business default at billing time."""

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from ttd.core.errors import ConflictError, NotFoundError
from ttd.core.slugs import slugify
from ttd.services.clients import get_client
from ttd.storage.models import Client, Entry, Project, pk


async def create_project(
    name: str,
    client_slug: str,
    *,
    slug: str | None = None,
    hourly_rate: Decimal | None = None,
) -> Project:
    client = await get_client(client_slug)
    assert client.id is not None  # persisted rows always carry an id
    name = name.strip()
    slug = slug or slugify(name)
    clash = await Project.where(lambda p: (p.client_id == client.id) & (p.slug == slug)).exists()
    if clash:
        raise ConflictError(f"Client '{client_slug}' already has a project '{slug}'")
    now = datetime.now()
    project = Project(
        id=uuid4(),
        client_id=client.id,
        name=name,
        slug=slug,
        hourly_rate=hourly_rate,
        created_at=now,
        updated_at=now,
    )
    await project.save()
    return project


async def get_project(slug: str, client_slug: str | None = None) -> Project:
    """Resolve a project by slug, optionally scoped to a client.

    Unscoped lookups must be unambiguous across clients.
    """
    if client_slug is not None:
        client = await get_client(client_slug)
        project = await Project.where(
            lambda p: (p.slug == slug) & (p.client_id == client.id)
        ).first()
        if project is None:
            raise NotFoundError(f"Client '{client_slug}' has no project '{slug}'")
        return project
    matches = await Project.where(lambda p: p.slug == slug).all()
    if not matches:
        raise NotFoundError(f"No project with slug '{slug}'")
    if len(matches) > 1:
        clients = await Client.all()
        names = sorted(next((c.slug for c in clients if c.id == m.client_id), "?") for m in matches)
        raise ConflictError(
            f"Project slug '{slug}' exists under multiple clients ({', '.join(names)}); "
            "pass --client to disambiguate"
        )
    return matches[0]


async def list_projects(
    client_slug: str | None = None, include_archived: bool = False
) -> list[Project]:
    if client_slug is not None:
        client = await get_client(client_slug)
        projects = await Project.where(lambda p: p.client_id == client.id).all()
    else:
        projects = await Project.all()
    if not include_archived:
        projects = [p for p in projects if p.archived_at is None]
    return sorted(projects, key=lambda p: p.name.lower())


async def update_project(
    slug: str,
    client_slug: str | None = None,
    *,
    name: str | None = None,
    new_slug: str | None = None,
    hourly_rate: Decimal | None = None,
) -> Project:
    project = await get_project(slug, client_slug)
    if new_slug and new_slug != project.slug:
        clash = await Project.where(
            lambda p: (p.client_id == project.client_id) & (p.slug == new_slug)
        ).exists()
        if clash:
            raise ConflictError(f"This client already has a project '{new_slug}'")
        project.slug = new_slug
    if name is not None:
        project.name = name.strip()
    if hourly_rate is not None:
        project.hourly_rate = hourly_rate
    project.updated_at = datetime.now()
    await project.save()
    return project


async def archive_project(slug: str, client_slug: str | None = None) -> Project:
    project = await get_project(slug, client_slug)
    project.archived_at = datetime.now()
    project.updated_at = project.archived_at
    await project.save()
    return project


async def delete_project(slug: str, client_slug: str | None = None, force: bool = False) -> None:
    """Delete a project. Refuses if entries exist unless force; never deletes invoiced work."""
    project = await get_project(slug, client_slug)
    pid = pk(project)
    invoiced = await Entry.where(
        lambda e, pid=pid: (e.project_id == pid) & (e.invoice_id != None)  # noqa: E711
    ).exists()
    if invoiced:
        raise ConflictError(f"Project '{slug}' has invoiced entries and can't be deleted")
    count = await Entry.where(lambda e, pid=pid: e.project_id == pid).count()
    if count and not force:
        raise ConflictError(
            f"Project '{slug}' has {count} entr{'y' if count == 1 else 'ies'}; "
            "delete with force to remove them too"
        )
    await Entry.where(lambda e, pid=pid: e.project_id == pid).delete()
    await project.delete()


async def effective_rate(project: Project) -> Decimal | None:
    """Project rate, falling back to the client default."""
    if project.hourly_rate is not None:
        return project.hourly_rate
    client = await Client.get_or_none(project.client_id)
    return client.hourly_rate if client else None


async def entry_seconds(project: Project, uninvoiced_only: bool = False) -> int:
    entries = await Entry.where(lambda e: e.project_id == project.id).all()
    if uninvoiced_only:
        entries = [e for e in entries if e.invoice_id is None]
    return sum(e.seconds for e in entries)
