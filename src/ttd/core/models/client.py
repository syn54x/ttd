"""Client persistence model."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from ferro.base import FerroField, varchar
from ferro.models import Model


class Client(Model):
    """Contracted customer with default hourly rate and currency."""

    id: Annotated[UUID | None, FerroField(primary_key=True)] = None
    """Stable identifier for surfaces and export."""

    name: str
    """Human-readable client name."""

    default_hourly_rate: Decimal
    """Default billable rate for hourly child projects."""

    currency: Annotated[str, FerroField(db_type=varchar(3))]
    """ISO 4217 currency code (e.g. USD)."""
