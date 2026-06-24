# /// script
# requires-python = ">=3.13"
# dependencies = ["ferro-orm==0.12.2"]
# ///
"""Regression: Model.get_or_none() and Model.delete() on ferro-orm ≥ 0.12.2.

Fixed in 0.12.2 (ferro-orm#121): built-in helpers no longer emit operator-predicate
DeprecationWarning.

Run:
  uv run docs/upstream/ferro-v012-get-or-none-delete-operator-predicate-repro-standalone.py

Expected: no DeprecationWarning from framework helpers consumers did not write.
Actual: DeprecationWarning on get_or_none (and delete uses the same pattern).
"""

import asyncio
import tempfile
import warnings
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from ferro import FerroField, connect, engines
from ferro.models import Model


class Widget(Model):
    id: Annotated[UUID | None, FerroField(primary_key=True)] = None
    name: str


async def main() -> None:
    db = Path(tempfile.mktemp(suffix=".db"))
    await connect(f"sqlite:{db}?mode=rwc", auto_migrate=True)
    async with engines.session():
        widget = Widget(id=uuid4(), name="demo")
        await widget.save()

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            loaded = await Widget.get_or_none(widget.id)
            assert loaded is not None
            await loaded.delete()

        predicate_warnings = [
            w
            for w in caught
            if issubclass(w.category, DeprecationWarning)
            and "Operator predicate style" in str(w.message)
        ]
        if predicate_warnings:
            for w in predicate_warnings:
                print(f"WARN: {w.filename}:{w.lineno}: {w.message}")
            raise SystemExit(1)
        print("ok: no operator-predicate deprecation warnings")


asyncio.run(main())
