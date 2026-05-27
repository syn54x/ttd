"""Tests for core database admin helpers."""

from __future__ import annotations

import pytest

from ttd.core import db_admin
from ttd.core.db import close_db
from ttd.core.exceptions import ValidationError


@pytest.mark.asyncio
async def test_describe_db_without_connect(settings) -> None:
    location = db_admin.describe_db(settings)
    assert location.db_path == settings.db_path
    assert location.data_dir == settings.data_dir
    assert location.exists is False


@pytest.mark.asyncio
async def test_reset_requires_confirmation(settings, reset_db_state) -> None:
    with pytest.raises(ValidationError, match="--yes"):
        await db_admin.reset_database(settings, confirmed=False)


@pytest.mark.asyncio
async def test_apply_schema_creates_file(settings, reset_db_state) -> None:
    await close_db()
    location = await db_admin.apply_schema(settings)
    assert location.exists
    assert settings.db_path.is_file()
