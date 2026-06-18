"""Rich rendering for reports: tables, sparklines, day bars."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from ttd.config.schema import BillingConfig
from ttd.core.money import format_hours, format_money
from ttd.core.rollup import amount
from ttd.core.rounding import round_seconds
from ttd.services import entries as entry_svc
from ttd.storage.models import Entry, pk

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


def entry_time_label(entry: Entry) -> str:
    """Interval times for an entry, or em dash for duration-only."""
    if entry.started_at and entry.ended_at:
        return f"{entry.started_at:%-I:%M%p}–{entry.ended_at:%-I:%M%p}".lower()
    return "—"


def entry_flags_markup(entry: Entry) -> str:
    """Rich suffix for non-billable / invoiced entries."""
    parts = []
    if not entry.billable:
        parts.append(" [muted](nb)[/muted]")
    if entry.invoice_id is not None:
        parts.append(" [accent]·inv[/accent]")
    return "".join(parts)


def entry_detail_label(entry: Entry) -> str:
    """One-line date + time label for report drill-down rows."""
    day = entry.work_date.strftime("%a %b %-d")
    when = entry_time_label(entry)
    return f"{day} · {when}" if when != "—" else day


def truncate_note(note: str, limit: int = 40) -> str:
    text = note.strip()
    if not text:
        return "—"
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def entry_billed_seconds(entry: Entry, billing: BillingConfig) -> int:
    if not entry.billable:
        return 0
    return round_seconds(entry.seconds, billing)


def entry_amount(entry: Entry, rate: Decimal | None, billing: BillingConfig) -> Decimal | None:
    return amount(entry_billed_seconds(entry, billing), rate)


def group_entries_by_project(
    rows: list[entry_svc.EntryRow],
) -> dict[UUID, list[entry_svc.EntryRow]]:
    out: dict[UUID, list[entry_svc.EntryRow]] = {}
    for r in rows:
        pid = pk(r.project)
        bucket = out.get(pid)
        if bucket is None:
            bucket = out[pid] = []
        bucket.append(r)
    return out
