"""Import engine: validate rows, resolve slugs, dedupe, apply."""

from dataclasses import dataclass, field
from datetime import date as date_t
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

from ttd.core.errors import TtdError
from ttd.interchange.model import EntryRecord, from_raw
from ttd.services import clients as client_svc
from ttd.services import projects as project_svc
from ttd.storage.models import Client, Entry, EntrySource, Expense, ExpenseReceipt, Project, pk

OnConflict = Literal["skip", "update", "duplicate"]


@dataclass
class ImportPlan:
    new: list[EntryRecord] = field(default_factory=list)
    update: list[tuple[EntryRecord, Entry]] = field(default_factory=list)
    skip: list[tuple[EntryRecord, str]] = field(default_factory=list)  # (record, reason)
    errors: list[tuple[int, str]] = field(default_factory=list)  # (row number, message)
    missing_clients: set[str] = field(default_factory=set)
    missing_projects: set[tuple[str, str]] = field(default_factory=set)  # (client, project)

    @property
    def importable(self) -> int:
        return len(self.new) + len(self.update)


def validate_rows(
    raws: list[dict[str, Any]],
    default_client: str | None = None,
    default_project: str | None = None,
) -> tuple[list[EntryRecord], list[tuple[int, str]]]:
    records: list[EntryRecord] = []
    errors: list[tuple[int, str]] = []
    for i, raw in enumerate(raws, start=2):  # row 1 is the header
        data = dict(raw)
        if not str(data.get("client") or "").strip() and default_client:
            data["client"] = default_client
        if not str(data.get("project") or "").strip() and default_project:
            data["project"] = default_project
        try:
            records.append(from_raw(data))
        except Exception as exc:
            message = str(exc).split("\n")[1].strip() if "\n" in str(exc) else str(exc)
            errors.append((i, message))
    return records, errors


async def build_plan(
    raws: list[dict[str, Any]],
    *,
    on_conflict: OnConflict = "skip",
    default_client: str | None = None,
    default_project: str | None = None,
) -> ImportPlan:
    records, errors = validate_rows(raws, default_client, default_project)
    plan = ImportPlan(errors=errors)

    clients = {c.slug: c for c in await Client.all()}
    projects = {}
    for p in await Project.all():
        client_slug = next((c.slug for c in clients.values() if c.id == p.client_id), None)
        if client_slug:
            projects[(client_slug, p.slug)] = p

    existing = await Entry.all()
    by_uuid = {e.id: e for e in existing}
    project_slug_of = {pk(p): key for key, p in projects.items()}
    by_content = {}
    for e in existing:
        key = project_slug_of.get(e.project_id)
        if key is None:
            continue
        by_content[
            (
                key[0],
                key[1],
                e.work_date,
                e.started_at.time() if e.started_at else None,
                e.ended_at.time() if e.ended_at else None,
                e.seconds,
                e.note,
            )
        ] = e

    seen_in_file: set[tuple] = set()
    for record in records:
        if record.client not in clients:
            plan.missing_clients.add(record.client)
        if (record.client, record.project) not in projects:
            plan.missing_projects.add((record.client, record.project))

        match = by_uuid.get(record.uuid) if record.uuid else None
        if match is None:
            match = by_content.get(record.content_key)

        if record.content_key in seen_in_file:
            plan.skip.append((record, "duplicate row within file"))
            continue
        seen_in_file.add(record.content_key)

        if match is None:
            plan.new.append(record)
        elif match.invoice_id is not None:
            plan.skip.append((record, "matches an invoiced entry"))
        elif on_conflict == "skip":
            plan.skip.append((record, "already exists"))
        elif on_conflict == "update":
            plan.update.append((record, match))
        else:  # duplicate
            plan.new.append(record)
    return plan


async def apply_plan(
    plan: ImportPlan,
    *,
    create_missing: bool = False,
    metadata: dict[str, Any] | None = None,
) -> int:
    """Create/update entries. Returns how many entries were written."""
    if plan.missing_clients or plan.missing_projects:
        if not create_missing:
            missing = ", ".join(
                sorted(plan.missing_clients | {f"{c}/{p}" for c, p in plan.missing_projects})
            )
            raise TtdError(
                f"Unknown clients/projects in file: {missing} — "
                "rerun with --create-missing to add them"
            )
        await _create_missing(plan, metadata or {})

    clients = {c.slug: c for c in await Client.all()}
    project_map = {}
    for p in await Project.all():
        client_slug = next((c.slug for c in clients.values() if c.id == p.client_id), None)
        project_map[(client_slug, p.slug)] = p

    written = 0
    stamp = datetime.now()
    taken_ids = {e.id for e in await Entry.all()}
    for record in plan.new:
        project = project_map[(record.client, record.project)]
        entry = Entry(
            id=record.uuid or uuid4(),
            project_id=pk(project),
            work_date=record.date,
            started_at=datetime.combine(record.date, record.start) if record.start else None,
            ended_at=datetime.combine(record.date, record.end) if record.end else None,
            seconds=record.seconds,
            note=record.note,
            tags=record.tags,
            billable=record.billable,
            source=EntrySource.IMPORT,
            created_at=stamp,
            updated_at=stamp,
        )
        if entry.id in taken_ids:  # uid collision when on_conflict=duplicate
            entry.id = uuid4()
        taken_ids.add(entry.id)
        await entry.save()
        written += 1

    for record, target in plan.update:
        project = project_map[(record.client, record.project)]
        target.project_id = pk(project)
        target.work_date = record.date
        target.started_at = datetime.combine(record.date, record.start) if record.start else None
        target.ended_at = datetime.combine(record.date, record.end) if record.end else None
        target.seconds = record.seconds
        target.note = record.note
        target.tags = record.tags
        target.billable = record.billable
        target.updated_at = stamp
        await target.save()
        written += 1
    return written


