import pytest

from ttd.core.config import Settings
from ttd.core.db import close_db


@pytest.fixture
async def reset_db_state() -> None:
    await close_db()
    yield
    await close_db()


@pytest.fixture
def settings(tmp_path) -> Settings:
    data_dir = tmp_path / "ttd-data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return Settings(data_dir=data_dir, db_filename="test.db")
