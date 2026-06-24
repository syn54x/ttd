"""Ferro session helper for TUI pilot tests."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from ferro import engines

from ttd.config.schema import Settings
from ttd.storage.db import close_db, init_db


@asynccontextmanager
async def open_test_db(settings: Settings | None = None) -> AsyncIterator[None]:
    """Connect, run work inside a Ferro session, then tear down."""
    await close_db()
    await init_db(settings)
    try:
        async with engines.session():
            yield
    finally:
        await close_db()
