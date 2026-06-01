"""Tests for full-ledger JSON export."""

from __future__ import annotations

from decimal import Decimal

from ttd.core.schemas import CreateClient, CreateDurationEntry, LedgerDocument
from ttd.core.services import clients as client_service
from ttd.core.services import time_entries as entry_service
from ttd.core.services.portable_json import (
    export_ledger_json,
    parse_ledger_json,
    render_ledger_json,
)


async def test_export_empty_ledger(db) -> None:
    document = await export_ledger_json()
    assert document.clients == []
    assert document.projects == []
    assert document.time_entries == []
    assert document.schema_version == 1


async def test_export_includes_entities(db, sample_client, hourly_project) -> None:
    await entry_service.create_duration_entry(
        CreateDurationEntry(
            project_id=hourly_project.id,
            work_date="2026-05-01",
            billable_hours=Decimal("2.5"),
            note="Design",
        )
    )
    document = await export_ledger_json()
    assert len(document.clients) == 1
    assert len(document.projects) == 1
    assert len(document.time_entries) == 1
    assert document.projects[0].client_id == document.clients[0].id


async def test_export_json_round_trip(db, sample_client, hourly_project) -> None:
    await entry_service.create_duration_entry(
        CreateDurationEntry(
            project_id=hourly_project.id,
            work_date="2026-05-02",
            billable_hours=Decimal("1"),
        )
    )
    rendered = render_ledger_json(await export_ledger_json())
    parsed = parse_ledger_json(rendered)
    assert isinstance(parsed, LedgerDocument)
    assert parsed.clients[0].default_hourly_rate == Decimal("150")


async def test_export_two_clients(db) -> None:
    await client_service.create_client(
        CreateClient(name="A", default_hourly_rate=Decimal("100"), currency="USD")
    )
    await client_service.create_client(
        CreateClient(name="B", default_hourly_rate=Decimal("120"), currency="USD")
    )
    document = await export_ledger_json()
    assert len(document.clients) == 2
