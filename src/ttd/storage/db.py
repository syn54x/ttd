"""Database lifecycle. One global Ferro engine per process."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from ferro import connect, reset_engine
from ferro.raw import execute, fetch_all

import ttd.storage.models  # noqa: F401  (register model metadata before connect)
from ttd.config.loader import get_settings
from ttd.config.schema import Settings

_initialized = False

# Ferro's auto_migrate creates missing tables but never alters existing ones,
# so nullable columns added to a model after first release are applied here.
# Column DDL must match what Ferro emits for a fresh database (see the model).
_COLUMN_ADDS: tuple[tuple[str, str, str], ...] = (
    ("invoice", "paid_date", "date_text"),
    ("invoice", "set_aside_rate", "real"),
    ("invoice", "set_aside", "real"),
)


async def _add_missing_columns() -> bool:
    added = False
    for table, column, ddl in _COLUMN_ADDS:
        rows = await fetch_all(f"PRAGMA table_info({table})")
        if column not in {row["name"] for row in rows}:
            await execute(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {ddl}')
            added = True
    return added


async def init_db(settings: Settings | None = None) -> None:
    global _initialized
    if _initialized:
        return
    cfg = settings or get_settings()
    cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
    await connect(cfg.db_dsn, auto_migrate=True)
    if await _add_missing_columns():
        # Pooled connections cache prepared-statement metadata from before the
        # ALTERs; reconnect so every connection sees the final schema.
        reset_engine()
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
