"""Sync terminal prompts (questionary) invoked from async CLI handlers."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any, TypeVar

import questionary
from questionary import Choice

T = TypeVar("T")


async def to_thread(fn: Any, /) -> Any:
    return await asyncio.to_thread(fn)


async def ask_text(message: str, *, default: str = "") -> str:
    def _run() -> str:
        answer = questionary.text(message, default=default).unsafe_ask()
        if answer is None:
            raise KeyboardInterrupt
        return answer.strip()

    return str(await to_thread(_run))


async def ask_confirm(message: str, *, default: bool = False) -> bool:
    def _run() -> bool:
        answer = questionary.confirm(message, default=default).unsafe_ask()
        if answer is None:
            raise KeyboardInterrupt
        return bool(answer)

    return bool(await to_thread(_run))


async def ask_select[T](message: str, choices: Sequence[tuple[str, T]]) -> T:
    if not choices:
        raise ValueError("ask_select requires at least one choice")

    def _run() -> T:
        picked = questionary.select(
            message,
            choices=[Choice(title=label, value=value) for label, value in choices],
        ).unsafe_ask()
        if picked is None:
            raise KeyboardInterrupt
        return picked

    return await to_thread(_run)


async def ask_checkbox(message: str, choices: Sequence[tuple[str, str]]) -> list[str]:
    """Return selected field keys (choice values)."""

    def _run() -> list[str]:
        picked = questionary.checkbox(
            message,
            choices=[Choice(title=label, value=key) for label, key in choices],
        ).unsafe_ask()
        if picked is None:
            raise KeyboardInterrupt
        return list(picked)

    return await to_thread(_run)
