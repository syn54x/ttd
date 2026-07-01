"""Resolve report periods (day/week/month/range) against a reference date."""

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta

from ttd.core.errors import TtdError


@dataclass(frozen=True)
class Period:
    start: date
    end: date  # inclusive
    label: str

    def days(self) -> list[date]:
        return [self.start + timedelta(days=i) for i in range((self.end - self.start).days + 1)]


def day_period(d: date) -> Period:
    return Period(d, d, d.strftime("%A, %b %-d %Y"))


def week_period(today: date, week_start: str = "monday", last: bool = False) -> Period:
    offset = today.weekday() if week_start == "monday" else (today.weekday() + 1) % 7
    start = today - timedelta(days=offset)
    if last:
        start -= timedelta(days=7)
    end = start + timedelta(days=6)
    return Period(start, end, f"Week of {start:%b %-d} – {end:%b %-d %Y}")


def month_period(today: date, last: bool = False, ym: str | None = None) -> Period:
    if ym is not None:
        try:
            year, month = (int(part) for part in ym.split("-"))
            first = date(year, month, 1)
        except ValueError as exc:
            raise TtdError(f"Months are YYYY-MM (got '{ym}')") from exc
    elif last:
        first = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    else:
        first = today.replace(day=1)
    days_in_month = calendar.monthrange(first.year, first.month)[1]
    return Period(first, first.replace(day=days_in_month), first.strftime("%B %Y"))


def range_period(start: date, end: date) -> Period:
    if end < start:
        raise TtdError(f"--to {end} is before --from {start}")
    return Period(start, end, f"{start:%b %-d %Y} – {end:%b %-d %Y}")


_MONTH_RE = re.compile(r"^(\d{4})-(\d{1,2})$")
_RANGE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\s*(?:to|\.\.|–|-)\s*(\d{4}-\d{2}-\d{2})$")

_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
_RELATIVE_RE = re.compile(r"^last\s+(\w+)\s+(day|days|week|weeks|month|months)$")


def _subtract_months(d: date, n: int) -> date:
    """d shifted back n calendar months, clamping the day to the target month."""
    month_index = (d.year * 12 + (d.month - 1)) - n
    year, month = divmod(month_index, 12)
    month += 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


def _parse_relative(text: str, today: date) -> "Period | None":
    """Rolling 'last <N> days|weeks|months' ending today; None if no match."""
    m = _RELATIVE_RE.match(text)
    if m is None:
        return None
    raw, unit = m[1], m[2].rstrip("s")
    n = _NUMBER_WORDS.get(raw) or (int(raw) if raw.isdigit() else 0)
    if n < 1:
        raise TtdError(f"'{text}' — the count must be a positive number")
    if unit == "day":
        start = today - timedelta(days=n - 1)
    elif unit == "week":
        start = today - timedelta(days=n * 7 - 1)
    else:  # month
        start = _subtract_months(today, n)
    return range_period(start, today)


_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
_MON = r"[a-z]{3,9}"
_SEP = r"(?:to|through|thru|until|till|\.\.|--|-|–|—)"
_MM_RANGE_RE = re.compile(
    rf"^(?P<m1>{_MON})\s+(?P<d1>\d{{1,2}})\s*{_SEP}\s*(?P<m2>{_MON})\s+(?P<d2>\d{{1,2}})"
    rf"(?:\s+(?P<year>\d{{4}}))?$"
)
_MD_RANGE_RE = re.compile(
    rf"^(?P<m1>{_MON})\s+(?P<d1>\d{{1,2}})\s*{_SEP}\s*(?P<d2>\d{{1,2}})"
    rf"(?:\s+(?P<year>\d{{4}}))?$"
)
_MONTH_ONLY_RE = re.compile(rf"^(?P<m1>{_MON})(?:\s+(?P<year>\d{{4}}))?$")


def _month_num(name: str) -> int | None:
    return _MONTHS.get(name)


def _range_distance(start: date, end: date, today: date) -> int:
    if start <= today <= end:
        return 0
    if today < start:
        return (start - today).days
    return (today - end).days


