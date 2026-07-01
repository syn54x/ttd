# tests/test_reporting/test_periods.py
from datetime import date

import pytest

from ttd.core.errors import TtdError
from ttd.reporting import periods


def test_this_week_and_last_week():
    today = date(2026, 6, 18)  # a Thursday
    tw = periods.parse_period("this week", today)
    assert tw.start == date(2026, 6, 15) and tw.end == date(2026, 6, 21)  # Mon–Sun
    lw = periods.parse_period("last week", today)
    assert lw.start == date(2026, 6, 8) and lw.end == date(2026, 6, 14)


def test_rolling_last_n_ending_today():
    today = date(2026, 6, 18)
    ltw = periods.parse_period("last two weeks", today)
    assert ltw.start == date(2026, 6, 5)
    assert ltw.end == today
    assert periods.parse_period("last 10 days", today).start == date(2026, 6, 9)
    assert periods.parse_period("last 1 week", today).start == date(2026, 6, 12)
    assert periods.parse_period("last 3 months", today).start == date(2026, 3, 18)
    assert periods.parse_period("last 3 months", today).end == today


def test_rolling_month_clamps_day():
    # today Mar 31 minus 1 month clamps to Feb 28 (2026 not a leap year)
    assert periods.parse_period("last 1 month", date(2026, 3, 31)).start == date(2026, 2, 28)


def test_week_start_sunday():
    today = date(2026, 6, 18)
    tw = periods.parse_period("this week", today, week_start="sunday")
    assert tw.start == date(2026, 6, 14)  # Sunday


def test_month_name_range_closest_year():
    # today mid-2026
    today = date(2026, 7, 1)
    p = periods.parse_period("june 16 to june 30", today)
    assert p.start == date(2026, 6, 16) and p.end == date(2026, 6, 30)


def test_closest_year_examples():
    # Jan 1 2026, "dec 15 - dec 31" -> Dec 2025 (last year is closest)
    p = periods.parse_period("dec 15 - dec 31", date(2026, 1, 1))
    assert p.start == date(2025, 12, 15) and p.end == date(2025, 12, 31)
    # June 30 2026, "june 16 - june 30" -> this year (today inside)
    p = periods.parse_period("june 16 - june 30", date(2026, 6, 30))
    assert p.start == date(2026, 6, 16)
    # June 1 2026, "june 16 - june 30" -> this year (near future beats a year ago)
    p = periods.parse_period("june 16 - june 30", date(2026, 6, 1))
    assert p.start == date(2026, 6, 16)


def test_month_shorthands():
    today = date(2026, 7, 1)
    whole = periods.parse_period("june", today)
    assert whole.start == date(2026, 6, 1) and whole.end == date(2026, 6, 30)
    inherit = periods.parse_period("june 16 - 30", today)
    assert inherit.start == date(2026, 6, 16) and inherit.end == date(2026, 6, 30)
    abbrev = periods.parse_period("jun 16 to jun 30", today)
    assert abbrev.start == date(2026, 6, 16) and abbrev.end == date(2026, 6, 30)


def test_cross_year_wrap():
    # "dec 28 to jan 3" — end month wraps into the next year
    p = periods.parse_period("dec 28 to jan 3", date(2026, 1, 15))
    # closest-year for start Dec: Dec 2025 (ended ~2 weeks ago) beats Dec 2026
    assert p.start == date(2025, 12, 28) and p.end == date(2026, 1, 3)


def test_explicit_year_honored():
    p = periods.parse_period("june 16 to june 30 2024", date(2026, 7, 1))
    assert p.start == date(2024, 6, 16) and p.end == date(2024, 6, 30)


def test_bad_month_name_errors():
    with pytest.raises(TtdError):
        periods.parse_period("smarch 3 to smarch 9", date(2026, 7, 1))
