from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from ferro import FerroField
from ferro.models import Model

from ttd.storage.models.enums import EntrySource


class Entry(Model):
    """A completed chunk of work.

    ``work_date`` is the local workday all rollups group by. Interval entries
    carry ``started_at``/``ended_at``; duration-only entries leave both None.
    ``seconds`` is always populated. ``invoice_id`` set means billed & locked.
    """

    id: Annotated[UUID | None, FerroField(primary_key=True)] = None
    project_id: Annotated[UUID, FerroField(index=True)]
    work_date: Annotated[date, FerroField(db_type="date", index=True)]
    started_at: datetime | None = None
    ended_at: datetime | None = None
    seconds: int
    note: str = ""
    tags: str = ""
    billable: bool = True
    source: Annotated[EntrySource, FerroField(db_type="text")] = EntrySource.LOG
    invoice_id: Annotated[UUID | None, FerroField(index=True)] = None
    created_at: datetime
    updated_at: datetime
