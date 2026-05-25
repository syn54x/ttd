from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from ttd.core.domain.hours import duration_from_interval, recompute_interval_snapshot

UTC = UTC


@given(
    minutes=st.integers(min_value=1, max_value=7 * 24 * 60),
)
def test_interval_hours_match_timedelta(minutes: int) -> None:
    start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    end = start + timedelta(minutes=minutes)
    expected = Decimal(minutes) / Decimal(60)
    assert duration_from_interval(start, end) == expected
    assert recompute_interval_snapshot(start, end) == expected


@given(
    extra_minutes=st.integers(min_value=1, max_value=480),
)
def test_longer_interval_never_decreases_hours(extra_minutes: int) -> None:
    start = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
    end_short = start + timedelta(hours=2)
    end_long = end_short + timedelta(minutes=extra_minutes)
    short_hours = duration_from_interval(start, end_short)
    long_hours = duration_from_interval(start, end_long)
    assert long_hours >= short_hours
