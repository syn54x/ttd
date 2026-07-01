"""Export entries to records (the read side of import lives in interchange.importer)."""

from datetime import date, time

from ttd.interchange.model import EntryRecord
from ttd.services.entries import list_entries
from ttd.services.expenses import list_expenses
from ttd.storage.db import in_db_session
from ttd.storage.models import Client, ExpenseReceipt, Invoice, Project


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

    expense_views = await list_expenses(
        project_slug=project_slug,
        client_slug=client_slug,
        date_from=date_from,
        date_to=date_to,
    )
    if invoiced is not None:
        expense_views = [v for v in expense_views if (v.expense.invoice_id is not None) == invoiced]

    used_clients = {r.client for r in records}
    used_projects = {(r.client, r.project) for r in records}
    used_clients |= {v.client.slug for v in expense_views}
    used_projects |= {(v.client.slug, v.project.slug) for v in expense_views}

    all_clients = await Client.all()
    clients_meta = [
        {
            "slug": c.slug,
            "name": c.name,
            "currency": c.currency,
            "hourly_rate": str(c.hourly_rate) if c.hourly_rate is not None else None,
            "email": c.email,
        }
        for c in all_clients
        if c.slug in used_clients
    ]
    client_slugs = {c.id: c.slug for c in all_clients}
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

    invoice_numbers = {i.id: i.number for i in await Invoice.all()}
    expenses_meta = [
        {
            "id": str(v.expense.id),
            "client": v.client.slug,
            "project": v.project.slug,
            "incurred_date": v.expense.incurred_date.isoformat(),
            "description": v.expense.description,
            "amount": str(v.expense.amount),
            "note": v.expense.note,
            "invoice_number": invoice_numbers.get(v.expense.invoice_id, "")
            if v.expense.invoice_id
            else "",
        }
        for v in expense_views
    ]
    expense_ids = {str(v.expense.id) for v in expense_views}
    receipts_meta = [
        {
            "expense_id": str(r.expense_id),
            "filename": r.filename,
            "content_type": r.content_type,
            "data_b64": r.data_b64,
        }
        for r in await ExpenseReceipt.all()
        if str(r.expense_id) in expense_ids
    ]
    return records, {
        "clients": clients_meta,
        "projects": projects_meta,
        "expenses": expenses_meta,
        "receipts": receipts_meta,
    }
