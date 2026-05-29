"""Sort helpers for CLI table list commands."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from ttd.core.exceptions import ValidationError
from ttd.core.models.client import Client
from ttd.core.models.enums import enum_value
from ttd.core.models.project import Project
from ttd.core.models.time_entry import TimeEntry

SortKey = Callable[..., Any]


def parse_sort(
    value: str | None,
    *,
    allowed: dict[str, SortKey],
    default: str,
) -> tuple[str, bool]:
    """Return ``(field, reverse)`` from a CLI sort value."""
    spec = value if value is not None else default
    reverse = spec.startswith("-")
    field = spec[1:] if reverse else spec
    if field not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ValidationError(
            f"Invalid sort field '{field}'; choose from: {choices} "
            "(prefix with '-' for descending)"
        )
    return field, reverse


def sort_items[T](
    items: Sequence[T],
    *,
    allowed: dict[str, Callable[[T], Any]],
    sort: str | None,
    default: str,
) -> list[T]:
    field, reverse = parse_sort(sort, allowed=allowed, default=default)
    return sorted(items, key=allowed[field], reverse=reverse)


CLIENT_SORTS: dict[str, Callable[[Client], Any]] = {
    "id": lambda c: c.id or "",
    "name": lambda c: c.name.casefold(),
    "rate": lambda c: (c.default_hourly_rate, c.name.casefold()),
    "currency": lambda c: (c.currency, c.name.casefold()),
}

PROJECT_SORTS: dict[str, Callable[[Project], Any]] = {
    "id": lambda p: p.id or "",
    "client": lambda p: p.client_id,
    "name": lambda p: p.name.casefold(),
    "mode": lambda p: (enum_value(p.billing_mode), p.name.casefold()),
}

ENTRY_SORTS: dict[str, Callable[[TimeEntry], Any]] = {
    "id": lambda e: e.id or "",
    "project": lambda e: e.project_id,
    "date": lambda e: (e.work_date, e.id or ""),
    "hours": lambda e: (e.billable_hours, e.work_date, e.id or ""),
    "billable": lambda e: (e.billable, e.work_date, e.id or ""),
}
