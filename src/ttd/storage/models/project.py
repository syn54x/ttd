from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from ferro import FerroField
from ferro.models import Model


class Project(Model):
    """Billable work under a client. ``hourly_rate`` of None inherits the client rate."""

    __ferro_composite_uniques__ = (("client_id", "slug"),)

    id: Annotated[UUID | None, FerroField(primary_key=True)] = None
    client_id: Annotated[UUID, FerroField(index=True)]
    name: str
    slug: Annotated[str, FerroField(index=True)]
    hourly_rate: Decimal | None = None
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
