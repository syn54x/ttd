from datetime import date
from decimal import Decimal
from uuid import uuid4

from hypothesis import given
from hypothesis import strategies as st

from ttd.config.schema import BillingConfig
from ttd.core.rollup import EntryFacts, amount, rollup_days, seconds_by_date
from ttd.core.rounding import round_seconds

P1, P2 = uuid4(), uuid4()
C1 = uuid4()
D1, D2 = date(2026, 6, 8), date(2026, 6, 9)


def fact(project=P1, day=D1, seconds=3600, billable=True, note=""):
    return EntryFacts(project, C1, day, seconds, billable, note)


# --- rounding ---------------------------------------------------------------


def test_rounding_modes_golden():
    cfg = lambda mode, inc=15: BillingConfig(rounding=mode, increment_minutes=inc)  # noqa: E731
    assert round_seconds(3500, cfg("none")) == 3500
    assert round_seconds(3500, cfg("up")) == 3600  # 58m20s → 1h
    assert round_seconds(3601, cfg("up")) == 4500  # 1h0m1s → 1h15
    assert round_seconds(3500, cfg("nearest")) == 3600
    assert round_seconds(3150, cfg("nearest")) == 3600  # 52m30s half rounds up
    assert round_seconds(3149, cfg("nearest")) == 2700  # 52m29s rounds down
    assert round_seconds(100, cfg("nearest", 6)) == 0  # under half an increment
    assert round_seconds(100, cfg("up", 6)) == 360


@given(st.integers(min_value=1, max_value=14 * 3600), st.sampled_from([6, 15, 30, 60]))
def test_rounding_up_properties(seconds, inc):
    cfg = BillingConfig(rounding="up", increment_minutes=inc)
    rounded = round_seconds(seconds, cfg)
    assert rounded >= seconds
    assert rounded % (inc * 60) == 0
    assert rounded - seconds < inc * 60


@given(
    st.integers(min_value=1, max_value=14 * 3600),
    st.integers(min_value=1, max_value=14 * 3600),
    st.sampled_from([6, 15, 30]),
)
def test_rounding_nearest_monotonic(a, b, inc):
    cfg = BillingConfig(rounding="nearest", increment_minutes=inc)
    lo, hi = sorted((a, b))
    assert round_seconds(lo, cfg) <= round_seconds(hi, cfg)
    assert abs(round_seconds(a, cfg) - a) <= inc * 60 // 2


# --- rollup -----------------------------------------------------------------


def test_rollup_groups_by_project_and_day():
    cells = rollup_days(
        [
            fact(P1, D1, 3600),
            fact(P1, D1, 1800, note="standup"),
            fact(P2, D1, 900),
            fact(P1, D2, 7200),
        ]
    )
    assert len(cells) == 3
    p1d1 = next(c for c in cells if c.project_id == P1 and c.work_date == D1)
    assert p1d1.seconds == 5400
    assert p1d1.entry_count == 2
    assert p1d1.notes == ["standup"]
    assert cells[0].work_date == D1 and cells[-1].work_date == D2


def test_rollup_separates_billable():
    cells = rollup_days([fact(seconds=3600), fact(seconds=1800, billable=False)])
    (cell,) = cells
    assert cell.seconds == 5400
    assert cell.billable_seconds == 3600


def test_billed_seconds_rounds_the_day_not_entries():
    # Two 50-minute entries: rounding per entry would give 2x1h; per day 1h45m
    cells = rollup_days([fact(seconds=50 * 60), fact(seconds=50 * 60)])
    cfg = BillingConfig(rounding="up", increment_minutes=15)
    assert cells[0].billed_seconds(cfg) == 105 * 60


def test_seconds_by_date():
    by = seconds_by_date([fact(day=D1, seconds=60), fact(day=D2, seconds=120), fact(day=D1)])
    assert by == {D1: 3660, D2: 120}


def test_amount():
    assert amount(3600, Decimal("150")) == Decimal("150")
    assert amount(5400, Decimal("100")) == Decimal("150")
    assert amount(3600, None) is None
