"""Error handling and DB lifespan for Cyclopts commands.

Services are async (Ferro); commands are native async and Cyclopts runs them.
TtdApp translates any TtdError — raised sync or async — into a red message
and exit code 1.
"""

import functools
import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from cyclopts import App

from ttd.cli._output import error
from ttd.core.errors import TtdError
from ttd.storage.db import db_lifespan


class TtdApp(App):
    """Cyclopts app whose commands surface TtdError as a clean CLI error."""

    def command(self, obj: Any = None, name: Any = None, **kwargs: Any) -> Any:
        if obj is None:  # bare @app.command(name=...) form
            return lambda fn: self.command(fn, name=name, **kwargs)
        if isinstance(obj, App):  # sub-app registration
            return super().command(obj, name=name, **kwargs)

        if inspect.iscoroutinefunction(obj):

            @functools.wraps(obj)
            async def wrapper(*a: Any, **kw: Any) -> Any:
                try:
                    return await obj(*a, **kw)
                except TtdError as exc:
                    error(str(exc))
                    raise SystemExit(1) from exc
        else:

            @functools.wraps(obj)
            def wrapper(*a: Any, **kw: Any) -> Any:
                try:
                    return obj(*a, **kw)
                except TtdError as exc:
                    error(str(exc))
                    raise SystemExit(1) from exc

        return super().command(wrapper, name=name, **kwargs)


def with_db[**P, T](fn: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
    """Open the DB for the duration of an async command."""

    @functools.wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        async with db_lifespan():
            return await fn(*args, **kwargs)

    return wrapper


def abort() -> None:
    """User cancel: print 'Aborted.' and exit 1."""
    print("Aborted.")
    raise SystemExit(1)
