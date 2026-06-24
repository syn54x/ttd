"""Client CRUD. All functions assume an initialized DB."""

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from ttd.core.errors import ConflictError, NotFoundError
from ttd.core.slugs import slugify
from ttd.storage.db import in_db_session
from ttd.storage.models import Client, Entry, Project


@in_db_session
async def create_client(
    name: str,
    *,
    slug: str | None = None,
    hourly_rate: Decimal | None = None,
    currency: str = "USD",
    contact_name: str | None = None,
    email: str | None = None,
    address: str | None = None,
) -> Client:
    name = name.strip()
    slug = slug or slugify(name)
    if await Client.where(lambda c: c.slug == slug).exists():
        raise ConflictError(f"A client with slug '{slug}' already exists")
    now = datetime.now()
    client = Client(
        id=uuid4(),
        name=name,
        slug=slug,
        hourly_rate=hourly_rate,
        currency=currency.upper(),
        contact_name=contact_name,
        email=email,
        address=address,
        created_at=now,
        updated_at=now,
    )
    await client.save()
    return client


async def get_client(slug: str) -> Client:
    client = await Client.where(lambda c: c.slug == slug).first()
    if client is None:
        raise NotFoundError(f"No client with slug '{slug}'")
    return client


@in_db_session
async def list_clients(include_archived: bool = False) -> list[Client]:
    clients = await Client.select().order_by("name").all()
    if not include_archived:
        clients = [c for c in clients if c.archived_at is None]
    return clients


@in_db_session
async def update_client(
    slug: str,
    *,
    name: str | None = None,
    new_slug: str | None = None,
    hourly_rate: Decimal | None = None,
    currency: str | None = None,
    contact_name: str | None = None,
    email: str | None = None,
    address: str | None = None,
) -> Client:
    client = await get_client(slug)
    if new_slug and new_slug != slug:
        if await Client.where(lambda c: c.slug == new_slug).exists():
            raise ConflictError(f"A client with slug '{new_slug}' already exists")
        client.slug = new_slug
    if name is not None:
        client.name = name.strip()
    if hourly_rate is not None:
        client.hourly_rate = hourly_rate
    if currency is not None:
        client.currency = currency.upper()
    if contact_name is not None:
        client.contact_name = contact_name
    if email is not None:
        client.email = email
    if address is not None:
        client.address = address
    client.updated_at = datetime.now()
    await client.save()
    return client


@in_db_session
async def archive_client(slug: str) -> Client:
    client = await get_client(slug)
    client.archived_at = datetime.now()
    client.updated_at = client.archived_at
    await client.save()
    return client


@in_db_session
async def delete_client(slug: str, force: bool = False) -> None:
    """Delete a client. Refuses if projects exist unless force; never deletes invoiced work."""
    client = await get_client(slug)
    projects = await Project.where(lambda p: p.client_id == client.id).all()
    if projects and not force:
        raise ConflictError(
            f"Client '{slug}' has {len(projects)} project(s); use --force to delete them too"
        )
    for project in projects:
        pid = project.id
        invoiced = await Entry.where(
            lambda e, pid=pid: (e.project_id == pid) & (e.invoice_id != None)  # noqa: E711
        ).exists()
        if invoiced:
            raise ConflictError(
                f"Project '{project.slug}' has invoiced entries; cannot delete client '{slug}'"
            )
    for project in projects:
        pid = project.id
        await Entry.where(lambda e, pid=pid: e.project_id == pid).delete()
        await project.delete()
    await client.delete()
