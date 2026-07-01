"""Database lifecycle. One global Ferro engine per process."""

import functools
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from ferro import connect, engines, reset_engine

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
    await connect(cfg.db_dsn, migrate_updates=True)
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
        async with engines.session():
            yield
    finally:
        await close_db()


@asynccontextmanager
async def db_session() -> AsyncIterator[None]:
    """Open a Ferro session for ORM/raw work (safe to nest under db_lifespan)."""
    async with engines.session():
        yield


def in_db_session[**P, R](fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """Ensure each service entrypoint runs inside a Ferro session."""

    @functools.wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        async with engines.session():
            return await fn(*args, **kwargs)

    return wrapper
