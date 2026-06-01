"""Full-ledger JSON export and merge import."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from ttd.core.exceptions import ValidationError
from ttd.core.models.client import Client
from ttd.core.models.project import Project
from ttd.core.models.time_entry import TimeEntry
from ttd.core.schemas import (
    LEDGER_SCHEMA_VERSION,
    CreateProject,
    ImportSummary,
    LedgerClientRecord,
    LedgerDocument,
    LedgerEntryRecord,
    LedgerProjectRecord,
)
from ttd.core.services import clients as client_service
from ttd.core.services import projects as project_service
from ttd.core.services import time_entries as entry_service


def _require_uuid(value: UUID | None, label: str) -> UUID:
    if value is None:
        raise ValidationError(f"{label} is missing an id")
    return value


async def export_ledger_json() -> LedgerDocument:
    """Build a portable document containing the full ledger."""
    client_records: list[LedgerClientRecord] = []
    project_records: list[LedgerProjectRecord] = []
    entry_records: list[LedgerEntryRecord] = []

    for client in await client_service.list_clients():
        client_id = _require_uuid(client.id, "client")
        client_records.append(
            LedgerClientRecord(
                id=client_id,
                name=client.name,
                default_hourly_rate=client.default_hourly_rate,
                currency=client.currency,
                rounding_increment_minutes=client.rounding_increment_minutes,
            )
        )
        for project in await project_service.list_projects_for_client(client_id):
            project_id = _require_uuid(project.id, "project")
            project_records.append(
                LedgerProjectRecord(
                    id=project_id,
                    client_id=project.client_id,
                    name=project.name,
                    billing_mode=project.billing_mode,
                    hourly_rate=project.hourly_rate,
                    currency=project.currency,
                    contract_total=project.contract_total,
                    soft_max_hours=project.soft_max_hours,
                    rounding_increment_minutes=project.rounding_increment_minutes,
                )
            )
            for entry in await entry_service.list_time_entries_for_project(project_id):
                entry_id = _require_uuid(entry.id, "time entry")
                entry_records.append(
                    LedgerEntryRecord(
                        id=entry_id,
                        project_id=entry.project_id,
                        work_date=entry.work_date,
                        entry_mode=entry.entry_mode,
                        billable_hours=entry.billable_hours,
                        started_at=entry.started_at,
                        ended_at=entry.ended_at,
                        billable=entry.billable,
                        note=entry.note,
                    )
                )

    return LedgerDocument(
        schema_version=LEDGER_SCHEMA_VERSION,
        exported_at=datetime.now(tz=UTC),
        clients=client_records,
        projects=project_records,
        time_entries=entry_records,
    )


def render_ledger_json(document: LedgerDocument) -> str:
    """Serialize a ledger document to JSON."""
    return document.model_dump_json(indent=2)


def parse_ledger_json(text: str) -> LedgerDocument:
    """Parse and validate a ledger JSON document."""
    return LedgerDocument.model_validate_json(text)


LedgerRecord = LedgerClientRecord | LedgerProjectRecord | LedgerEntryRecord


def _duplicate_ids(records: Sequence[LedgerRecord]) -> None:
    seen: set[UUID] = set()
    for record in records:
        if record.id in seen:
            raise ValidationError(f"Duplicate id in ledger document: {record.id}")
        seen.add(record.id)


def _validate_document_references(document: LedgerDocument) -> None:
    _duplicate_ids(document.clients)
    _duplicate_ids(document.projects)
    _duplicate_ids(document.time_entries)

    client_ids = {client.id for client in document.clients}
    project_ids = {project.id for project in document.projects}

    for project in document.projects:
        if project.client_id not in client_ids:
            raise ValidationError(
                f"Project {project.id} references unknown client {project.client_id}"
            )

    for entry in document.time_entries:
        if entry.project_id not in project_ids:
            raise ValidationError(
                f"Time entry {entry.id} references unknown project {entry.project_id}"
            )


async def _count_pending_inserts(document: LedgerDocument) -> int:
    pending = 0
    for client in document.clients:
        if await Client.get_or_none(client.id) is None:
            pending += 1
    for project in document.projects:
        if await Project.get_or_none(project.id) is None:
            pending += 1
    for entry in document.time_entries:
        if await TimeEntry.get_or_none(entry.id) is None:
            pending += 1
    return pending


async def _rollback_import(
    *,
    client_ids: list[UUID],
    project_ids: list[UUID],
    entry_ids: list[UUID],
) -> None:
    for entry_id in reversed(entry_ids):
        entry = await TimeEntry.get_or_none(entry_id)
        if entry is not None:
            await entry.delete()
    for project_id in reversed(project_ids):
        project = await Project.get_or_none(project_id)
        if project is not None:
            await project.delete()
    for client_id in reversed(client_ids):
        client = await Client.get_or_none(client_id)
        if client is not None:
            await client.delete()


async def import_ledger_json(
    document: LedgerDocument,
    *,
    confirmed: bool,
) -> ImportSummary:
    """Merge ledger records, skipping any id that already exists."""
    _validate_document_references(document)

    pending = await _count_pending_inserts(document)
    if pending > 0 and not confirmed:
        raise ValidationError(
            f"Import will insert {pending} new records. Re-run with --yes to confirm."
        )

    summary = ImportSummary()
    inserted_clients: list[UUID] = []
    inserted_projects: list[UUID] = []
    inserted_entries: list[UUID] = []

    try:
        for record in document.clients:
            if await client_service.insert_client_if_absent(record):
                summary.clients_inserted += 1
                inserted_clients.append(record.id)
            else:
                summary.clients_skipped += 1

        for record in document.projects:
            create_data = CreateProject(
                client_id=record.client_id,
                name=record.name,
                billing_mode=record.billing_mode,
                hourly_rate=record.hourly_rate,
                currency=record.currency,
                contract_total=record.contract_total,
                soft_max_hours=record.soft_max_hours,
                rounding_increment_minutes=record.rounding_increment_minutes,
            )
            if await project_service.insert_project_if_absent(record.id, create_data):
                summary.projects_inserted += 1
                inserted_projects.append(record.id)
            else:
                summary.projects_skipped += 1

        for record in document.time_entries:
            if await entry_service.insert_entry_if_absent(record):
                summary.entries_inserted += 1
                inserted_entries.append(record.id)
            else:
                summary.entries_skipped += 1
    except BaseException:
        await _rollback_import(
            client_ids=inserted_clients,
            project_ids=inserted_projects,
            entry_ids=inserted_entries,
        )
        raise

    return summary
