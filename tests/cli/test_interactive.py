"""Tests for CLI interactive mode (mocked prompts)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from ttd.cli.inputs import ClientAddInput
from ttd.cli.interactive import RunMode, resolve_run_mode, set_invocation_tokens
from ttd.cli.main import app
from ttd.core.db import close_db, init_db


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


def test_resolve_run_mode_bare_subcommand(monkeypatch) -> None:
    monkeypatch.setattr("ttd.cli.interactive.stdin_is_tty", lambda: True)
    set_invocation_tokens(["client", "add"])
    mode, missing = resolve_run_mode(
        subcommand=("client", "add"),
        interactive_flag=False,
        provided={"name": None, "rate": None},
        required_for_run=("name", "rate"),
    )
    assert mode == RunMode.INTERACTIVE
    assert "name" in missing


def test_resolve_run_mode_partial_without_interactive() -> None:
    set_invocation_tokens(["client", "add", "--name", "Acme"])
    mode, missing = resolve_run_mode(
        subcommand=("client", "add"),
        interactive_flag=False,
        provided={"name": "Acme", "rate": None},
        required_for_run=("name", "rate"),
    )
    assert mode == RunMode.ERROR
    assert missing == ["rate"]


def test_client_add_interactive_mocked(cli_db, monkeypatch) -> None:
    monkeypatch.setattr("ttd.cli.interactive.stdin_is_tty", lambda: True)
    collected = ClientAddInput(name="Acme", rate="150", currency="USD")

    with patch(
        "ttd.cli.client_cmds.collect.collect_client_add",
        new=AsyncMock(return_value=collected),
    ):
        run_cli(["client", "add"])

    run_cli(
        [
            "client",
            "add",
            "--name",
            "Beta",
            "--rate",
            "100",
            "--currency",
            "USD",
        ]
    )


def test_client_add_partial_without_i_errors(cli_db) -> None:
    set_invocation_tokens(["client", "add", "--name", "Acme"])
    with pytest.raises(SystemExit) as exc_info:
        app(["client", "add", "--name", "Acme"])
    assert exc_info.value.code == 2


def test_non_tty_interactive_fails(cli_db, monkeypatch) -> None:
    monkeypatch.setattr("ttd.cli.interactive.stdin_is_tty", lambda: False)
    set_invocation_tokens(["client", "add", "-i"])
    with pytest.raises(SystemExit) as exc_info:
        app(["client", "add", "-i"])
    assert exc_info.value.code == 2
