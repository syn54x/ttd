from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

from ttd.config.schema import Settings, StorageConfig
from ttd.storage.db import close_db, init_db


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(storage=StorageConfig(db_path=tmp_path / "test.db"))


@pytest.fixture
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point global config + cwd + DB at tmp dirs so tests never touch real files."""
    config_dir = tmp_path / "config"
    cwd = tmp_path / "work" / "nested"
    cwd.mkdir(parents=True)
    monkeypatch.setenv("TTD_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("TTD_DB_PATH", str(tmp_path / "cli.db"))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.chdir(cwd)
    yield tmp_path


@pytest.fixture
async def db(settings: Settings) -> AsyncIterator[Settings]:
    await close_db()
    await init_db(settings)
    yield settings
    await close_db()
