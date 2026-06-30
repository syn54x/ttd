from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from ferro import FerroField
from ferro.models import Model


class Expense(Model):
    """A purchased item billed back to a client, attached to a project.

    ``invoice_id`` set means billed & locked — mirrors ``Entry``. ``amount`` is
    pure pass-through: what you paid is what the client is billed.
    """

    id: Annotated[UUID | None, FerroField(primary_key=True)] = None
    project_id: Annotated[UUID, FerroField(index=True)]
    incurred_date: Annotated[date, FerroField(db_type="date", index=True)]
    description: str
    amount: Decimal
    note: str = ""
    invoice_id: Annotated[UUID | None, FerroField(index=True)] = None
    created_at: datetime
    updated_at: datetime


class ExpenseReceipt(Model):
    """Optional receipt for an expense, stored base64 in its own table.

    Separate table so ``expense list`` never loads receipt bytes. Base64 text
    rather than raw ``bytes`` because ferro-orm#160 blocks binary via the ORM.
    """

    id: Annotated[UUID | None, FerroField(primary_key=True)] = None
    expense_id: Annotated[UUID, FerroField(unique=True, index=True)]
    filename: str
    content_type: str
    data_b64: Annotated[str, FerroField(db_type="text")]
