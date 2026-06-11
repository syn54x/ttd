from datetime import datetime
from typing import Annotated
from uuid import UUID

from ferro import FerroField
from ferro.models import Model

# Well-known id for the singleton running-timer row (enforced in services.timer).
TIMER_SINGLETON_ID = UUID("00000000-0000-0000-0000-000000000001")


class TimerState(Model):
    """The single running timer, if any. Entries only ever hold completed work."""

    id: Annotated[UUID | None, FerroField(primary_key=True)] = None
    project_id: Annotated[UUID, FerroField(index=True)]
    started_at: datetime
    note: str = ""
