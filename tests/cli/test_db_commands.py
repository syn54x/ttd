"""Tests for `ttd db` commands."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from ttd.cli.interactive import set_invocation_tokens
from ttd.cli.main import app
from ttd.core import db_admin
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


def test_describe_db_uses_settings(cli_settings) -> None:
    location = db_admin.describe_db(cli_settings)
    assert location.db_path == cli_settings.db_path
    assert location.data_dir == cli_settings.data_dir


def test_db_where_cli(cli_settings) -> None:
    assert run_cli(["db", "where"]) == 0


def test_db_migrate_creates_file(cli_settings, reset_db_state, capsys) -> None:
    path = cli_settings.db_path
    assert not path.exists()
    code = run_cli(["db", "migrate"])
    assert code == 0
    assert path.exists()
    assert "Schema applied" in capsys.readouterr().out


def test_db_reset_requires_yes(cli_db) -> None:
    assert run_cli(["db", "reset"]) == 2


def test_db_reset_with_yes(cli_db, cli_settings) -> None:
    asyncio.run(
        client_service.create_client(
            CreateClient(
                name="Acme",
                default_hourly_rate=Decimal("100"),
                currency="USD",
            )
        )
    )
    assert run_cli(["db", "reset", "--yes"]) == 0
    asyncio.run(close_db())
    asyncio.run(init_db(cli_settings))
    assert asyncio.run(client_service.list_clients()) == []
