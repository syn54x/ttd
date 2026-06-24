# /// script
# requires-python = ">=3.13"
# dependencies = ["ferro-orm==0.12.2"]
# ///
"""Regression: cross-context Session teardown on ferro-orm ≥ 0.12.2.

Fixed in 0.12.2 (ferro-orm#123): __aexit__ succeeds when enter/exit run in different
asyncio contexts (e.g. GUI mount vs unmount).

Run:
  uv run docs/upstream/ferro-v012-session-cross-context-teardown-repro-standalone.py

Expected: session teardown succeeds (or documents a supported cross-task pattern).
Actual: ValueError on ContextVar.reset during __aexit__.
"""

import asyncio
import tempfile
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from ferro import FerroField, connect, engines
from ferro.models import Model


class Widget(Model):
    id: Annotated[UUID | None, FerroField(primary_key=True)] = None
    name: str


async def open_session() -> AsyncExitStack:
    stack = AsyncExitStack()
    await stack.__aenter__()
    await stack.enter_async_context(engines.session())
    widget = Widget(id=uuid4(), name="demo")
    await widget.save()
    return stack


async def close_session(stack: AsyncExitStack) -> None:
    await stack.__aexit__(None, None, None)


async def main() -> None:
    db = Path(tempfile.mktemp(suffix=".db"))
    await connect(f"sqlite:{db}?mode=rwc", auto_migrate=True)

    stack = await open_session()
    # Different task/context than open_session — mirrors GUI mount vs unmount.
    await asyncio.create_task(close_session(stack))
    print("ok: session closed across asyncio contexts")


asyncio.run(main())
