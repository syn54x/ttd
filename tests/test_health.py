import pytest

from ttd.core.config import Settings
from ttd.core.services import health


@pytest.mark.usefixtures("reset_db_state")
async def test_health_ping_returns_ok(settings: Settings) -> None:
    result = await health.ping(settings=settings)
    assert result["status"] == "ok"
    assert result["service"] == "ttd"
    assert result["db_path"] == str(settings.db_path)


@pytest.mark.usefixtures("reset_db_state")
async def test_init_db_is_idempotent(settings: Settings) -> None:
    from ttd.core.db import init_db

    await init_db(settings)
    await init_db(settings)
