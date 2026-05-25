"""Smoke tests that ledger tables exist after init_db."""

from ferro import reset_engine

from ttd.core.db import init_db
from ttd.core.models.client import Client
from ttd.core.models.project import Project
from ttd.core.models.time_entry import TimeEntry


async def test_init_db_registers_ledger_models(db) -> None:
    clients = await Client.all()
    assert clients == []
    reset_engine()
    await init_db(db)
    assert Project.model_fields
    assert TimeEntry.model_fields
