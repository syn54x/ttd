"""Rich rendering for reports: tables, sparklines, day bars."""

from datetime import date
from decimal import Decimal

from ttd.core.money import format_hours, format_money

BLOCKS = " ▁▂▃▄▅▆▇█"


def sparkline(values: list[int]) -> str:
    """Seconds-per-slot → unicode sparkline."""
    if not values or max(values) == 0:
        return "[muted]" + "·" * len(values) + "[/muted]"
    peak = max(values)
    out = []
    for v in values:
        idx = 0 if v == 0 else max(1, round(v / peak * (len(BLOCKS) - 1)))
        out.append(BLOCKS[idx] if v else "·")
    return "[accent]" + "".join(out) + "[/accent]"


def day_series(by_date: dict[date, int], days: list[date]) -> list[int]:
    return [by_date.get(d, 0) for d in days]


def hours_cell(seconds: int, billable_seconds: int | None = None) -> str:
    text = format_hours(seconds)
    if billable_seconds is not None and billable_seconds != seconds:
        text += f" [muted]({format_hours(billable_seconds)} billable)[/muted]"
    return text


def money_cell(value: Decimal | None, currency: str) -> str:
    if value is None:
        return "[muted]—[/muted]"
    return format_money(value, currency)
