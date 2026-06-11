"""Pure aggregation of entries into project-day cells and report groups.

Everything here is plain data in → plain data out; services fetch, this folds.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from ttd.config.schema import BillingConfig
from ttd.core.rounding import round_seconds


@dataclass(frozen=True)
class EntryFacts:
    """The slice of an Entry that rollups need (keeps core import-free)."""

    project_id: UUID
    client_id: UUID
    work_date: date
    seconds: int
    billable: bool
    note: str = ""
    invoiced: bool = False


@dataclass
class DayCell:
    """One project-day: the unit invoices and reports roll up to."""

    project_id: UUID
    client_id: UUID
    work_date: date
    seconds: int = 0
    billable_seconds: int = 0
    entry_count: int = 0
    notes: list[str] = field(default_factory=list)

    def billed_seconds(self, config: BillingConfig) -> int:
        return round_seconds(self.billable_seconds, config)


def rollup_days(entries: list[EntryFacts]) -> list[DayCell]:
    """Group entries into per-(project, day) cells, ordered by date then project."""
    cells: dict[tuple[UUID, date], DayCell] = {}
    for e in entries:
        cell = cells.get((e.project_id, e.work_date))
        if cell is None:
            cell = cells[(e.project_id, e.work_date)] = DayCell(
                e.project_id, e.client_id, e.work_date
            )
        cell.seconds += e.seconds
        cell.entry_count += 1
        if e.billable:
            cell.billable_seconds += e.seconds
        if e.note:
            cell.notes.append(e.note)
    return sorted(cells.values(), key=lambda c: (c.work_date, str(c.project_id)))


def seconds_by_date(entries: list[EntryFacts]) -> dict[date, int]:
    out: dict[date, int] = defaultdict(int)
    for e in entries:
        out[e.work_date] += e.seconds
    return dict(out)


def seconds_by_key[K](entries: list[EntryFacts], key) -> dict[K, int]:
    out: dict[K, int] = defaultdict(int)
    for e in entries:
        out[key(e)] += e.seconds
    return dict(out)


def amount(billed_seconds: int, rate: Decimal | None) -> Decimal | None:
    """Money for a rounded project-day, or None when no rate is configured."""
    if rate is None:
        return None
    return (Decimal(billed_seconds) / Decimal(3600)) * rate
