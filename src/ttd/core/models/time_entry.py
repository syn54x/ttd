"""Time entry persistence model."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from ferro.base import FerroField
from ferro.models import Model

from ttd.core.models.enums import EntryMode


class TimeEntry(Model):
    """Logged work on a project; billable hours are canonical."""

    id: Annotated[UUID | None, FerroField(primary_key=True)] = None
    """Stable identifier for surfaces and export."""

    project_id: Annotated[UUID, FerroField(index=True)]
    """Project this entry belongs to."""

    work_date: Annotated[date, FerroField(db_type="date")]
    """Calendar day used for period rollups."""

    entry_mode: Annotated[EntryMode, FerroField(db_type="text")]
    """Duration (hours only) or interval (time-in/out)."""

    billable_hours: Decimal
    """Canonical billable hours for totals and export."""

    started_at: datetime | None = None
    """Interval start (UTC); null for duration mode."""

    ended_at: datetime | None = None
    """Interval end (UTC); null for duration mode."""

    billable: bool = True
    """When false, excluded from billable-hour aggregates."""

    note: str | None = None
    """Optional description."""
