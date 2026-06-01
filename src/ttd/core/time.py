"""Natural-language and structured date/time parsing for capture."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time

from timefhuman import tfhConfig, timefhuman

from ttd.core.exceptions import ValidationError


@dataclass(frozen=True, slots=True)
class ParsedInterval:
    """Work date and UTC interval bounds from a capture phrase."""

    work_date: date
    started_at: datetime
    ended_at: datetime


def reference_now() -> datetime:
    """Anchor for relative phrases (local wall clock, naive)."""
    return datetime.now()


def _config(now: datetime | None = None) -> tfhConfig:
    return tfhConfig(now=now or reference_now())


def parse_work_date(value: str, *, now: datetime | None = None) -> date:
    """Parse YYYY-MM-DD or phrases such as today / yesterday."""
    text = value.strip()
    if not text:
        raise ValidationError("Work date is required")
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass

    results = timefhuman(text, config=_config(now))
    if not results:
        raise ValidationError(
            f"Could not parse work date '{value}'; use YYYY-MM-DD or today / yesterday"
        )
    first = _first_datetime(results)
    return first.date()


def parse_interval_phrase(
    phrase: str, *, now: datetime | None = None
) -> ParsedInterval:
    """Parse a phrase such as ``today 8am to 5pm`` into work date and UTC bounds."""
    text = phrase.strip()
    if not text:
        raise ValidationError("Interval phrase is required")
    started, ended = _extract_range(timefhuman(text, config=_config(now)), text)
    work_date = started.date()
    return ParsedInterval(
        work_date=work_date,
        started_at=_as_utc(started),
        ended_at=_as_utc(ended),
    )


def parse_interval_parts(
    *,
    work_date: str | None,
    time_from: str,
    time_to: str,
    now: datetime | None = None,
) -> ParsedInterval:
    """Parse separate date and clock strings into an interval."""
    day = (work_date or "today").strip()
    start_text = time_from.strip()
    end_text = time_to.strip()
    if not start_text or not end_text:
        raise ValidationError("Both interval start and end are required")
    phrase = f"{day} {start_text} to {end_text}"
    return parse_interval_phrase(phrase, now=now)


def parse_clock_on_work_date(
    work_date: date, clock: str, *, now: datetime | None = None
) -> datetime:
    """Parse HH:MM or natural clock text on a calendar work date (stored as UTC)."""
    text = clock.strip()
    if not text:
        raise ValidationError("Time is required")
    if _looks_like_clock_only(text):
        return _as_utc(datetime.combine(work_date, _parse_hhmm(text)))
    phrase = f"{work_date.isoformat()} {text}"
    results = timefhuman(phrase, config=_config(now))
    if not results:
        raise ValidationError(f"Could not parse time '{clock}'")
    dt = _first_datetime(results)
    if dt.date() != work_date:
        raise ValidationError(
            f"Time '{clock}' does not match work date {work_date.isoformat()}"
        )
    return _as_utc(dt)


def _looks_like_clock_only(text: str) -> bool:
    parts = text.split(":")
    return len(parts) in (2, 3) and all(part.isdigit() for part in parts)


def _parse_hhmm(text: str) -> time:
    parts = text.split(":")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
        second = int(parts[2]) if len(parts) == 3 else 0
        return time(hour, minute, second)
    except ValueError as exc:
        raise ValidationError(f"Invalid time '{text}'; use HH:MM or HH:MM:SS") from exc


def _extract_range(
    results: list[datetime | tuple[datetime, datetime] | list[datetime]],
    source: str,
) -> tuple[datetime, datetime]:
    ranges: list[tuple[datetime, datetime]] = []
    for item in results:
        if isinstance(item, tuple) and len(item) == 2:
            ranges.append(item)
    if len(ranges) != 1:
        raise ValidationError(
            f"Could not parse interval '{source}'; "
            "use a single range like 'today 8am to 5pm'"
        )
    return ranges[0]


def _first_datetime(
    results: list[datetime | tuple[datetime, datetime] | list[datetime]],
) -> datetime:
    for item in results:
        if isinstance(item, datetime):
            return item
        if isinstance(item, tuple) and item:
            return item[0]
    raise ValidationError("No date or time found in phrase")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
