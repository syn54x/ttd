"""CLI tests for backup, restore, and portable JSON commands."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path

import pytest

from ttd.cli.interactive import set_invocation_tokens
from ttd.cli.main import app
from ttd.core.db import close_db, init_db
from ttd.core.schemas import CreateClient
from ttd.core.services import clients as client_service


@pytest.fixture
def cli_settings(monkeypatch, settings):
    monkeypatch.setattr("ttd.core.config.get_settings", lambda: settings)
    return settings


@pytest.fixture
def cli_db(cli_settings, reset_db_state):
    asyncio.run(init_db(cli_settings))
    yield cli_settings
    asyncio.run(close_db())


def run_cli(argv: list[str]) -> int:
    set_invocation_tokens(argv)
    with pytest.raises(SystemExit) as exc_info:
        app(argv)
    return int(exc_info.value.code)


def test_db_backup_cli(cli_db, tmp_path: Path) -> None:
    asyncio.run(
        client_service.create_client(
            CreateClient(
                name="Acme",
                default_hourly_rate=Decimal("100"),
                currency="USD",
            )
        )
    )
    destination = tmp_path / "ledger-backup.db"
    assert run_cli(["db", "backup", str(destination)]) == 0
    assert destination.exists()


def test_db_restore_requires_yes(cli_db, tmp_path: Path) -> None:
    destination = tmp_path / "ledger-backup.db"
    assert run_cli(["db", "backup", str(destination)]) == 0
    assert run_cli(["db", "restore", str(destination)]) == 2


def test_export_json_requires_output(cli_db) -> None:
    assert run_cli(["export", "json"]) == 2


def test_export_and_import_json(cli_db, tmp_path: Path) -> None:
    asyncio.run(
        client_service.create_client(
            CreateClient(
                name="Portable",
                default_hourly_rate=Decimal("90"),
                currency="USD",
            )
        )
    )
    json_path = tmp_path / "ledger.json"
    assert run_cli(["export", "json", "--output", str(json_path)]) == 0
    assert json_path.exists()

    assert run_cli(["db", "reset", "--yes"]) == 0
    asyncio.run(close_db())
    asyncio.run(init_db(cli_db))
    assert asyncio.run(client_service.list_clients()) == []

    assert run_cli(["import", "json", str(json_path), "--yes"]) == 0
    asyncio.run(close_db())
    asyncio.run(init_db(cli_db))
    clients = asyncio.run(client_service.list_clients())
    assert len(clients) == 1
    assert clients[0].name == "Portable"


def test_import_json_requires_yes(cli_db, tmp_path: Path) -> None:
    asyncio.run(
        client_service.create_client(
            CreateClient(
                name="NeedsYes",
                default_hourly_rate=Decimal("90"),
                currency="USD",
            )
        )
    )
    json_path = tmp_path / "ledger.json"
    assert run_cli(["export", "json", "--output", str(json_path)]) == 0
    assert run_cli(["db", "reset", "--yes"]) == 0
    asyncio.run(close_db())
    asyncio.run(init_db(cli_db))
    assert run_cli(["import", "json", str(json_path)]) == 2
