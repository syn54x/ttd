from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from ferro import FerroField
from ferro.models import Model


class TaxPayment(Model):
    """An estimated-tax remittance actually sent to the IRS.

    Payments are *for* an IRS quarter (year + 1..4), not derived from their
    date — remittance happens after the quarter ends. Multiple payments per
    quarter are allowed and summed.
    """

    id: Annotated[UUID | None, FerroField(primary_key=True)] = None
    year: Annotated[int, FerroField(index=True)]
    quarter: int  # 1..4
    amount: Decimal
    paid_on: Annotated[date, FerroField(db_type="date")]
    note: str = ""
    created_at: datetime
