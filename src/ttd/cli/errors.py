"""Map core exceptions to CLI exit codes."""

from __future__ import annotations

from ttd.cli.console import error as print_error
from ttd.core.exceptions import NotFoundError, TTDError, ValidationError


def cli_exit(exc: BaseException) -> None:
    if isinstance(exc, NotFoundError):
        print_error(str(exc))
        raise SystemExit(1) from exc
    if isinstance(exc, ValidationError):
        print_error(str(exc))
        raise SystemExit(2) from exc
    if isinstance(exc, TTDError):
        print_error(str(exc))
        raise SystemExit(1) from exc
    raise exc
