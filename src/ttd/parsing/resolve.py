"""Resolve a ParsedSpan against a clock and config into concrete times.

All functions are pure over the injected ``now``; the am/pm inference window
comes from ``[parsing]`` config.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from ttd.config.schema import ParsingConfig
from ttd.core.errors import AmbiguousTimeError, ParseError
from ttd.parsing.grammar import ClockTime, ParsedSpan, parse_spec

MAX_INTERVAL = timedelta(hours=14)

_POD_MERIDIEM = {"morning": "am", "afternoon": "pm", "evening": "pm", "night": "pm"}


@dataclass(frozen=True)
class ResolvedSpan:
    work_date: date
    started_at: datetime | None
    ended_at: datetime | None
    seconds: int

    @property
    def is_interval(self) -> bool:
        return self.started_at is not None


def _resolve_date(span: ParsedSpan, now: datetime) -> date:
    today = now.date()
    if span.date_keyword == "today":
        return today
    if span.date_keyword == "yesterday":
        return today - timedelta(days=1)
    if span.weekday is not None:
        if span.last_weekday:
            days_back = ((today.weekday() - span.weekday - 1) % 7) + 1
        else:
            days_back = (today.weekday() - span.weekday) % 7
        return today - timedelta(days=days_back)
    if span.date is not None:
        year, month, day = span.date
        try:
            resolved = date(year or today.year, month, day)
        except ValueError as exc:
            raise ParseError(f"'{span.raw}': not a real date ({exc})") from exc
        if resolved > today:
            raise ParseError(
                f"'{span.raw}' resolves to {resolved.isoformat()}, which is in the future"
            )
        return resolved
    return today


def _clock_candidates(t: ClockTime, bias: str | None) -> list[time]:
    hour, minute, meridiem = t
    if meridiem == "24":  # leading-zero form, already exact
        return [time(hour, minute)]
    meridiem = meridiem or (bias if hour <= 12 else None)
    if meridiem == "am":
        return [time(0 if hour == 12 else hour, minute)]
    if meridiem == "pm":
        return [time(hour if hour == 12 else (hour + 12) % 24, minute)]
    if hour == 0 or hour > 12:  # unambiguous 24h form
        return [time(hour, minute)]
    if hour == 12:
        return [time(12, minute), time(0, minute)]
    return [time(hour, minute), time(hour + 12, minute)]


def _fmt(t: time) -> str:
    return t.strftime("%-I:%M%p").lower()


def _resolve_interval(
    span: ParsedSpan, work_date: date, config: ParsingConfig
) -> tuple[datetime, datetime]:
    assert span.start is not None
    bias = _POD_MERIDIEM.get(span.part_of_day) if span.part_of_day else None
    window_start = time(config.workday_start, 0)
    window_end = time(config.workday_end, 0)

    candidates: list[tuple[datetime, datetime]] = []
    for start_clock in _clock_candidates(span.start, bias):
        start_dt = datetime.combine(work_date, start_clock)
        if span.end is not None:
            ends = [datetime.combine(work_date, e) for e in _clock_candidates(span.end, bias)]
        else:
            assert span.duration is not None
            ends = [start_dt + timedelta(seconds=span.duration)]
        for end_dt in ends:
            if end_dt.time() == time(0, 0) and end_dt <= start_dt:
                end_dt += timedelta(days=1)  # "10pm to midnight"
            elif end_dt.date() != work_date:
                continue  # cross-midnight intervals unsupported
            if end_dt <= start_dt or end_dt - start_dt > MAX_INTERVAL:
                continue
            candidates.append((start_dt, end_dt))

    if not candidates:
        raise ParseError(f"'{span.raw}' doesn't resolve to a positive interval within one day")
    if len(candidates) == 1:
        return candidates[0]

    in_window = [
        (s, e)
        for s, e in candidates
        if window_start <= s.time() <= window_end and window_start <= e.time() <= window_end
    ]
    if len(in_window) == 1:
        return in_window[0]

    pool = in_window or candidates
    labelled = [
        (f"{_fmt(s.time())} to {_fmt(e.time())}", f"{_fmt(s.time())}-{_fmt(e.time())}")
        for s, e in pool
    ]
    raise AmbiguousTimeError(
        f"'{span.raw}' is ambiguous — could be {' or '.join(label for label, _ in labelled)}. "
        "Add am/pm to pin it down.",
        candidates=labelled,
    )


def resolve_entry(
    spec_or_span: str | ParsedSpan,
    now: datetime,
    config: ParsingConfig | None = None,
) -> ResolvedSpan:
    """Resolve a log spec into a work_date + interval or bare duration."""
    span = parse_spec(spec_or_span) if isinstance(spec_or_span, str) else spec_or_span
    config = config or ParsingConfig()
    work_date = _resolve_date(span, now)

    if span.start is not None and span.end is None and span.duration is None:
        raise ParseError(
            f"'{span.raw}' has a start time but no end or duration — "
            "try '9am to 5pm' or '9am for 3h'"
        )
    if not span.has_body:
        raise ParseError(f"'{span.raw}' has no hours in it — try '2h' or '9am to 5pm'")

    if span.start is None:
        assert span.duration is not None
        if span.duration > int(MAX_INTERVAL.total_seconds()):
            raise ParseError(
                f"'{span.raw}' is longer than {MAX_INTERVAL.total_seconds() / 3600:.0f}h"
            )
        return ResolvedSpan(work_date, None, None, span.duration)

    started_at, ended_at = _resolve_interval(span, work_date, config)
    return ResolvedSpan(
        work_date, started_at, ended_at, int((ended_at - started_at).total_seconds())
    )


def resolve_point(
    spec: str,
    now: datetime,
    config: ParsingConfig | None = None,
) -> datetime:
    """Resolve a point-in-time spec ('9am', 'today 8:30') for --at flags.

    Bare ambiguous times prefer the candidate closest to ``now``.
    """
    span = parse_spec(spec)
    if span.duration is not None or span.end is not None:
        raise ParseError(f"Expected a single time, got a range/duration: {spec!r}")
    if span.start is None:
        raise ParseError(f"No time found in {spec!r}")
    work_date = _resolve_date(span, now)
    bias = _POD_MERIDIEM.get(span.part_of_day) if span.part_of_day else None
    options = [datetime.combine(work_date, c) for c in _clock_candidates(span.start, bias)]
    return min(options, key=lambda dt: abs(dt - now))
