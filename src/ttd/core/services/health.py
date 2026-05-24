from typing import Any

from ttd.core.config import Settings, get_settings
from ttd.core.db import init_db


async def ping(settings: Settings | None = None) -> dict[str, Any]:
    cfg = settings or get_settings()
    await init_db(cfg)
    return {
        "status": "ok",
        "service": "ttd",
        "db_path": str(cfg.db_path),
    }
