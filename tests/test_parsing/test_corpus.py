"""Table-driven corpus for the NL time parser.

NOW is frozen at Tue 2026-06-09 15:00 local; workday window is the default 7-19.
Each case: (spec, expected work_date, expected start 'HH:MM' or None,
expected end or None, expected seconds).
"""

from datetime import date, datetime, time

import pytest

from ttd.core.errors import AmbiguousTimeError, ParseError
from ttd.parsing.resolve import resolve_entry, resolve_point

NOW = datetime(2026, 6, 9, 15, 0)  # Tuesday afternoon
H = 3600

CORPUS = [
    # The must-handle examples from the design
    ("today 8am to 5pm", date(2026, 6, 9), "08:00", "17:00", 9 * H),
    ("yesterday 9-11:30", date(2026, 6, 8), "09:00", "11:30", int(2.5 * H)),
    ("2h this morning", date(2026, 6, 9), None, None, 2 * H),
    ("monday 1pm for 3 hours", date(2026, 6, 8), "13:00", "16:00", 3 * H),
    ("8 to 5", date(2026, 6, 9), "08:00", "17:00", 9 * H),
    ("9:15-12", date(2026, 6, 9), "09:15", "12:00", int(2.75 * H)),
    ("last friday 2h", date(2026, 6, 5), None, None, 2 * H),
    ("45m", date(2026, 6, 9), None, None, 45 * 60),
    ("6/3 10am-1pm", date(2026, 6, 3), "10:00", "13:00", 3 * H),
    ("from 1 till 3:30", date(2026, 6, 9), "13:00", "15:30", int(2.5 * H)),
    ("tonight 9 to 11", date(2026, 6, 9), "21:00", "23:00", 2 * H),
    # Ranges: connectives, hyphens, mixed meridiems
    ("9am to 5pm", date(2026, 6, 9), "09:00", "17:00", 8 * H),
    ("9 until 5", date(2026, 6, 9), "09:00", "17:00", 8 * H),
    ("9 thru 5", date(2026, 6, 9), "09:00", "17:00", 8 * H),
    ("9-5", date(2026, 6, 9), "09:00", "17:00", 8 * H),
    ("10am-1pm", date(2026, 6, 9), "10:00", "13:00", 3 * H),
    ("10:15am-1:45pm", date(2026, 6, 9), "10:15", "13:45", int(3.5 * H)),
    ("8:30 to 12", date(2026, 6, 9), "08:30", "12:00", int(3.5 * H)),
    ("13:00 to 17:00", date(2026, 6, 9), "13:00", "17:00", 4 * H),
    ("noon to 5", date(2026, 6, 9), "12:00", "17:00", 5 * H),
    ("9 to noon", date(2026, 6, 9), "09:00", "12:00", 3 * H),
    ("from 9 to 5", date(2026, 6, 9), "09:00", "17:00", 8 * H),
    ("9:15 - 12", date(2026, 6, 9), "09:15", "12:00", int(2.75 * H)),
    # One endpoint anchors the other
    ("9:15-12pm", date(2026, 6, 9), "09:15", "12:00", int(2.75 * H)),
    ("8am to 5", date(2026, 6, 9), "08:00", "17:00", 9 * H),
    # Timed durations
    ("at 1pm for 3 hours", date(2026, 6, 9), "13:00", "16:00", 3 * H),
    ("1pm for 3h", date(2026, 6, 9), "13:00", "16:00", 3 * H),
    ("2h at 9am", date(2026, 6, 9), "09:00", "11:00", 2 * H),
    ("for 90m at 10", date(2026, 6, 9), "10:00", "11:30", int(1.5 * H)),
    ("9 for 2 hours", date(2026, 6, 9), "09:00", "11:00", 2 * H),
    # Bare durations
    ("2h", date(2026, 6, 9), None, None, 2 * H),
    ("3 hours", date(2026, 6, 9), None, None, 3 * H),
    ("1h30m", date(2026, 6, 9), None, None, int(1.5 * H)),
    ("1h 30m", date(2026, 6, 9), None, None, int(1.5 * H)),
    ("1.5h", date(2026, 6, 9), None, None, int(1.5 * H)),
    ("90 minutes", date(2026, 6, 9), None, None, int(1.5 * H)),
    ("45 min", date(2026, 6, 9), None, None, 45 * 60),
    # Date anchors in both positions
    ("yesterday 2h", date(2026, 6, 8), None, None, 2 * H),
    ("2h yesterday", date(2026, 6, 8), None, None, 2 * H),
    ("9-5 yesterday", date(2026, 6, 8), "09:00", "17:00", 8 * H),
    ("on monday 9 to 5", date(2026, 6, 8), "09:00", "17:00", 8 * H),
    ("fri 1h", date(2026, 6, 5), None, None, H),
    ("tuesday 1h", date(2026, 6, 9), None, None, H),  # today is Tuesday
    ("last tuesday 1h", date(2026, 6, 2), None, None, H),
    ("sunday 2h", date(2026, 6, 7), None, None, 2 * H),
    ("2026-06-01 9 to 5", date(2026, 6, 1), "09:00", "17:00", 8 * H),
    ("6/3/2026 2h", date(2026, 6, 3), None, None, 2 * H),
    # Part-of-day biases am/pm
    ("this morning 9 to 11", date(2026, 6, 9), "09:00", "11:00", 2 * H),
    ("this afternoon 1 to 3", date(2026, 6, 9), "13:00", "15:00", 2 * H),
    ("this evening 6 to 8", date(2026, 6, 9), "18:00", "20:00", 2 * H),
    ("yesterday evening 7 to 9", date(2026, 6, 8), "19:00", "21:00", 2 * H),
    ("3h this afternoon", date(2026, 6, 9), None, None, 3 * H),
    # Window inference picks the working-hours candidate
    ("from 1 to 3", date(2026, 6, 9), "13:00", "15:00", 2 * H),
    ("8:15 to 9:45", date(2026, 6, 9), "08:15", "09:45", int(1.5 * H)),
    ("8 to 10", date(2026, 6, 9), "08:00", "10:00", 2 * H),
]


