"""Tests for database backup and restore."""

from __future__ import annotations

from decimal import Decimal

import pytest

from ttd.core import db_admin
from ttd.core.exceptions import ValidationError
from ttd.core.schemas import CreateClient
from ttd.core.services import clients as client_service


async def test_backup_populated_ledger(db, settings, tmp_path) -> None:
    await client_service.create_client(
        CreateClient(name="Acme", default_hourly_rate=Decimal("100"), currency="USD")
    )
    destination = tmp_path / "backup.db"
    result = await db_admin.backup_database(destination, settings=settings)
    assert result.destination == destination
    assert destination.exists()
    assert result.size_bytes > 0


async def test_backup_missing_database(settings, tmp_path) -> None:
    destination = tmp_path / "backup.db"
    with pytest.raises(ValidationError, match="No ledger database"):
        await db_admin.backup_database(destination, settings=settings)
    assert not destination.exists()


async def test_restore_requires_confirmation(db, settings, tmp_path) -> None:
    destination = tmp_path / "backup.db"
    await db_admin.backup_database(destination, settings=settings)
    with pytest.raises(ValidationError, match="restore is destructive"):
        await db_admin.restore_database(destination, settings=settings, confirmed=False)


async def test_restore_replaces_ledger(db, settings, tmp_path) -> None:
    await client_service.create_client(
        CreateClient(name="Acme", default_hourly_rate=Decimal("100"), currency="USD")
    )
    destination = tmp_path / "backup.db"
    await db_admin.backup_database(destination, settings=settings)

    await client_service.create_client(
        CreateClient(name="Other", default_hourly_rate=Decimal("50"), currency="USD")
    )
    assert len(await client_service.list_clients()) == 2

    await db_admin.restore_database(destination, settings=settings, confirmed=True)
    clients = await client_service.list_clients()
    assert len(clients) == 1
    assert clients[0].name == "Acme"


async def test_restore_invalid_source_fails(db, settings, tmp_path) -> None:
    invalid = tmp_path / "not-a-db.txt"
    invalid.write_text("not sqlite", encoding="utf-8")
    with pytest.raises(ValidationError, match="not a readable SQLite"):
        await db_admin.restore_database(invalid, settings=settings, confirmed=True)


async def test_restore_missing_source_fails(settings, tmp_path) -> None:
    missing = tmp_path / "missing.db"
    with pytest.raises(ValidationError, match="Backup file not found"):
        await db_admin.restore_database(missing, settings=settings, confirmed=True)
