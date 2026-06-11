from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from ferro import FerroField, varchar
from ferro.models import Model

from ttd.storage.models.enums import InvoiceStatus


class Invoice(Model):
    """A numbered bill for one client over a period. Numbers are never reused."""

    id: Annotated[UUID | None, FerroField(primary_key=True)] = None
    number: Annotated[str, FerroField(unique=True, index=True)]
    client_id: Annotated[UUID, FerroField(index=True)]
    period_start: Annotated[date, FerroField(db_type="date")]
    period_end: Annotated[date, FerroField(db_type="date")]
    issued_date: Annotated[date, FerroField(db_type="date")]
    due_date: Annotated[date | None, FerroField(db_type="date")] = None
    currency: Annotated[str, FerroField(db_type=varchar(3))] = "USD"
    subtotal: Decimal
    tax_rate: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")
    total: Decimal
    status: Annotated[InvoiceStatus, FerroField(db_type="text")] = InvoiceStatus.DRAFT
    notes: str = ""
    created_at: datetime


class InvoiceLine(Model):
    """One project-day on an invoice; ``rate`` is frozen at invoice time."""

    id: Annotated[UUID | None, FerroField(primary_key=True)] = None
    invoice_id: Annotated[UUID, FerroField(index=True)]
    project_id: Annotated[UUID, FerroField(index=True)]
    work_date: Annotated[date, FerroField(db_type="date")]
    billed_seconds: int
    rate: Decimal
    amount: Decimal
    description: str = ""