@pytest.mark.parametrize(("spec", "wd", "start", "end", "seconds"), CORPUS)
def test_corpus(spec, wd, start, end, seconds):
    r = resolve_entry(spec, NOW)
    assert r.work_date == wd, spec
    if start is None:
        assert r.started_at is None and r.ended_at is None, spec
    else:
        assert r.started_at is not None and r.ended_at is not None, spec
        assert r.started_at.time() == time.fromisoformat(start), spec
        assert r.ended_at.time() == time.fromisoformat(end), spec
    assert r.seconds == seconds, spec


REJECTED = [
    "",  # empty
    "banana",  # unknown word
    "9am",  # point without end/duration
    "today",  # date without body
    "this morning",  # part-of-day without body
    "5pm to 9am",  # negative interval
    "9am to 9am",  # zero interval
    "1am to 11pm",  # > 14h
    "0m",  # zero duration
    "16h",  # bare duration > 14h
    "25:00 to 26:00",  # nonsense times
    "9:75-10",  # invalid minutes
    "13pm to 14pm",  # meridiem with 24h hour
    "9-5 today yesterday",  # two dates
    "9-5 and 6-7",  # unknown connective
    "2/30 2h",  # not a real date
    "12/25 2h",  # future date (Dec 2026)
    "9-5 8-9",  # two bodies
    "last 2h",  # 'last' without weekday
    "tomorrow 9-5",  # future keyword not supported
]


@pytest.mark.parametrize("spec", REJECTED)
def test_rejected(spec):
    with pytest.raises(ParseError):
        resolve_entry(spec, NOW)


def test_ambiguous_raises_with_candidates():
    # 6-8: no am/pm assignment puts both endpoints inside the 7-19 window,
    # so several readings survive and the parser must ask
    with pytest.raises(AmbiguousTimeError) as exc:
        resolve_entry("6 to 8", NOW)
    assert len(exc.value.candidates) >= 2


def test_ambiguity_resolved_by_meridiem():
    r = resolve_entry("8pm to 10pm", NOW)
    assert r.started_at.time() == time(20, 0)


def test_ambiguity_resolved_by_part_of_day():
    r = resolve_entry("tonight 8 to 10", NOW)
    assert r.started_at.time() == time(20, 0)


def test_weekday_never_resolves_to_future():
    # Wednesday from a Tuesday must be last week's Wednesday
    r = resolve_entry("wednesday 1h", NOW)
    assert r.work_date == date(2026, 6, 3)
    assert r.work_date <= NOW.date()


def test_midnight_end_allowed():
    r = resolve_entry("10pm to midnight", NOW)
    assert r.seconds == 2 * H


def test_resolve_point_prefers_nearest_to_now():
    # 15:00 now: bare "9" → 9am (6h away) over 9pm (6h away)... tie-ish; explicit cases:
    assert resolve_point("2", NOW).time() == time(14, 0)  # 2pm is 1h ago vs 2am 13h ago
    assert resolve_point("9am", NOW).time() == time(9, 0)
    assert resolve_point("yesterday 11pm", NOW).date() == date(2026, 6, 8)


def test_resolve_point_rejects_ranges():
    with pytest.raises(ParseError):
        resolve_point("9 to 5", NOW)
