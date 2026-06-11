"""Property tests: the parser may reject, but must never crash or mis-resolve."""

from contextlib import suppress
from datetime import datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from ttd.core.errors import ParseError
from ttd.parsing.resolve import MAX_INTERVAL, resolve_entry
from ttd.parsing.tokens import tokenize

NOW = datetime(2026, 6, 9, 15, 0)


@given(st.text(max_size=40))
def test_tokenizer_never_crashes_unexpectedly(text):
    # rejection (ParseError) is fine; any other exception is a bug
    with suppress(ParseError):
        tokenize(text)


@given(st.text(alphabet="0123456789:- ampto/h", max_size=24))
def test_timey_garbage_never_crashes(text):
    with suppress(ParseError):
        resolve_entry(text, NOW)


@given(
    st.integers(min_value=0, max_value=23),
    st.integers(min_value=0, max_value=59),
    st.integers(min_value=1, max_value=14 * 60),
)
def test_explicit_24h_range_roundtrip(hour, minute, duration_min):
    """Unambiguous 24h start + duration resolves to exactly that interval."""
    start = datetime(2026, 6, 9, hour, minute)
    end = start + timedelta(minutes=duration_min)
    if end.date() != start.date():
        return  # cross-midnight unsupported by design
    if 10 <= hour <= 12:  # two digits but no leading zero: say am/pm explicitly
        clock = f"{hour}:{minute:02d}{'pm' if hour == 12 else 'am'}"
    else:
        clock = f"{hour:02d}:{minute:02d}"  # leading zero / >12: exact 24h form
    spec = f"today {clock} for {duration_min}m"
    r = resolve_entry(spec, NOW)
    assert r.started_at == start
    assert r.ended_at == end
    assert r.seconds == duration_min * 60
    assert timedelta(seconds=r.seconds) <= MAX_INTERVAL


@given(st.integers(min_value=1, max_value=14 * 60))
def test_bare_duration_roundtrip(minutes):
    r = resolve_entry(f"{minutes}m", NOW)
    assert r.seconds == minutes * 60
    assert r.started_at is None
