"""Rate resolution and implied hourly rate."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ttd.core.exceptions import ValidationError
from ttd.core.models.client import Client
from ttd.core.models.enums import BillingMode
from ttd.core.models.project import Project


@dataclass(frozen=True, slots=True)
class ImpliedRate:
    """Derived hourly rate for a fixed-price project."""

    amount: Decimal
    """Billable amount per hour."""

    currency: str
    """ISO 4217 currency code."""


def effective_hourly_rate(client: Client, project: Project) -> tuple[Decimal, str]:
    """Resolve hourly rate and currency for an hourly project."""
    if project.billing_mode != BillingMode.HOURLY:
        raise ValidationError("effective hourly rate applies only to hourly projects")
    if project.hourly_rate is not None and project.currency is not None:
        return project.hourly_rate, project.currency
    return client.default_hourly_rate, client.currency


def implied_hourly_rate(
    contract_total: Decimal,
    currency: str,
    billable_hours_sum: Decimal,
) -> ImpliedRate | None:
    """Contract total divided by logged billable hours; None when hours are zero."""
    if billable_hours_sum <= 0:
        return None
    return ImpliedRate(amount=contract_total / billable_hours_sum, currency=currency)
