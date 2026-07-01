# tests/test_reporting/test_periods.py
from datetime import date

from ttd.reporting import periods


def test_this_week_and_last_week():
    today = date(2026, 6, 18)  # a Thursday
    tw = periods.parse_period("this week", today)
    assert tw.start == date(2026, 6, 15) and tw.end == date(2026, 6, 21)  # Mon–Sun
    lw = periods.parse_period("last week", today)
    assert lw.start == date(2026, 6, 8) and lw.end == date(2026, 6, 14)


def test_rolling_last_n_ending_today():
    today = date(2026, 6, 18)
    assert periods.parse_period("last two weeks", today).start == date(2026, 6, 5)
    assert periods.parse_period("last two weeks", today).end == today
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
