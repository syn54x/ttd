from __future__ import annotations

import pytest

from ttd.core.seed.demo_data import MARKER_CLIENT_NAME
from ttd.core.seed.runner import is_demo_seeded, seed_database
from ttd.core.services import clients as client_service


@pytest.mark.asyncio
async def test_seed_populates_demo_ledger(db) -> None:
    summary = await seed_database()
    assert summary.skipped is False
    assert summary.clients == 2
    assert summary.projects == 4
    assert summary.entries == 8
    assert await is_demo_seeded() is True
    names = {c.name for c in await client_service.list_clients()}
    assert MARKER_CLIENT_NAME in names


@pytest.mark.asyncio
async def test_seed_skips_when_already_present(db) -> None:
    await seed_database()
    summary = await seed_database()
    assert summary.skipped is True
    assert summary.clients == 0


@pytest.mark.asyncio
async def test_seed_force_replaces_demo_data(db) -> None:
    await seed_database()
    summary = await seed_database(force=True)
    assert summary.skipped is False
    assert summary.clients == 2