def _closest_year_range(m1: int, d1: int, m2: int, d2: int, today: date) -> Period:
    """Build (start, end) for the closest non-future year; end wraps to +1 year
    when the end month is earlier than the start month."""
    best: tuple[int, date, date] | None = None
    for y in (today.year, today.year - 1):  # this year first -> ties favor it
        end_year = y + 1 if m2 < m1 else y
        try:
            start = date(y, m1, d1)
            end = date(end_year, m2, d2)
        except ValueError:
            continue
        dist = _range_distance(start, end, today)
        if best is None or dist < best[0]:
            best = (dist, start, end)
    if best is None:
        raise TtdError("Not a real date in that month-name range")
    return range_period(best[1], best[2])


def _fixed_year_range(m1: int, d1: int, m2: int, d2: int, year: int) -> Period:
    end_year = year + 1 if m2 < m1 else year
    try:
        return range_period(date(year, m1, d1), date(end_year, m2, d2))
    except ValueError as exc:
        raise TtdError(f"Not a real date ({exc})") from exc


def _closest_month_year(month: int, today: date) -> int:
    """Closest non-future year for a whole-month reference."""
    best: tuple[int, int] | None = None
    for y in (today.year, today.year - 1):
        first = date(y, month, 1)
        last = date(y, month, calendar.monthrange(y, month)[1])
        dist = _range_distance(first, last, today)
        if best is None or dist < best[0]:
            best = (dist, y)
    assert best is not None
    return best[1]


def _parse_month_name(text: str, today: date) -> "Period | None":
    # whole month: "june" / "june 2025"
    if m := _MONTH_ONLY_RE.match(text):
        num = _month_num(m["m1"])
        if num is None:
            return None
        year = int(m["year"]) if m["year"] else _closest_month_year(num, today)
        return month_period(date(year, num, 1), ym=f"{year}-{num:02d}")
    # month day <sep> month day
    if m := _MM_RANGE_RE.match(text):
        n1, n2 = _month_num(m["m1"]), _month_num(m["m2"])
        if n1 is None or n2 is None:
            return None
        d1, d2 = int(m["d1"]), int(m["d2"])
        if m["year"]:
            return _fixed_year_range(n1, d1, n2, d2, int(m["year"]))
        return _closest_year_range(n1, d1, n2, d2, today)
    # month day <sep> day  (inherit month)
    if m := _MD_RANGE_RE.match(text):
        n1 = _month_num(m["m1"])
        if n1 is None:
            return None
        d1, d2 = int(m["d1"]), int(m["d2"])
        if m["year"]:
            return _fixed_year_range(n1, d1, n1, d2, int(m["year"]))
        return _closest_year_range(n1, d1, n1, d2, today)
    return None


def parse_period(text: str, today: date, *, week_start: str = "monday") -> Period:
    """Parse a human period spec. Supports: '' / 'last month' / 'this month' /
    'this week' / 'last week' / 'last <N> days|weeks|months' / 'YYYY-MM' /
    'YYYY-MM-DD to YYYY-MM-DD' / month-name ranges like 'june 16 to june 30'."""
    text = text.strip().lower()
    if text in ("", "last month"):
        return month_period(today, last=True)
    if text == "this month":
        return month_period(today)
    if text == "this week":
        return week_period(today, week_start)
    if text == "last week":
        return week_period(today, week_start, last=True)
    if _MONTH_RE.match(text):
        return month_period(today, ym=text)
    if m := _RANGE_RE.match(text):
        try:
            return range_period(date.fromisoformat(m[1]), date.fromisoformat(m[2]))
        except ValueError as exc:
            raise TtdError(f"Not a real date in '{text}' ({exc})") from exc
    if relative := _parse_relative(text, today):
        return relative
    if month_name := _parse_month_name(text, today):
        return month_name
    raise TtdError(
        f"Can't read period '{text}' — try '2026-05', 'last month', 'this week', "
        "'last two weeks', 'june 16 to june 30', or '2026-05-01 to 2026-05-15'"
    )
