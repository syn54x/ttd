"""Pure billing domain helpers (no persistence)."""

from ttd.core.domain.aggregates import (
    SoftMaxStatus,
    soft_max_status,
    sum_billable_hours,
)
from ttd.core.domain.hours import duration_from_interval, recompute_interval_snapshot
from ttd.core.domain.rates import (
    ImpliedRate,
    effective_hourly_rate,
    implied_hourly_rate,
)

__all__ = [
    "ImpliedRate",
    "SoftMaxStatus",
    "duration_from_interval",
    "effective_hourly_rate",
    "implied_hourly_rate",
    "recompute_interval_snapshot",
    "soft_max_status",
    "sum_billable_hours",
]
