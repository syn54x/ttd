"""Export entries to records (the read side of import lives in interchange.importer)."""

from datetime import date, time

from ttd.interchange.model import EntryRecord
from ttd.services.entries import list_entries
from ttd.storage.db import in_db_session
from ttd.storage.models import Client, Invoice, Project


@in_db_session
async def export_records(
    *,
    project_slug: str | None = None,
    client_slug: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    invoiced: bool | None = None,  # None = all
) -> tuple[list[EntryRecord], dict]:
    rows = await list_entries(
        project_slug=project_slug,
        client_slug=client_slug,
        date_from=date_from,
        date_to=date_to,
    )
    if invoiced is not None:
        rows = [r for r in rows if (r.entry.invoice_id is not None) == invoiced]

    numbers = {i.id: i.number for i in await Invoice.all()}
    records = [
        EntryRecord(
            uid=str(r.entry.id),
            client=r.client.slug,
            project=r.project.slug,
            date=r.entry.work_date,
            start=r.entry.started_at.time() if r.entry.started_at else None,
            end=r.entry.ended_at.time() if r.entry.ended_at else None,
            seconds=r.entry.seconds,
            note=r.entry.note,
            tags=r.entry.tags,
            billable=r.entry.billable,
            invoice_number=numbers.get(r.entry.invoice_id, "") if r.entry.invoice_id else "",
        )
        for r in rows
    ]
    records.sort(key=lambda r: (r.date, r.start or time.min, r.uid))

    used_clients = {r.client for r in records}
    used_projects = {(r.client, r.project) for r in records}
    clients_meta = [
        {
            "slug": c.slug,
            "name": c.name,
            "currency": c.currency,
            "hourly_rate": str(c.hourly_rate) if c.hourly_rate is not None else None,
            "email": c.email,
        }
        for c in await Client.all()
        if c.slug in used_clients
    ]
    client_slugs = {c.id: c.slug for c in await Client.all()}
    projects_meta = [
        {
            "client": client_slugs.get(p.client_id),
            "slug": p.slug,
            "name": p.name,
            "hourly_rate": str(p.hourly_rate) if p.hourly_rate is not None else None,
        }
        for p in await Project.all()
        if (client_slugs.get(p.client_id), p.slug) in used_projects
    ]
    return records, {"clients": clients_meta, "projects": projects_meta}
