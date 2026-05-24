from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from ferro import connect, reset_engine

from ttd.core.config import Settings, get_settings

_db_initialized = False


async def init_db(settings: Settings | None = None) -> None:
    global _db_initialized
    if _db_initialized:
        return
    cfg = settings or get_settings()
    cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
    await connect(cfg.db_dsn, auto_migrate=True)
    _db_initialized = True


async def close_db() -> None:
    global _db_initialized
    if not _db_initialized:
        return
    reset_engine()
    _db_initialized = False
    _db_initialized = False


@asynccontextmanager
async def db_lifespan(settings: Settings | None = None) -> AsyncIterator[None]:
    await init_db(settings)
    try:
        yield
    finally:
        await close_db()
