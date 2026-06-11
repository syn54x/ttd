"""Database lifecycle. One global Ferro engine per process."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from ferro import connect, reset_engine

import ttd.storage.models  # noqa: F401  (register model metadata before connect)
from ttd.config.loader import get_settings
from ttd.config.schema import Settings

_initialized = False


async def init_db(settings: Settings | None = None) -> None:
    global _initialized
    if _initialized:
        return
    cfg = settings or get_settings()
    cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
    await connect(cfg.db_dsn, auto_migrate=True)
    _initialized = True


async def close_db() -> None:
    global _initialized
    if not _initialized:
        return
    reset_engine()
    _initialized = False


@asynccontextmanager
async def db_lifespan(settings: Settings | None = None) -> AsyncIterator[None]:
    await init_db(settings)
    try:
        yield
    finally:
        await close_db()
