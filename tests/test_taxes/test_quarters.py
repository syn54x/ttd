"""IRS quarter boundaries and set-aside math invariants."""

from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ttd.core.errors import TtdError
from ttd.core.money import to_cents
from ttd.core.taxes import TaxQuarter, compute_set_aside, format_rate, quarters_of

TODAY = date(2026, 6, 11)


# --- boundaries ---------------------------------------------------------------


def test_quarter_windows_are_irs_not_calendar():
    q1, q2, q3, q4 = quarters_of(2026)
    assert (q1.start, q1.end) == (date(2026, 1, 1), date(2026, 3, 31))
    assert (q2.start, q2.end) == (date(2026, 4, 1), date(2026, 5, 31))  # two months
    assert (q3.start, q3.end) == (date(2026, 6, 1), date(2026, 8, 31))
    assert (q4.start, q4.end) == (date(2026, 9, 1), date(2026, 12, 31))  # four months


def test_from_date_boundaries():
    assert TaxQuarter.from_date(date(2026, 5, 31)) == TaxQuarter(2026, 2)
    assert TaxQuarter.from_date(date(2026, 6, 1)) == TaxQuarter(2026, 3)
    assert TaxQuarter.from_date(date(2026, 12, 31)) == TaxQuarter(2026, 4)
    assert TaxQuarter.from_date(date(2026, 1, 1)) == TaxQuarter(2026, 1)


def test_due_dates():
    assert TaxQuarter(2026, 1).due_date == date(2026, 4, 15)
    assert TaxQuarter(2026, 2).due_date == date(2026, 6, 15)
    assert TaxQuarter(2026, 3).due_date == date(2026, 9, 15)
    assert TaxQuarter(2026, 4).due_date == date(2027, 1, 15)  # next year


def test_invalid_quarter_rejected():
    with pytest.raises(TtdError, match="1-4"):
        TaxQuarter(2026, 5)


# --- parsing ------------------------------------------------------------------


def test_parse_full_and_short_forms():
    assert TaxQuarter.parse("2026q2", TODAY) == TaxQuarter(2026, 2)
    assert TaxQuarter.parse("2025Q4", TODAY) == TaxQuarter(2025, 4)
    assert TaxQuarter.parse("q3", TODAY) == TaxQuarter(2026, 3)  # current year
    assert TaxQuarter.parse(" Q1 ", TODAY) == TaxQuarter(2026, 1)


@pytest.mark.parametrize("bad", ["banana", "2026q5", "q0", "2026", "20q2x"])
def test_parse_garbage_rejected(bad):
    with pytest.raises(TtdError, match="2026q2"):
        TaxQuarter.parse(bad, TODAY)


def test_label_roundtrips_through_parse():
    q = TaxQuarter(2026, 4)
    assert TaxQuarter.parse(q.label, TODAY) == q


# --- properties ---------------------------------------------------------------


@given(st.dates(min_value=date(2000, 1, 1), max_value=date(2100, 12, 31)))
def test_quarters_tile_the_year(d):
    containing = [q for q in quarters_of(d.year) if q.start <= d <= q.end]
    assert len(containing) == 1
    assert TaxQuarter.from_date(d) == containing[0]


@given(
    st.decimals(min_value=0, max_value=10**7, places=2),
    st.decimals(min_value=0, max_value=1, places=4),
)
def test_set_aside_bounded_and_cent_aligned(subtotal, rate):
    set_aside = compute_set_aside(subtotal, rate)
    # subtotal is cent-aligned, so half-up rounding can never overshoot it
    assert Decimal("0") <= set_aside <= subtotal
    assert set_aside == to_cents(set_aside)


def test_format_rate():
    assert format_rate(Decimal("0.32")) == "32%"
    assert format_rate(Decimal("0.325")) == "32.5%"
    assert format_rate(Decimal("0")) == "0%"
