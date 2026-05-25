"""Billable hour calculations from intervals."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from ttd.core.exceptions import ValidationError

_SECONDS_PER_HOUR = Decimal(3600)


def duration_from_interval(started_at: datetime, ended_at: datetime) -> Decimal:
    """Return billable hours as the exact span between UTC-aware bounds."""
    _require_aware_utc(started_at, "started_at")
    _require_aware_utc(ended_at, "ended_at")
    if ended_at <= started_at:
        raise ValidationError("ended_at must be after started_at")
    seconds = Decimal((ended_at - started_at).total_seconds())
    return seconds / _SECONDS_PER_HOUR


def recompute_interval_snapshot(started_at: datetime, ended_at: datetime) -> Decimal:
    """Recompute stored billable hours after interval bounds change."""
    return duration_from_interval(started_at, ended_at)


def _require_aware_utc(value: datetime, field: str) -> None:
    if value.tzinfo is None:
        raise ValidationError(f"{field} must be timezone-aware (UTC)")
    if value.tzinfo != UTC:
        raise ValidationError(f"{field} must use UTC (tzinfo=timezone.utc)")
