from datetime import date

import pytest

from ttd.core.errors import TtdError
from ttd.reporting.periods import day_period, month_period, range_period, week_period

TUE = date(2026, 6, 9)


def test_week_monday_start():
    p = week_period(TUE, "monday")
    assert p.start == date(2026, 6, 8)
    assert p.end == date(2026, 6, 14)
    assert len(p.days()) == 7


def test_week_sunday_start():
    p = week_period(TUE, "sunday")
    assert p.start == date(2026, 6, 7)


def test_last_week():
    p = week_period(TUE, "monday", last=True)
    assert p.start == date(2026, 6, 1)
    assert p.end == date(2026, 6, 7)


def test_month_current_and_last():
    assert month_period(TUE).start == date(2026, 6, 1)
    assert month_period(TUE).end == date(2026, 6, 30)
    assert month_period(TUE, last=True).start == date(2026, 5, 1)
    assert month_period(TUE, last=True).end == date(2026, 5, 31)


def test_month_explicit_and_invalid():
    p = month_period(TUE, ym="2026-02")
    assert p.end == date(2026, 2, 28)
    with pytest.raises(TtdError, match="YYYY-MM"):
        month_period(TUE, ym="Feb")


def test_range_validates_order():
    p = range_period(date(2026, 6, 1), date(2026, 6, 9))
    assert len(p.days()) == 9
    with pytest.raises(TtdError):
        range_period(date(2026, 6, 9), date(2026, 6, 1))


def test_day_period():
    assert day_period(TUE).days() == [TUE]


def test_parse_period():
    from ttd.reporting.periods import parse_period

    assert parse_period("", TUE).start == date(2026, 5, 1)  # blank = last month
    assert parse_period("last month", TUE).end == date(2026, 5, 31)
    assert parse_period("This Month", TUE).start == date(2026, 6, 1)
    assert parse_period("2026-04", TUE).start == date(2026, 4, 1)
    p = parse_period("2026-05-01 to 2026-05-15", TUE)
    assert (p.start, p.end) == (date(2026, 5, 1), date(2026, 5, 15))
    assert parse_period("2026-05-01..2026-05-15", TUE).end == date(2026, 5, 15)


def test_parse_period_rejects():
    from ttd.reporting.periods import parse_period

    for bad in ("banana", "2026-13", "2026-05-15 to 2026-05-01", "2026-02-30 to 2026-03-01"):
        with pytest.raises(TtdError):
            parse_period(bad, TUE)
