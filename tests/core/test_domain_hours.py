from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ttd.core.domain.hours import duration_from_interval, recompute_interval_snapshot
from ttd.core.exceptions import ValidationError

UTC = UTC


def test_duration_from_interval_same_day() -> None:
    start = datetime(2026, 5, 1, 9, 0, tzinfo=UTC)
    end = datetime(2026, 5, 1, 12, 30, tzinfo=UTC)
    assert duration_from_interval(start, end) == Decimal("3.5")


def test_duration_from_interval_overnight() -> None:
    start = datetime(2026, 5, 1, 22, 0, tzinfo=UTC)
    end = datetime(2026, 5, 2, 2, 0, tzinfo=UTC)
    assert duration_from_interval(start, end) == Decimal("4")


def test_recompute_matches_duration() -> None:
    start = datetime(2026, 5, 1, 9, 0, tzinfo=UTC)
    end = start + timedelta(hours=2, minutes=15)
    assert recompute_interval_snapshot(start, end) == duration_from_interval(start, end)


def test_end_before_start_raises() -> None:
    start = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    end = datetime(2026, 5, 1, 9, 0, tzinfo=UTC)
    with pytest.raises(ValidationError, match="ended_at"):
        duration_from_interval(start, end)


def test_naive_datetime_raises() -> None:
    start = datetime(2026, 5, 1, 9, 0)
    end = datetime(2026, 5, 1, 10, 0, tzinfo=UTC)
    with pytest.raises(ValidationError, match="timezone-aware"):
        duration_from_interval(start, end)
