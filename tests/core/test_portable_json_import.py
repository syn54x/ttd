"""Tests for merge JSON import."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from ferro import reset_engine

from ttd.core import db_admin
from ttd.core.db import close_db, init_db
from ttd.core.exceptions import ValidationError
from ttd.core.models.enums import BillingMode, EntryMode
from ttd.core.schemas import (
    CreateDurationEntry,
    LedgerClientRecord,
    LedgerDocument,
    LedgerEntryRecord,
    LedgerProjectRecord,
)
from ttd.core.services import clients as client_service
from ttd.core.services import time_entries as entry_service
from ttd.core.services.portable_json import export_ledger_json, import_ledger_json


async def _sample_document() -> LedgerDocument:
    client_id = uuid4()
    project_id = uuid4()
    entry_id = uuid4()
    return LedgerDocument(
        exported_at="2026-05-31T12:00:00+00:00",
        clients=[
            LedgerClientRecord(
                id=client_id,
                name="Portable",
                default_hourly_rate=Decimal("100"),
                currency="USD",
            )
        ],
        projects=[
            LedgerProjectRecord(
                id=project_id,
                client_id=client_id,
                name="Work",
                billing_mode=BillingMode.HOURLY,
            )
        ],
        time_entries=[
            LedgerEntryRecord(
                id=entry_id,
                project_id=project_id,
                work_date="2026-05-01",
                entry_mode=EntryMode.DURATION,
                billable_hours=Decimal("3"),
            )
        ],
    )


async def test_import_into_empty_db(db) -> None:
    document = await _sample_document()
    summary = await import_ledger_json(document, confirmed=True)
    assert summary.clients_inserted == 1
    assert summary.projects_inserted == 1
    assert summary.entries_inserted == 1
    assert len(await client_service.list_clients()) == 1


async def test_import_skips_existing_ids(db, sample_client) -> None:
    document = await _sample_document()
    document.clients[0].id = sample_client.id
    document.projects[0].client_id = sample_client.id
    summary = await import_ledger_json(document, confirmed=True)
    assert summary.clients_skipped == 1
    assert summary.clients_inserted == 0
    assert summary.projects_inserted == 1


async def test_import_same_file_twice(db) -> None:
    document = await _sample_document()
    first = await import_ledger_json(document, confirmed=True)
    assert first.clients_inserted == 1
    second = await import_ledger_json(document, confirmed=True)
    assert second.clients_skipped == 1
    assert second.projects_skipped == 1
    assert second.entries_skipped == 1


async def test_import_requires_confirmation(db) -> None:
    document = await _sample_document()
    with pytest.raises(ValidationError, match="Re-run with --yes"):
        await import_ledger_json(document, confirmed=False)


async def test_import_unknown_project_reference_fails(db) -> None:
    document = await _sample_document()
    document.time_entries[0].project_id = uuid4()
    with pytest.raises(ValidationError, match="unknown project"):
        await import_ledger_json(document, confirmed=True)
    assert await client_service.list_clients() == []


async def test_export_import_round_trip(db, hourly_project) -> None:
    await entry_service.create_duration_entry(
        CreateDurationEntry(
            project_id=hourly_project.id,
            work_date="2026-05-03",
            billable_hours=Decimal("4"),
        )
    )
    exported = await export_ledger_json()
    await db_admin.reset_database(confirmed=True)
    summary = await import_ledger_json(exported, confirmed=True)
    assert summary.clients_inserted == 1
    assert summary.entries_inserted == 1


async def test_import_cold_load_hydrates_enums(db) -> None:
    document = await _sample_document()
    await import_ledger_json(document, confirmed=True)
    project_id = document.projects[0].id
    await close_db()
    reset_engine()
    from ttd.core.models.project import Project

    Project._reregister_ferro()
    await init_db(db)
    loaded = await Project.get_or_none(project_id)
    assert loaded is not None
    assert isinstance(loaded.billing_mode, BillingMode)
