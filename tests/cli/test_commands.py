from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import UUID

import pytest

from ttd.cli.interactive import set_invocation_tokens
from ttd.cli.main import app
from ttd.core.db import close_db, init_db
from ttd.core.services import time_entries as entry_service


@pytest.fixture
def cli_settings(monkeypatch, settings):
    monkeypatch.setattr("ttd.core.config.get_settings", lambda: settings)
    return settings


@pytest.fixture
def cli_db(cli_settings, reset_db_state):
    asyncio.run(init_db(cli_settings))
    yield cli_settings
    asyncio.run(close_db())


def run_cli(argv: list[str]) -> None:
    set_invocation_tokens(argv)
    with pytest.raises(SystemExit) as exc_info:
        app(argv)
    assert exc_info.value.code == 0


def test_client_add_and_list(cli_db, capsys) -> None:
    run_cli(["client", "add", "Acme", "--rate", "150", "--currency", "USD"])
    run_cli(["client", "list"])
    out = capsys.readouterr().out
    assert "Acme" in out
    assert "150" in out


def test_project_and_log_duration(cli_db, capsys) -> None:
    run_cli(["client", "add", "Acme", "--rate", "150"])
    run_cli(
        [
            "project",
            "add",
            "--client",
            "Acme",
            "--name",
            "Website",
            "--billing-mode",
            "hourly",
        ]
    )
    run_cli(
        [
            "log",
            "--client",
            "Acme",
            "--project",
            "Website",
            "--date",
            "2026-05-20",
            "--hours",
            "2.5",
            "--note",
            "API work",
        ]
    )
    run_cli(
        [
            "entries",
            "list",
            "--client",
            "Acme",
            "--project",
            "Website",
            "--from",
            "2026-05-01",
            "--to",
            "2026-05-31",
        ]
    )
    out = capsys.readouterr().out
    assert "2.50h" in out
    assert "API work" in out


def test_log_interval_natural_language(cli_db, capsys) -> None:
    run_cli(["client", "add", "Gamma", "--rate", "100"])
    run_cli(
        [
            "project",
            "add",
            "--client",
            "Gamma",
            "--name",
            "Support",
        ]
    )
    run_cli(
        [
            "log",
            "--client",
            "Gamma",
            "--project",
            "Support",
            "--when",
            "2026-05-21 9am to 11:30am",
        ]
    )
    out = capsys.readouterr().out
    assert "09:00" in out
    assert "11:30" in out


def test_log_interval(cli_db, capsys) -> None:
    run_cli(["client", "add", "Beta", "--rate", "100"])
    run_cli(
        [
            "project",
            "add",
            "--client",
            "Beta",
            "--name",
            "Ops",
        ]
    )
    run_cli(
        [
            "log",
            "--client",
            "Beta",
            "--project",
            "Ops",
            "--date",
            "2026-05-21",
            "--from",
            "09:00",
            "--to",
            "11:30",
        ]
    )
    out = capsys.readouterr().out
    assert "09:00" in out
    assert "11:30" in out


async def _first_entry_id() -> str:
    from ttd.core.services import clients as client_service
    from ttd.core.services import projects as project_service

    client = (await client_service.list_clients())[0]
    project = (await project_service.list_projects_for_client(client.id))[0]
    entry = (await entry_service.list_time_entries_for_project(project.id))[0]
    return str(entry.id)


def test_entries_edit_duration(cli_db) -> None:
    run_cli(["client", "add", "Acme", "--rate", "150"])
    run_cli(
        [
            "project",
            "add",
            "--client",
            "Acme",
            "--name",
            "Website",
        ]
    )
    run_cli(
        [
            "log",
            "--client",
            "Acme",
            "--project",
            "Website",
            "--date",
            "2026-05-22",
            "--hours",
            "1",
        ]
    )
    entry_id = asyncio.run(_first_entry_id())
    run_cli(
        [
            "entries",
            "edit",
            entry_id,
            "--hours",
            "3",
        ]
    )
    updated = asyncio.run(entry_service.get_time_entry(UUID(entry_id)))
    assert updated.billable_hours == Decimal("3")


def test_cli_not_found_exit(cli_db) -> None:
    with pytest.raises(SystemExit) as exc_info:
        app(["log", "--client", "Missing", "--project", "X", "--hours", "1"])
    assert exc_info.value.code == 1


def test_cli_validation_exit(cli_db) -> None:
    run_cli(["client", "add", "Acme", "--rate", "150"])
    with pytest.raises(SystemExit) as exc_info:
        app(["log", "--client", "Acme", "--hours", "1"])
    assert exc_info.value.code == 2
