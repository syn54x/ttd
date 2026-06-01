from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError as PydanticValidationError

from ttd.core.config import (
    CONFIG_KEYS,
    Settings,
    clear_settings_cache,
    config_file_has_settings,
    get_config_value,
    get_settings,
    init_config,
    resolve_sources,
    set_config_value,
)
from ttd.core.config_files import (
    CONFIG_FILENAME,
    find_local_config,
    global_config_path,
    local_config_write_path,
    read_toml,
    update_config_file,
    write_toml,
)
from ttd.core.db_admin import describe_db
from ttd.core.exceptions import ValidationError


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
    for key in CONFIG_KEYS:
        monkeypatch.delenv(f"TTD_{key.upper()}", raising=False)
    return xdg


def test_global_config_path_respects_xdg(config_home: Path) -> None:
    assert global_config_path() == config_home / "ttd" / CONFIG_FILENAME


def test_find_local_config_in_cwd(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert find_local_config() is None
    (tmp_path / CONFIG_FILENAME).write_text('data_dir = "/local"\n')
    assert find_local_config() == tmp_path / CONFIG_FILENAME


def test_find_local_config_in_parent(tmp_path: Path, monkeypatch) -> None:
    parent = tmp_path / "repo"
    child = parent / "src"
    child.mkdir(parents=True)
    (parent / CONFIG_FILENAME).write_text('data_dir = "/parent"\n')
    monkeypatch.chdir(child)
    assert find_local_config() == parent / CONFIG_FILENAME


def test_local_config_write_path_creates_in_cwd(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert local_config_write_path() == tmp_path / CONFIG_FILENAME


def test_local_config_write_path_uses_existing(tmp_path: Path, monkeypatch) -> None:
    parent = tmp_path / "repo"
    child = parent / "src"
    child.mkdir(parents=True)
    config_file = parent / CONFIG_FILENAME
    config_file.write_text('data_dir = "/parent"\n')
    monkeypatch.chdir(child)
    assert local_config_write_path() == config_file


def test_toml_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "ttd.toml"
    write_toml(path, {"data_dir": "/data", "clock_format": "24h"})
    assert read_toml(path) == {"data_dir": "/data", "clock_format": "24h"}


def test_update_config_preserves_other_keys(tmp_path: Path) -> None:
    path = tmp_path / "ttd.toml"
    write_toml(path, {"data_dir": "/data", "clock_format": "24h"})
    update_config_file(path, "db_filename", "custom.db")
    assert read_toml(path) == {
        "data_dir": "/data",
        "clock_format": "24h",
        "db_filename": "custom.db",
    }


def test_local_overrides_global(config_home: Path, tmp_path: Path, monkeypatch) -> None:
    global_path = global_config_path()
    write_toml(global_path, {"data_dir": "/global"})
    local_path = tmp_path / CONFIG_FILENAME
    write_toml(local_path, {"data_dir": "./local"})
    monkeypatch.chdir(tmp_path)
    settings = get_settings()
    assert settings.data_dir == (tmp_path / "local").resolve()


def test_env_overrides_toml(config_home: Path, tmp_path: Path, monkeypatch) -> None:
    write_toml(global_config_path(), {"data_dir": "/global"})
    write_toml(tmp_path / CONFIG_FILENAME, {"data_dir": "./local"})
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TTD_DATA_DIR", "/env")
    settings = get_settings()
    assert settings.data_dir == Path("/env").resolve()


def test_resolve_sources(config_home: Path, tmp_path: Path, monkeypatch) -> None:
    write_toml(global_config_path(), {"db_filename": "global.db"})
    write_toml(tmp_path / CONFIG_FILENAME, {"clock_format": "12h"})
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TTD_DATA_DIR", str(tmp_path / "env-data"))
    sources = resolve_sources()
    assert sources["data_dir"] == "env"
    assert sources["clock_format"] == "local"
    assert sources["db_filename"] == "global"


def test_missing_files_use_defaults(
    config_home: Path, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = get_settings()
    assert settings.db_filename == "ttd.db"
    assert settings.clock_format == "24h"


def test_legacy_timezone_key_ignored(
    config_home: Path, tmp_path: Path, monkeypatch
) -> None:
    write_toml(tmp_path / CONFIG_FILENAME, {"timezone": "America/Chicago"})
    monkeypatch.chdir(tmp_path)
    get_settings()
    assert "timezone" not in Settings.model_fields


def test_invalid_clock_format_rejected(
    config_home: Path, tmp_path: Path, monkeypatch
) -> None:
    write_toml(tmp_path / CONFIG_FILENAME, {"clock_format": "48h"})
    monkeypatch.chdir(tmp_path)
    with pytest.raises(PydanticValidationError):
        get_settings()


def test_set_config_global_creates_file(config_home: Path) -> None:
    path = set_config_value("data_dir", "/var/ttd", global_=True)
    assert path == global_config_path()
    assert path.is_file()
    assert get_config_value("data_dir") == str(Path("/var/ttd").resolve())


def test_set_config_clock_format(
    config_home: Path, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    set_config_value("clock_format", "12h")
    data = read_toml(tmp_path / CONFIG_FILENAME)
    assert data["clock_format"] == "12h"
    assert get_config_value("clock_format") == "12h"


def test_set_unknown_key_raises() -> None:
    with pytest.raises(ValidationError, match="Unknown config key"):
        set_config_value("not_a_key", "x")


def test_set_unknown_timezone_key_raises() -> None:
    with pytest.raises(ValidationError, match="Unknown config key"):
        set_config_value("timezone", "UTC")


def test_describe_db_uses_toml_data_dir(
    config_home: Path, tmp_path: Path, monkeypatch
) -> None:
    data_dir = tmp_path / "ledger-data"
    write_toml(global_config_path(), {"data_dir": str(data_dir)})
    monkeypatch.chdir(tmp_path)
    location = describe_db(get_settings())
    assert location.data_dir == data_dir.resolve()


def test_init_config_writes_global_file(config_home: Path) -> None:
    path = init_config(
        data_dir="/var/ttd-data",
        db_filename="ledger.db",
        clock_format="24h",
        global_=True,
        create_data_dir=False,
    )
    assert path == global_config_path()
    data = read_toml(path)
    assert data == {
        "data_dir": str(Path("/var/ttd-data").resolve()),
        "db_filename": "ledger.db",
        "clock_format": "24h",
    }
    assert get_config_value("db_filename") == "ledger.db"


def test_init_config_creates_data_dir(config_home: Path, tmp_path: Path) -> None:
    data_dir = tmp_path / "new-data"
    init_config(
        data_dir=str(data_dir),
        db_filename="ttd.db",
        clock_format="12h",
        global_=True,
        create_data_dir=True,
    )
    assert data_dir.is_dir()


def test_config_file_has_settings(config_home: Path) -> None:
    path = global_config_path()
    assert not config_file_has_settings(path)
    write_toml(path, {"clock_format": "12h"})
    assert config_file_has_settings(path)
