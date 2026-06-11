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


def parse_period(text: str, today: date) -> Period:
    """Parse a human period spec: '' / 'last month' / 'this month' /
    'YYYY-MM' / 'YYYY-MM-DD to YYYY-MM-DD'."""
    text = text.strip().lower()
    if text in ("", "last month"):
        return month_period(today, last=True)
    if text == "this month":
        return month_period(today)
    if _MONTH_RE.match(text):
        return month_period(today, ym=text)
    if m := _RANGE_RE.match(text):
        try:
            return range_period(date.fromisoformat(m[1]), date.fromisoformat(m[2]))
        except ValueError as exc:
            raise TtdError(f"Not a real date in '{text}' ({exc})") from exc
    raise TtdError(
        f"Can't read period '{text}' — try '2026-05', 'last month', 'this month', "
        "or '2026-05-01 to 2026-05-15'"
    )
