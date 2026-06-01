"""Export-time hour rounding."""

from __future__ import annotations

from decimal import ROUND_CEILING, Decimal

from ttd.core.models.client import Client
from ttd.core.models.project import Project


def _resolve_rounding_minutes(value: object) -> int | None:
    """Coerce model field values; ferro may yield FieldProxy when unset or unloaded."""
    if value is None or isinstance(value, int):
        return value
    return None


def effective_rounding_increment(client: Client, project: Project) -> int | None:
    """Project override when set; otherwise client default."""
    project_minutes = _resolve_rounding_minutes(project.rounding_increment_minutes)
    if project_minutes is not None:
        return project_minutes
    return _resolve_rounding_minutes(client.rounding_increment_minutes)


def round_hours_up(hours: Decimal, increment_minutes: int | None) -> Decimal:
    """Round billable hours up to increment; no-op when increment is unset."""
    if increment_minutes is None:
        return hours
    increment_hours = Decimal(increment_minutes) / Decimal(60)
    units = (hours / increment_hours).to_integral_value(rounding=ROUND_CEILING)
    return units * increment_hours
