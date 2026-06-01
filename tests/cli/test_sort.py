"""CLI list sort options."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from ttd.cli.sort import ENTRY_SORTS, sort_items
from ttd.core.exceptions import ValidationError
from ttd.core.models.enums import EntryMode
from ttd.core.models.time_entry import TimeEntry


def _entry(work_date: date, hours: str) -> TimeEntry:
    return TimeEntry(
        project_id="00000000-0000-0000-0000-000000000001",
        work_date=work_date,
        entry_mode=EntryMode.DURATION,
        billable_hours=Decimal(hours),
    )


def test_sort_items_default_entries_newest_first() -> None:
    entries = [
        _entry(date(2026, 5, 1), "1"),
        _entry(date(2026, 5, 20), "2"),
        _entry(date(2026, 5, 10), "3"),
    ]
    ordered = sort_items(entries, allowed=ENTRY_SORTS, sort=None, default="-date")
    assert [e.work_date for e in ordered] == [
        date(2026, 5, 20),
        date(2026, 5, 10),
        date(2026, 5, 1),
    ]


def test_sort_items_explicit_ascending_date() -> None:
    entries = [
        _entry(date(2026, 5, 20), "2"),
        _entry(date(2026, 5, 1), "1"),
    ]
    ordered = sort_items(entries, allowed=ENTRY_SORTS, sort="date", default="-date")
    assert [e.work_date for e in ordered] == [date(2026, 5, 1), date(2026, 5, 20)]


def test_sort_items_invalid_field() -> None:
    with pytest.raises(ValidationError, match="Invalid sort field"):
        sort_items([], allowed=ENTRY_SORTS, sort="note", default="-date")
