from __future__ import annotations

from pathlib import Path

import pytest

from ttd.cli.interactive import set_invocation_tokens
from ttd.cli.main import app
from ttd.core.config import clear_settings_cache
from ttd.core.config_files import CONFIG_FILENAME, global_config_path, read_toml


@pytest.fixture(autouse=True)
def clear_config_cache() -> None:
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.fixture
def config_home(monkeypatch, tmp_path: Path) -> Path:
    xdg = tmp_path / "xdg-config"
    xdg.mkdir(exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    for var in ("TTD_DATA_DIR", "TTD_DB_FILENAME", "TTD_CLOCK_FORMAT"):
        monkeypatch.delenv(var, raising=False)
    return xdg


def run_cli(argv: list[str]) -> None:
    set_invocation_tokens(argv)
    with pytest.raises(SystemExit) as exc_info:
        app(argv)
    assert exc_info.value.code == 0


def test_config_get_stdout(config_home: Path, capsys) -> None:
    run_cli(["config", "set", "--global", "data_dir", "/var/ttd"])
    run_cli(["config", "get", "data_dir"])
    out = capsys.readouterr().out.strip().splitlines()[-1]
    assert out == str(Path("/var/ttd").resolve())


def test_config_local_set_creates_file(
    config_home: Path, tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    run_cli(["config", "set", "clock_format", "12h"])
    assert (tmp_path / CONFIG_FILENAME).is_file()
    assert read_toml(tmp_path / CONFIG_FILENAME)["clock_format"] == "12h"


def test_config_show_lists_sources(
    config_home: Path, tmp_path: Path, monkeypatch, capsys
) -> None:
    global_path = global_config_path()
    global_path.parent.mkdir(parents=True, exist_ok=True)
    global_path.write_text('db_filename = "global.db"\n')
    local_path = tmp_path / CONFIG_FILENAME
    local_path.write_text('clock_format = "12h"\n')
    monkeypatch.chdir(tmp_path)
    run_cli(["config", "show"])
    out = capsys.readouterr().out
    assert "db_filename" in out
    assert "clock_format" in out
    assert "global:" in out
    assert "local:" in out


def test_config_help_lists_subcommands() -> None:
    with pytest.raises(SystemExit) as exc_info:
        app(["config", "--help"])
    assert exc_info.value.code == 0


def test_config_init_interactive_mocked(config_home: Path, monkeypatch) -> None:
    from unittest.mock import AsyncMock, patch

    from ttd.cli.inputs import ConfigInitInput

    monkeypatch.setattr("ttd.cli.interactive.stdin_is_tty", lambda: True)
    collected = ConfigInitInput(
        data_dir=str(config_home / "data"),
        db_filename="ttd.db",
        clock_format="24h",
        create_data_dir=True,
        run_migrate=False,
    )
    with patch(
        "ttd.cli.collect.collect_config_init",
        new=AsyncMock(return_value=collected),
    ):
        run_cli(["config", "init"])
    assert global_config_path().is_file()
    assert read_toml(global_config_path())["clock_format"] == "24h"


def test_config_init_non_tty_fails(config_home: Path, monkeypatch) -> None:
    monkeypatch.setattr("ttd.cli.interactive.stdin_is_tty", lambda: False)
    set_invocation_tokens(["config", "init"])
    with pytest.raises(SystemExit) as exc_info:
        app(["config", "init"])
    assert exc_info.value.code == 2