async def _create_missing(plan: ImportPlan, metadata: dict[str, Any]) -> None:
    client_meta = {c.get("slug"): c for c in metadata.get("clients", [])}
    project_meta = {(p.get("client"), p.get("slug")): p for p in metadata.get("projects", [])}
    for slug in sorted(plan.missing_clients):
        meta = client_meta.get(slug, {})
        rate = meta.get("hourly_rate")
        await client_svc.create_client(
            meta.get("name") or slug.replace("-", " ").title(),
            slug=slug,
            hourly_rate=Decimal(str(rate)) if rate is not None else None,
            currency=meta.get("currency") or "USD",
            email=meta.get("email"),
        )
    for client_slug, project_slug in sorted(plan.missing_projects):
        meta = project_meta.get((client_slug, project_slug), {})
        rate = meta.get("hourly_rate")
        await project_svc.create_project(
            meta.get("name") or project_slug.replace("-", " ").title(),
            client_slug,
            slug=project_slug,
            hourly_rate=Decimal(str(rate)) if rate is not None else None,
        )


async def restore_expenses(
    metadata: dict[str, Any],
    *,
    on_conflict: OnConflict = "skip",
    create_missing: bool = False,
) -> int:
    """Restore expenses + receipts from a JSON backup's metadata. Returns count written.

    Never sets ``invoice_id`` — imports keep ``invoice_number`` informational only,
    mirroring entry import.
    """
    expenses = metadata.get("expenses", [])
    if not expenses:
        return 0

    if create_missing:
        # Reuse the client/project bootstrap by faking a plan of the referenced pairs.
        plan = ImportPlan()
        existing_clients = {c.slug for c in await Client.all()}
        projects_present: set[tuple[str, str]] = set()
        all_clients = {c.id: c for c in await Client.all()}
        for p in await Project.all():
            client = all_clients.get(p.client_id)
            if client:
                projects_present.add((client.slug, p.slug))
        for row in expenses:
            if row["client"] not in existing_clients:
                plan.missing_clients.add(row["client"])
            if (row["client"], row["project"]) not in projects_present:
                plan.missing_projects.add((row["client"], row["project"]))
        if plan.missing_clients or plan.missing_projects:
            await _create_missing(plan, metadata)

    clients = {c.slug: c for c in await Client.all()}
    project_map: dict[tuple[str, str], Project] = {}
    for p in await Project.all():
        for cslug, c in clients.items():
            if c.id == p.client_id:
                project_map[(cslug, p.slug)] = p
                break

    existing = {str(e.id): e for e in await Expense.all()}
    stamp = datetime.now()
    written = 0
    written_ids: set[str] = set()
    for row in expenses:
        key = (row["client"], row["project"])
        if key not in project_map:
            continue  # unresolved project; skip silently
        project = project_map[key]
        match = existing.get(row["id"])
        if match is not None and match.invoice_id is not None:
            continue  # never touch invoiced expenses
        if match is not None and on_conflict == "skip":
            continue
        if match is not None and on_conflict == "update":
            match.project_id = pk(project)
            match.incurred_date = date_t.fromisoformat(row["incurred_date"])
            match.description = row["description"]
            match.amount = Decimal(row["amount"])
            match.note = row.get("note", "")
            match.updated_at = stamp
            await match.save()
            written_ids.add(row["id"])
        else:  # new (or duplicate)
            await Expense(
                id=UUID(row["id"]),
                project_id=pk(project),
                incurred_date=date_t.fromisoformat(row["incurred_date"]),
                description=row["description"],
                amount=Decimal(row["amount"]),
                note=row.get("note", ""),
                created_at=stamp,
                updated_at=stamp,
            ).save()
            written_ids.add(row["id"])
        written += 1

    # Receipts: replace any existing receipt for expenses that were actually written.
    for r in metadata.get("receipts", []):
        if r["expense_id"] not in written_ids:
            continue
        expense_uuid = UUID(r["expense_id"])
        for old in await ExpenseReceipt.where(
            lambda rec, eid=expense_uuid: rec.expense_id == eid
        ).all():
            await old.delete()
        await ExpenseReceipt(
            id=uuid4(),
            expense_id=expense_uuid,
            filename=r["filename"],
            content_type=r["content_type"],
            data_b64=r["data_b64"],
        ).save()
    return written
