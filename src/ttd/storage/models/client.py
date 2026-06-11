from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from ferro import FerroField, varchar
from ferro.models import Model


class Client(Model):
    """Contracted customer. ``slug`` is the CLI handle."""

    id: Annotated[UUID | None, FerroField(primary_key=True)] = None
    name: str
    slug: Annotated[str, FerroField(unique=True, index=True)]
    contact_name: str | None = None
    email: str | None = None
    address: str | None = None
    currency: Annotated[str, FerroField(db_type=varchar(3))] = "USD"
    hourly_rate: Decimal | None = None
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
