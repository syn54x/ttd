"""Interactive CLI mode detection and invocation token tracking."""

from __future__ import annotations

import sys
from collections.abc import Iterable, Mapping, Sequence
from enum import Enum
from typing import Any

from ttd.core.exceptions import ValidationError

_invocation_tokens: list[str] = []


def set_invocation_tokens(tokens: Iterable[str]) -> None:
    global _invocation_tokens
    _invocation_tokens = list(tokens)


def invocation_tokens() -> list[str]:
    return list(_invocation_tokens)


def is_bare_subcommand(subcommand: Sequence[str]) -> bool:
    """True when argv is exactly the subcommand path with no flags or positionals."""
    tokens = _invocation_tokens
    path = list(subcommand)
    return tokens == path


class RunMode(Enum):
    RUN = "run"
    INTERACTIVE = "interactive"
    ERROR = "error"


def stdin_is_tty() -> bool:
    return sys.stdin.isatty()


def require_interactive_tty() -> None:
    if not stdin_is_tty():
        raise ValidationError(
            "Interactive mode requires a terminal (stdin is not a TTY)."
        )


def resolve_run_mode(
    *,
    subcommand: Sequence[str],
    interactive_flag: bool,
    provided: Mapping[str, Any],
    required_for_run: Sequence[str],
) -> tuple[RunMode, list[str]]:
    """Decide whether to run, prompt, or error from flags and provided values."""
    wants_interactive = interactive_flag or is_bare_subcommand(subcommand)
    missing = [key for key in required_for_run if provided.get(key) is None]

    if wants_interactive:
        if not stdin_is_tty():
            require_interactive_tty()
        if not missing and not is_bare_subcommand(subcommand):
            return RunMode.RUN, []
        return RunMode.INTERACTIVE, missing

    if missing:
        return RunMode.ERROR, missing
    return RunMode.RUN, []


def format_missing_fields(missing: Sequence[str]) -> str:
    labels = ", ".join(f"--{name.replace('_', '-')}" for name in missing)
    return (
        f"Missing required option(s): {labels}. "
        "Use -i to prompt, or pass all required flags."
    )
