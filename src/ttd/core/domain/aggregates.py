"""Hour aggregates and soft-max status."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from ttd.core.models.time_entry import TimeEntry


class SoftMaxStatus(StrEnum):
    """Project hours relative to optional soft-max threshold."""

    UNSET = "unset"
    UNDER = "under"
    OVER = "over"


def sum_billable_hours(entries: list[TimeEntry]) -> Decimal:
    """Sum billable_hours for entries marked billable."""
    total = Decimal(0)
    for entry in entries:
        if entry.billable:
            total += entry.billable_hours
    return total


def soft_max_status(total_hours: Decimal, soft_max: Decimal | None) -> SoftMaxStatus:
    """Compare logged hours to optional project soft-max."""
    if soft_max is None:
        return SoftMaxStatus.UNSET
    if total_hours > soft_max:
        return SoftMaxStatus.OVER
    return SoftMaxStatus.UNDER
