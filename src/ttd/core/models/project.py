"""Project persistence model."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from ferro.base import FerroField, varchar
from ferro.models import Model

from ttd.core.models.enums import BillingMode


class Project(Model):
    """Billable work under a client — hourly or fixed-price."""

    __ferro_composite_uniques__ = (("client_id", "name"),)

    id: Annotated[UUID | None, FerroField(primary_key=True)] = None
    """Stable identifier for surfaces and export."""

    client_id: Annotated[UUID, FerroField(index=True)]
    """Owning client."""

    name: str
    """Project name, unique within the client."""

    billing_mode: Annotated[BillingMode, FerroField(db_type="text")]
    """Hourly rate billing or fixed-price contract tracking."""

    hourly_rate: Decimal | None = None
    """Override hourly rate when billing_mode is hourly; pair with currency."""

    currency: Annotated[str | None, FerroField(db_type=varchar(3))] = None
    """Override currency when billing_mode is hourly."""

    contract_total: Decimal | None = None
    """Lump-sum contract amount when billing_mode is fixed_price."""

    soft_max_hours: Decimal | None = None
    """Informational effort threshold; logging is never blocked."""

    rounding_increment_minutes: int | None = None
    """Override client export rounding increment; unset inherits client."""
