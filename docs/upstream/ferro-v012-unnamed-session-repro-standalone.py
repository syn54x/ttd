# /// script
# requires-python = ">=3.13"
# dependencies = ["ferro-orm==0.12.2"]
# ///
"""Regression: unnamed engines.session() on ferro-orm ≥ 0.12.2.

Fixed in 0.12.2 (ferro-orm#122): session() with no name binds to the default connection.

Run:
  uv run docs/upstream/ferro-v012-unnamed-session-repro-standalone.py

Expected: unnamed session() routes to the default connection without warning.
Actual: connection_name=None and DeprecationWarning on queries inside the block.
"""

import asyncio
import tempfile
import warnings
from pathlib import Path
from typing import Annotated
from uuid import UUID

from ferro import FerroField, connect, engines
from ferro.models import Model


class Widget(Model):
    id: Annotated[UUID | None, FerroField(primary_key=True)] = None
    name: str


async def main() -> None:
    db = Path(tempfile.mktemp(suffix=".db"))
    await connect(f"sqlite:{db}?mode=rwc", auto_migrate=True)

    async with engines.session() as session:
        print(f"connection_name={session.connection_name!r}")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            await Widget.where(lambda w: w.name == "missing").exists()

        session_warnings = [
            w
            for w in caught
            if issubclass(w.category, DeprecationWarning)
            and "without an active session" in str(w.message)
        ]
        if session.connection_name is not None and not session_warnings:
            print("ok: unnamed session bound to a connection and queries are clean")
            return
        if session_warnings:
            for w in session_warnings:
                print(f"WARN: {w.filename}:{w.lineno}: {w.message}")
        raise SystemExit(1)


asyncio.run(main())
