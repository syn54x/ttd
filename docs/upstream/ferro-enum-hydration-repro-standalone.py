#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["ferro-orm==0.10.3"]  # use 0.10.3 to reproduce #65; >=0.10.5 passes
# ///
"""Standalone ferro-orm repro (no TTD). Cold fetch leaves text StrEnum as str."""

from __future__ import annotations

import asyncio
import tempfile
from enum import StrEnum
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from ferro import connect, reset_engine
from ferro.base import FerroField
from ferro.models import Model


class Mode(StrEnum):
    HOURLY = "hourly"


class Row(Model):
    id: Annotated[UUID | None, FerroField(primary_key=True)] = None
    name: str
    billing_mode: Annotated[Mode, FerroField(db_type="text")]


async def main() -> None:
    db = Path(tempfile.mkdtemp()) / "repro.db"
    dsn = f"sqlite:{db}?mode=rwc"
    await connect(dsn, auto_migrate=True)
    await Row.create(id=uuid4(), name="x", billing_mode=Mode.HOURLY)
    reset_engine()
    await connect(dsn, auto_migrate=True)

    loaded = (await Row.all())[0]
    print(f"billing_mode type: {type(loaded.billing_mode).__name__}")
    print(f"Row._enum_fields: {getattr(Row, '_enum_fields', {})}")
    if type(loaded.billing_mode) is str:
        raise SystemExit(
            f"FAIL: cold load returned str; _enum_fields={Row._enum_fields}"
        )
    if not isinstance(loaded.billing_mode, Mode):
        raise SystemExit(f"FAIL: expected Mode, got {type(loaded.billing_mode).__name__}")
    print("OK")


if __name__ == "__main__":
    asyncio.run(main())
